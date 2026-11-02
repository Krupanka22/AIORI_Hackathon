"""
AIORI - Anomaly Detection Service
Detects behavioral deviations from established device baselines.
"""

import numpy as np
from typing import Optional, Dict, List
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import (
    DeviceProfile,
    TrafficStats,
    SecurityAlert,
    AlertSeverity,
    Device,
)
from services.feature_extractor import FEATURE_NAMES


class AnomalyDetector:
    """
    Detects anomalous device behavior by comparing current features against
    the device's established behavioral baseline.

    Detection methods:
    1. Statistical deviation: Z-score of each feature vs baseline mean/std
    2. Isolation Forest score: ML-based anomaly scoring
    3. Threshold-based rules: Specific rules for known attack patterns
    """

    # Feature-specific anomaly thresholds (Z-score)
    ZSCORE_THRESHOLD = 3.0

    # Anomaly categories
    CATEGORIES = {
        "traffic_surge": "Sudden increase in traffic volume",
        "frequency_anomaly": "Unusual communication frequency",
        "packet_size_anomaly": "Unusual packet sizes",
        "destination_anomaly": "Unexpected destination pattern changes",
        "ratio_anomaly": "Unusual upload/download ratio",
        "protocol_anomaly": "Unexpected protocol distribution changes",
        "pattern_anomaly": "Unusual connection patterns",
        "ml_anomaly": "ML model detected behavioral deviation",
    }

    def __init__(self):
        self._anomaly_threshold = settings.anomaly_threshold

    async def check_device(
        self,
        device_id: str,
        db: AsyncSession,
    ) -> List[SecurityAlert]:
        """
        Check a device's latest behavior against its baseline.
        Returns a list of generated alerts (may be empty if normal).
        """
        # Get the device and its profile
        dev_result = await db.execute(select(Device).where(Device.id == device_id))
        device = dev_result.scalar_one_or_none()
        if not device or not device.profile_id:
            return []

        profile_result = await db.execute(
            select(DeviceProfile).where(DeviceProfile.id == device.profile_id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            return []

        # Get latest feature vector
        latest_result = await db.execute(
            select(TrafficStats)
            .where(TrafficStats.device_id == device_id)
            .where(TrafficStats.feature_vector.isnot(None))
            .order_by(TrafficStats.window_end.desc())
            .limit(1)
        )
        latest_stats = latest_result.scalar_one_or_none()
        if not latest_stats or not latest_stats.feature_vector:
            return []

        current_features = np.array(latest_stats.feature_vector, dtype=np.float64)

        # Get historical features for baseline computation
        history_result = await db.execute(
            select(TrafficStats)
            .where(TrafficStats.device_id == device_id)
            .where(TrafficStats.feature_vector.isnot(None))
            .order_by(TrafficStats.window_end.desc())
            .offset(1)  # Skip the latest (current observation)
            .limit(50)
        )
        history = list(history_result.scalars().all())

        if len(history) < 5:
            # Not enough history to establish a baseline
            return []

        # Build baseline statistics
        baseline_vectors = np.array(
            [h.feature_vector for h in history if h.feature_vector],
            dtype=np.float64,
        )
        baseline_mean = np.mean(baseline_vectors, axis=0)
        baseline_std = np.std(baseline_vectors, axis=0)

        # Replace zero std with small value to avoid division by zero
        baseline_std = np.where(baseline_std == 0, 1e-6, baseline_std)

        # Compute Z-scores
        z_scores = np.abs((current_features - baseline_mean) / baseline_std)

        alerts = []

        # Check each feature for anomalies
        for i, (zscore, feature_name) in enumerate(zip(z_scores, FEATURE_NAMES)):
            if zscore > self.ZSCORE_THRESHOLD:
                category, severity = self._categorize_anomaly(
                    feature_name, zscore, current_features[i], baseline_mean[i]
                )

                alert = SecurityAlert(
                    profile_id=device.profile_id,
                    device_id=device_id,
                    current_ipv6=device.current_ipv6,
                    severity=severity,
                    category=category,
                    anomaly_score=float(zscore),
                    observed_value=f"{feature_name}={current_features[i]:.4f}",
                    expected_baseline=f"mean={baseline_mean[i]:.4f}, std={baseline_std[i]:.4f}",
                    explanation=(
                        f"Feature '{feature_name}' deviates {zscore:.1f} standard deviations "
                        f"from baseline. Observed: {current_features[i]:.4f}, "
                        f"Expected: {baseline_mean[i]:.4f} +/- {baseline_std[i]:.4f}."
                    ),
                )
                db.add(alert)
                alerts.append(alert)

        # ML anomaly check (Isolation Forest)
        from services.ai_fingerprint import fingerprint_engine

        if fingerprint_engine._is_trained and fingerprint_engine._anomaly_detector:
            fv_scaled = fingerprint_engine._scaler.transform(
                current_features.reshape(1, -1)
            )
            ml_score = fingerprint_engine._anomaly_detector.score_samples(fv_scaled)[0]

            # Isolation Forest: negative scores indicate anomalies
            if ml_score < -0.5:
                severity = (
                    AlertSeverity.HIGH
                    if ml_score < -0.7
                    else AlertSeverity.MEDIUM
                )
                alert = SecurityAlert(
                    profile_id=device.profile_id,
                    device_id=device_id,
                    current_ipv6=device.current_ipv6,
                    severity=severity,
                    category="ml_anomaly",
                    anomaly_score=float(abs(ml_score)),
                    observed_value=f"isolation_score={ml_score:.4f}",
                    expected_baseline="Normal range: > -0.5",
                    explanation=(
                        f"Isolation Forest detected anomalous behavior pattern. "
                        f"Score: {ml_score:.4f} (threshold: -0.5). "
                        f"This indicates the overall communication pattern deviates "
                        f"significantly from learned normal behavior."
                    ),
                )
                db.add(alert)
                alerts.append(alert)

        if alerts:
            await db.flush()

            from services.blockchain_service import blockchain_service
            for alert in alerts:
                if alert.profile_id:
                    await blockchain_service.record_anomaly_detected(
                        profile_id=alert.profile_id,
                        ipv6_address=alert.current_ipv6,
                        anomaly_summary=alert.explanation,
                        db=db,
                    )

            # Broadcast alerts
            from api.websocket import broadcast_alert
            for alert in alerts:
                await broadcast_alert({
                    "id": alert.id,
                    "device_id": device_id,
                    "severity": alert.severity.value,
                    "category": alert.category,
                    "explanation": alert.explanation,
                })

            logger.warning(
                f"Detected {len(alerts)} anomalies for device {device_id}"
            )

        return alerts

    def _categorize_anomaly(
        self,
        feature_name: str,
        zscore: float,
        observed: float,
        baseline: float,
    ) -> tuple:
        """Map a feature anomaly to a category and severity."""
        # Category mapping
        category_map = {
            "avg_packet_size": "packet_size_anomaly",
            "avg_inter_arrival_time": "frequency_anomaly",
            "packet_frequency": "frequency_anomaly",
            "upload_download_ratio": "ratio_anomaly",
            "tcp_udp_ratio": "protocol_anomaly",
            "protocol_entropy": "protocol_anomaly",
            "destination_frequency": "destination_anomaly",
            "avg_connection_duration": "pattern_anomaly",
            "connection_periodicity": "pattern_anomaly",
            "duty_cycle": "traffic_surge",
        }
        category = category_map.get(feature_name, "pattern_anomaly")

        # Severity based on Z-score magnitude
        if zscore > 5.0:
            severity = AlertSeverity.CRITICAL
        elif zscore > 4.0:
            severity = AlertSeverity.HIGH
        elif zscore > 3.5:
            severity = AlertSeverity.MEDIUM
        else:
            severity = AlertSeverity.LOW

        # Boost severity for traffic surges
        if feature_name in ("packet_frequency", "duty_cycle") and observed > baseline * 5:
            severity = AlertSeverity.HIGH

        return category, severity

    async def check_all_devices(self, db: AsyncSession) -> List[SecurityAlert]:
        """Check all running devices for anomalies."""
        from services.device_manager import device_manager

        all_alerts = []
        for device_id in device_manager.get_running_devices():
            alerts = await self.check_device(device_id, db)
            all_alerts.extend(alerts)

        return all_alerts


# Singleton instance
anomaly_detector = AnomalyDetector()
