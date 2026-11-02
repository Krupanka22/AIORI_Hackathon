"""
AIORI - AI Behavioral Fingerprinting Engine
Machine learning models for device behavioral fingerprinting and similarity matching.
"""

import os
import numpy as np
import joblib
from typing import Optional, List, Dict
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings, BASE_DIR
from database.models import DeviceProfile, TrafficStats, DeviceType


class FingerprintEngine:
    """
    AI engine for behavioral fingerprinting of IoT devices.

    Models:
    1. RandomForest classifier: Predicts device type from behavioral features.
    2. IsolationForest: Anomaly scoring for each device.
    3. Feature-vector similarity: Cosine similarity between behavioral profiles.

    The fingerprint is the normalized feature vector representing a device's
    typical communication pattern. Identity resolution compares fingerprints
    across IPv6 address changes.
    """

    def __init__(self):
        self._model_dir = Path(BASE_DIR / settings.ml_model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)

        self._classifier: Optional[RandomForestClassifier] = None
        self._scaler: Optional[StandardScaler] = None
        self._anomaly_detector: Optional[IsolationForest] = None
        self._is_trained = False

        # Try to load existing models
        self._load_models()

    def _load_models(self):
        """Load pre-trained models from disk if available."""
        classifier_path = self._model_dir / "rf_classifier.joblib"
        scaler_path = self._model_dir / "scaler.joblib"
        anomaly_path = self._model_dir / "isolation_forest.joblib"

        if classifier_path.exists() and scaler_path.exists():
            try:
                self._classifier = joblib.load(classifier_path)
                self._scaler = joblib.load(scaler_path)
                if anomaly_path.exists():
                    self._anomaly_detector = joblib.load(anomaly_path)
                self._is_trained = True
                logger.info("ML models loaded from disk.")
            except Exception as e:
                logger.warning(f"Failed to load models: {e}")
                self._is_trained = False

    def _save_models(self):
        """Save trained models to disk."""
        if self._classifier:
            joblib.dump(
                self._classifier, self._model_dir / "rf_classifier.joblib"
            )
        if self._scaler:
            joblib.dump(self._scaler, self._model_dir / "scaler.joblib")
        if self._anomaly_detector:
            joblib.dump(
                self._anomaly_detector, self._model_dir / "isolation_forest.joblib"
            )
        logger.info("ML models saved to disk.")

    async def train(self, db: AsyncSession) -> dict:
        """
        Train models on collected traffic statistics.

        Requires sufficient data: at least 10 samples per device type.
        """
        # Fetch all traffic stats with known device associations
        result = await db.execute(
            select(TrafficStats).where(TrafficStats.feature_vector.isnot(None))
        )
        all_stats = list(result.scalars().all())

        if len(all_stats) < 20:
            return {
                "status": "insufficient_data",
                "samples": len(all_stats),
                "minimum_required": 20,
            }

        # Build feature matrix and labels
        X = []
        y = []
        device_type_map = {}

        for stats in all_stats:
            if stats.feature_vector and stats.device_id:
                X.append(stats.feature_vector)
                # Get device type for label
                dev_result = await db.execute(
                    select(DeviceType)
                    .select_from(
                        select(TrafficStats.device_id)
                        .where(TrafficStats.id == stats.id)
                        .subquery()
                    )
                )
                # Simplified: use device_id as proxy, we need the actual type
                y.append(stats.device_id)

        # Actually get device types
        from database.models import Device

        X_clean = []
        y_clean = []

        for stats in all_stats:
            if not stats.feature_vector:
                continue
            dev_result = await db.execute(
                select(Device.device_type).where(Device.id == stats.device_id)
            )
            dev_type = dev_result.scalar_one_or_none()
            if dev_type:
                X_clean.append(stats.feature_vector)
                y_clean.append(dev_type.value)

        if len(X_clean) < 20:
            return {
                "status": "insufficient_labeled_data",
                "samples": len(X_clean),
            }

        X_arr = np.array(X_clean, dtype=np.float64)
        y_arr = np.array(y_clean)

        # Handle NaN/Inf
        X_arr = np.nan_to_num(X_arr, nan=0.0, posinf=100.0, neginf=0.0)

        # Scale features
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X_arr)

        # Train Random Forest classifier
        self._classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1,
        )
        self._classifier.fit(X_scaled, y_arr)

        # Train Isolation Forest for anomaly detection
        self._anomaly_detector = IsolationForest(
            n_estimators=100,
            contamination=0.1,
            random_state=42,
            n_jobs=-1,
        )
        self._anomaly_detector.fit(X_scaled)

        self._is_trained = True
        self._save_models()

        # Compute training accuracy
        train_acc = self._classifier.score(X_scaled, y_arr)

        return {
            "status": "trained",
            "samples": len(X_clean),
            "device_types": len(set(y_clean)),
            "training_accuracy": round(train_acc, 4),
            "features_used": len(X_clean[0]) if X_clean else 0,
        }

    def generate_fingerprint(self, feature_vector: List[float]) -> Dict:
        """
        Generate a behavioral fingerprint from a feature vector.

        The fingerprint consists of:
        - The normalized feature vector
        - Predicted device type (if model is trained)
        - Anomaly score (if anomaly model is trained)
        """
        fv = np.array(feature_vector, dtype=np.float64).reshape(1, -1)
        fv = np.nan_to_num(fv, nan=0.0, posinf=100.0, neginf=0.0)

        result = {
            "raw_features": feature_vector,
            "normalized_features": None,
            "predicted_type": None,
            "prediction_confidence": None,
            "anomaly_score": None,
        }

        if self._is_trained and self._scaler:
            fv_scaled = self._scaler.transform(fv)
            result["normalized_features"] = fv_scaled[0].tolist()

            if self._classifier:
                prediction = self._classifier.predict(fv_scaled)[0]
                proba = self._classifier.predict_proba(fv_scaled)[0]
                result["predicted_type"] = prediction
                result["prediction_confidence"] = float(max(proba))

            if self._anomaly_detector:
                score = self._anomaly_detector.score_samples(fv_scaled)[0]
                result["anomaly_score"] = float(score)
        else:
            # Without trained models, use raw features as fingerprint
            result["normalized_features"] = feature_vector

        return result

    def compute_similarity(
        self, fingerprint_a: List[float], fingerprint_b: List[float]
    ) -> float:
        """
        Compute cosine similarity between two behavioral fingerprints.
        Returns a value between 0 (no similarity) and 1 (identical).
        """
        a = np.array(fingerprint_a, dtype=np.float64).reshape(1, -1)
        b = np.array(fingerprint_b, dtype=np.float64).reshape(1, -1)

        # Handle zero vectors
        if np.all(a == 0) or np.all(b == 0):
            return 0.0

        similarity = cosine_similarity(a, b)[0][0]
        return float(max(0.0, similarity))

    async def find_similar_profiles(
        self,
        target_profile: DeviceProfile,
        threshold: float,
        db: AsyncSession,
    ) -> List[Dict]:
        """Find profiles similar to the target based on fingerprint comparison."""
        if not target_profile.fingerprint:
            return []

        target_features = target_profile.fingerprint.get("normalized_features")
        if not target_features:
            target_features = target_profile.fingerprint.get("raw_features", [])

        if not target_features:
            return []

        # Get all other active profiles
        result = await db.execute(
            select(DeviceProfile)
            .where(DeviceProfile.id != target_profile.id)
            .where(DeviceProfile.is_active == True)
        )
        profiles = list(result.scalars().all())

        similarities = []
        for profile in profiles:
            if not profile.fingerprint:
                continue

            comp_features = profile.fingerprint.get(
                "normalized_features",
                profile.fingerprint.get("raw_features", []),
            )
            if not comp_features or len(comp_features) != len(target_features):
                continue

            sim = self.compute_similarity(target_features, comp_features)
            if sim >= threshold:
                similarities.append({
                    "profile_id": profile.id,
                    "label": profile.label,
                    "similarity_score": round(sim, 4),
                    "confidence": round(sim * profile.confidence, 4),
                })

        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similarities

    async def update_profile_fingerprint(
        self,
        profile: DeviceProfile,
        feature_vector: List[float],
        db: AsyncSession,
    ):
        """Update a profile's fingerprint with new observations."""
        fingerprint = self.generate_fingerprint(feature_vector)

        if profile.fingerprint and profile.fingerprint.get("raw_features"):
            # Exponential moving average to smooth fingerprint updates
            alpha = 0.3
            old = np.array(profile.fingerprint["raw_features"])
            new = np.array(feature_vector)
            if len(old) == len(new):
                smoothed = alpha * new + (1 - alpha) * old
                fingerprint = self.generate_fingerprint(smoothed.tolist())

        profile.fingerprint = fingerprint
        profile.last_seen = datetime.now(timezone.utc)

        if fingerprint.get("predicted_type"):
            try:
                profile.device_type_prediction = DeviceType(
                    fingerprint["predicted_type"]
                )
            except ValueError:
                pass

        if fingerprint.get("prediction_confidence"):
            profile.confidence = fingerprint["prediction_confidence"]

        await db.flush()


# Singleton instance
fingerprint_engine = FingerprintEngine()
