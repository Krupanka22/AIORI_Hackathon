"""
AIORI - Attack Traffic Analyzer
Controlled security testing environment for analyzing attack-like patterns.
"""

from typing import Optional, Dict
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SecurityAlert, AlertSeverity


class AttackAnalyzer:
    """
    Analyzes suspicious traffic patterns within the controlled virtual lab.

    Attack categories:
    - dos: Denial of Service traffic patterns
    - port_scan: Port scanning activity
    - auth_brute: Repeated authentication attempts
    - data_exfil: Unusual outbound data transfer
    - c2_comm: Command-and-control-like communication patterns

    IMPORTANT: All analysis occurs within the virtual lab.
    Does not claim to identify real persons from IP addresses.
    """

    ATTACK_CATEGORIES = {
        "dos": {
            "name": "Denial of Service",
            "indicators": [
                "High packet rate",
                "Uniform packet sizes",
                "Single source flooding",
            ],
        },
        "port_scan": {
            "name": "Port Scanning",
            "indicators": [
                "Sequential port access",
                "Short connection durations",
                "Many failed connections",
            ],
        },
        "auth_brute": {
            "name": "Brute Force Authentication",
            "indicators": [
                "Repeated connections to same port",
                "Small packet sizes",
                "Regular timing pattern",
            ],
        },
        "data_exfil": {
            "name": "Data Exfiltration",
            "indicators": [
                "High upload ratio",
                "Unusual destination",
                "Large data volume",
            ],
        },
        "c2_comm": {
            "name": "Command and Control",
            "indicators": [
                "Periodic beaconing",
                "Small, regular packets",
                "Consistent destination",
            ],
        },
    }

    async def analyze_traffic_pattern(
        self,
        device_id: str,
        connection_data: list,
        db: AsyncSession,
    ) -> Dict:
        """
        Analyze connection data for attack patterns.

        This is a classification step that follows anomaly detection.
        When anomalous behavior is detected, this analyzer attempts to
        categorize it.
        """
        if not connection_data:
            return {"classification": "no_data"}

        import numpy as np

        # Extract features relevant to attack classification
        packet_rates = []
        dest_ports = set()
        src_ports = set()
        total_bytes = 0
        connection_durations = []
        unique_destinations = set()

        for conn in connection_data:
            if hasattr(conn, "orig_pkts"):
                packet_rates.append(conn.orig_pkts or 0)
            if hasattr(conn, "dst_port") and conn.dst_port:
                dest_ports.add(conn.dst_port)
            if hasattr(conn, "src_port") and conn.src_port:
                src_ports.add(conn.src_port)
            if hasattr(conn, "orig_bytes"):
                total_bytes += conn.orig_bytes or 0
            if hasattr(conn, "duration") and conn.duration is not None:
                connection_durations.append(conn.duration)
            if hasattr(conn, "dst_ipv6"):
                unique_destinations.add(conn.dst_ipv6)

        n_connections = len(connection_data)

        # Classification heuristics
        scores = {}

        # DoS: High packet rate, many connections
        avg_packets = np.mean(packet_rates) if packet_rates else 0
        if avg_packets > 100 or n_connections > 50:
            scores["dos"] = min(1.0, avg_packets / 500 + n_connections / 100)

        # Port scan: Many destination ports, short durations
        if len(dest_ports) > 20:
            avg_duration = np.mean(connection_durations) if connection_durations else 0
            if avg_duration < 1.0:
                scores["port_scan"] = min(1.0, len(dest_ports) / 100)

        # Data exfiltration: High upload volume
        if total_bytes > 1_000_000:
            scores["data_exfil"] = min(1.0, total_bytes / 10_000_000)

        # C2: Regular timing pattern with consistent destination
        if len(unique_destinations) == 1 and n_connections > 5:
            if connection_durations:
                timing_regularity = (
                    1.0 - np.std(connection_durations) / (np.mean(connection_durations) + 1e-6)
                )
                if timing_regularity > 0.7:
                    scores["c2_comm"] = timing_regularity

        if not scores:
            return {
                "classification": "normal",
                "confidence": 0.0,
                "message": "No attack patterns detected.",
            }

        # Get the highest-scoring classification
        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        # Generate alert if score is significant
        if best_score > 0.3:
            category_info = self.ATTACK_CATEGORIES[best_category]
            severity = (
                AlertSeverity.CRITICAL
                if best_score > 0.8
                else AlertSeverity.HIGH
                if best_score > 0.5
                else AlertSeverity.MEDIUM
            )

            alert = SecurityAlert(
                device_id=device_id,
                severity=severity,
                category=f"attack_{best_category}",
                anomaly_score=best_score,
                explanation=(
                    f"Potential {category_info['name']} activity detected. "
                    f"Confidence: {best_score:.2f}. "
                    f"Indicators: {', '.join(category_info['indicators'][:2])}."
                ),
            )
            db.add(alert)
            await db.flush()

        return {
            "classification": best_category,
            "confidence": round(best_score, 4),
            "category_name": self.ATTACK_CATEGORIES[best_category]["name"],
            "all_scores": {k: round(v, 4) for k, v in scores.items()},
            "indicators_found": n_connections,
        }


# Singleton instance
attack_analyzer = AttackAnalyzer()
