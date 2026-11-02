"""
AIORI - Feature Extraction Pipeline
Extracts behavioral characteristics from network metadata (Zeek connection logs).
Operates on metadata only -- never inspects packet payloads.
"""

import numpy as np
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict

from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ConnectionLog, TrafficStats, Device


# Feature names in canonical order (for ML model input)
FEATURE_NAMES = [
    "avg_packet_size",
    "avg_inter_arrival_time",
    "packet_frequency",
    "upload_download_ratio",
    "tcp_udp_ratio",
    "protocol_entropy",
    "destination_frequency",
    "avg_connection_duration",
    "connection_periodicity",
    "duty_cycle",
]


class FeatureExtractor:
    """
    Extracts behavioral features from connection logs within configurable time windows.

    Feature set (metadata-only):
    1. Average packet size (bytes/packet)
    2. Average inter-arrival time (seconds between connections)
    3. Packet frequency (connections/second)
    4. Upload/download ratio
    5. TCP/UDP distribution ratio
    6. Protocol distribution entropy
    7. Destination frequency (unique destinations / total connections)
    8. Average connection duration
    9. Communication periodicity score (regularity of inter-arrival times)
    10. Activity duty cycle (fraction of window with active connections)
    """

    def __init__(self):
        pass

    async def extract_features_for_device(
        self,
        device_id: str,
        ipv6_address: str,
        window_seconds: int,
        db: AsyncSession,
        window_end: Optional[datetime] = None,
    ) -> Optional[TrafficStats]:
        """
        Extract behavioral features from connection logs for a specific device
        within a time window.
        """
        if window_end is None:
            window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(seconds=window_seconds)

        # Query connections involving this device's IPv6 address
        result = await db.execute(
            select(ConnectionLog)
            .where(
                and_(
                    ConnectionLog.timestamp >= window_start,
                    ConnectionLog.timestamp <= window_end,
                    (
                        (ConnectionLog.src_ipv6 == ipv6_address)
                        | (ConnectionLog.dst_ipv6 == ipv6_address)
                    ),
                )
            )
            .order_by(ConnectionLog.timestamp)
        )
        connections = list(result.scalars().all())

        if not connections:
            return None

        # Calculate features
        features = self._compute_features(connections, ipv6_address, window_seconds)

        # Store in database
        stats = TrafficStats(
            device_id=device_id,
            ipv6_address=ipv6_address,
            window_start=window_start,
            window_end=window_end,
            window_seconds=window_seconds,
            total_packets=features["total_packets"],
            total_bytes=features["total_bytes"],
            avg_packet_size=features["avg_packet_size"],
            avg_inter_arrival_time=features["avg_inter_arrival_time"],
            packet_frequency=features["packet_frequency"],
            upload_bytes=features["upload_bytes"],
            download_bytes=features["download_bytes"],
            upload_download_ratio=features["upload_download_ratio"],
            tcp_packets=features["tcp_packets"],
            udp_packets=features["udp_packets"],
            icmpv6_packets=features["icmpv6_packets"],
            tcp_udp_ratio=features["tcp_udp_ratio"],
            unique_destinations=features["unique_destinations"],
            avg_connection_duration=features["avg_connection_duration"],
            connection_count=features["connection_count"],
            periodicity_score=features["periodicity_score"],
            duty_cycle=features["duty_cycle"],
            feature_vector=features["feature_vector"],
        )

        db.add(stats)
        await db.flush()

        return stats

    def _compute_features(
        self,
        connections: List[ConnectionLog],
        ipv6_address: str,
        window_seconds: int,
    ) -> Dict:
        """Compute all behavioral features from a set of connection logs."""
        n = len(connections)

        # --- Packet counts and bytes ---
        total_orig_pkts = sum(c.orig_pkts or 0 for c in connections)
        total_resp_pkts = sum(c.resp_pkts or 0 for c in connections)
        total_packets = total_orig_pkts + total_resp_pkts

        total_orig_bytes = sum(c.orig_bytes or 0 for c in connections)
        total_resp_bytes = sum(c.resp_bytes or 0 for c in connections)
        total_bytes = total_orig_bytes + total_resp_bytes

        # Determine upload/download relative to the device address
        upload_bytes = 0
        download_bytes = 0
        for c in connections:
            if c.src_ipv6 == ipv6_address:
                upload_bytes += c.orig_bytes or 0
                download_bytes += c.resp_bytes or 0
            else:
                upload_bytes += c.resp_bytes or 0
                download_bytes += c.orig_bytes or 0

        # --- Feature 1: Average packet size ---
        avg_packet_size = total_bytes / total_packets if total_packets > 0 else 0.0

        # --- Feature 2: Average inter-arrival time ---
        timestamps = [c.timestamp for c in connections]
        if len(timestamps) > 1:
            deltas = [
                (timestamps[i + 1] - timestamps[i]).total_seconds()
                for i in range(len(timestamps) - 1)
            ]
            avg_inter_arrival_time = np.mean(deltas)
        else:
            avg_inter_arrival_time = 0.0

        # --- Feature 3: Packet frequency ---
        packet_frequency = n / window_seconds if window_seconds > 0 else 0.0

        # --- Feature 4: Upload/Download ratio ---
        if download_bytes > 0:
            upload_download_ratio = upload_bytes / download_bytes
        elif upload_bytes > 0:
            upload_download_ratio = float("inf")
        else:
            upload_download_ratio = 0.0
        # Clamp for ML
        upload_download_ratio = min(upload_download_ratio, 100.0)

        # --- Feature 5: TCP/UDP ratio ---
        tcp_packets = sum(1 for c in connections if c.protocol == "tcp")
        udp_packets = sum(1 for c in connections if c.protocol == "udp")
        icmpv6_packets = sum(1 for c in connections if c.protocol in ("icmp", "icmpv6"))
        if udp_packets > 0:
            tcp_udp_ratio = tcp_packets / udp_packets
        elif tcp_packets > 0:
            tcp_udp_ratio = float(tcp_packets)
        else:
            tcp_udp_ratio = 0.0
        tcp_udp_ratio = min(tcp_udp_ratio, 100.0)

        # --- Feature 6: Protocol distribution entropy ---
        protocol_counts = {}
        for c in connections:
            proto = c.protocol or "unknown"
            protocol_counts[proto] = protocol_counts.get(proto, 0) + 1
        protocol_entropy = self._entropy(list(protocol_counts.values()))

        # --- Feature 7: Destination frequency ---
        destinations = set()
        for c in connections:
            if c.src_ipv6 == ipv6_address:
                destinations.add(c.dst_ipv6)
            else:
                destinations.add(c.src_ipv6)
        unique_destinations = len(destinations)
        destination_frequency = unique_destinations / n if n > 0 else 0.0

        # --- Feature 8: Average connection duration ---
        durations = [c.duration for c in connections if c.duration is not None]
        avg_connection_duration = np.mean(durations) if durations else 0.0

        # --- Feature 9: Communication periodicity ---
        if len(timestamps) > 2:
            deltas_arr = np.array(deltas)
            if np.mean(deltas_arr) > 0:
                periodicity_score = 1.0 - (
                    np.std(deltas_arr) / np.mean(deltas_arr)
                )
                periodicity_score = max(0.0, min(1.0, periodicity_score))
            else:
                periodicity_score = 0.0
        else:
            periodicity_score = 0.0

        # --- Feature 10: Activity duty cycle ---
        if durations and window_seconds > 0:
            active_time = sum(durations)
            duty_cycle = min(active_time / window_seconds, 1.0)
        else:
            duty_cycle = 0.0

        # Build normalized feature vector for ML
        feature_vector = [
            float(avg_packet_size),
            float(avg_inter_arrival_time),
            float(packet_frequency),
            float(upload_download_ratio),
            float(tcp_udp_ratio),
            float(protocol_entropy),
            float(destination_frequency),
            float(avg_connection_duration),
            float(periodicity_score),
            float(duty_cycle),
        ]

        return {
            "total_packets": total_packets,
            "total_bytes": total_bytes,
            "avg_packet_size": float(avg_packet_size),
            "avg_inter_arrival_time": float(avg_inter_arrival_time),
            "packet_frequency": float(packet_frequency),
            "upload_bytes": upload_bytes,
            "download_bytes": download_bytes,
            "upload_download_ratio": float(upload_download_ratio),
            "tcp_packets": tcp_packets,
            "udp_packets": udp_packets,
            "icmpv6_packets": icmpv6_packets,
            "tcp_udp_ratio": float(tcp_udp_ratio),
            "unique_destinations": unique_destinations,
            "avg_connection_duration": float(avg_connection_duration),
            "connection_count": n,
            "periodicity_score": float(periodicity_score),
            "duty_cycle": float(duty_cycle),
            "feature_vector": feature_vector,
        }

    @staticmethod
    def _entropy(counts: List[int]) -> float:
        """Calculate Shannon entropy of a distribution."""
        total = sum(counts)
        if total == 0:
            return 0.0
        probs = [c / total for c in counts]
        return float(-sum(p * np.log2(p) for p in probs if p > 0))

    async def extract_features_for_all_devices(
        self,
        window_seconds: int,
        db: AsyncSession,
    ) -> List[TrafficStats]:
        """Extract features for all running devices."""
        from services.device_manager import device_manager

        results = []
        for device_id, info in device_manager.get_running_devices().items():
            ipv6_addr = info.get("ipv6_addr")
            if not ipv6_addr:
                continue
            stats = await self.extract_features_for_device(
                device_id, ipv6_addr, window_seconds, db
            )
            if stats:
                results.append(stats)

        return results


# Singleton instance
feature_extractor = FeatureExtractor()
