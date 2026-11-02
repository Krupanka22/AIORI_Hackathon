"""
AIORI - Traffic Monitor Service
Integrates with Zeek and tcpdump to capture and parse actual network traffic.
"""

import asyncio
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import ConnectionLog


class TrafficMonitor:
    """
    Monitors network traffic using Zeek and tcpdump inside WSL2.

    Pipeline:
    1. tcpdump captures packets on the bridge interface -> PCAP files
    2. Zeek processes PCAP files -> structured conn.log
    3. This service parses conn.log -> ConnectionLog database records
    4. Events are broadcast via WebSocket for live dashboard updates
    """

    def __init__(self):
        self._wsl_distro = settings.wsl_distro
        self._bridge_interface = "aiori-br0"
        self._pcap_dir = settings.pcap_dir
        self._zeek_log_dir = settings.zeek_log_dir
        self._capture_task: Optional[asyncio.Task] = None
        self._monitoring = False

    async def _run_wsl(self, command: str, check: bool = True) -> str:
        full_cmd = (
            f"wsl.exe -d {self._wsl_distro} -- bash -lc {subprocess.list2cmdline([command])}"
            if os.name == "nt"
            else command
        )
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if check and proc.returncode != 0:
            raise RuntimeError(f"Monitor command failed: {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def start_capture(self, duration_seconds: Optional[int] = None) -> dict:
        """Start packet capture using tcpdump on the bridge interface."""
        if self._monitoring:
            return {"status": "already_monitoring"}

        # Ensure PCAP directory exists
        await self._run_wsl(f"mkdir -p {self._pcap_dir}", check=False)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pcap_file = f"{self._pcap_dir}/capture_{timestamp}.pcap"

        # Build tcpdump command
        tcpdump_cmd = (
            f"tcpdump -i {self._bridge_interface} -w {pcap_file} "
            f"-n ip6 -s 128"  # Capture only headers (128 bytes), IPv6 only
        )
        if duration_seconds:
            tcpdump_cmd += f" -G {duration_seconds} -W 1"

        try:
            # Kill any existing tcpdump
            await self._run_wsl("pkill -f 'tcpdump.*aiori-br0' 2>/dev/null", check=False)

            # Start tcpdump in background
            self._capture_task = asyncio.create_task(
                self._run_capture(tcpdump_cmd, pcap_file)
            )
            self._monitoring = True

            logger.info(f"Packet capture started: {pcap_file}")
            return {
                "status": "capture_started",
                "pcap_file": pcap_file,
                "interface": self._bridge_interface,
            }
        except Exception as e:
            return {"error": str(e)}

    async def _run_capture(self, command: str, pcap_file: str):
        """Background capture task."""
        try:
            await self._run_wsl(command, check=False)
        except asyncio.CancelledError:
            # Stop tcpdump gracefully
            await self._run_wsl("pkill -f 'tcpdump.*aiori-br0' 2>/dev/null", check=False)
        finally:
            self._monitoring = False
            logger.info(f"Capture stopped. PCAP: {pcap_file}")

    async def stop_capture(self) -> dict:
        """Stop the active packet capture."""
        if self._capture_task:
            self._capture_task.cancel()
            self._capture_task = None

        await self._run_wsl("pkill -f 'tcpdump.*aiori-br0' 2>/dev/null", check=False)
        self._monitoring = False

        return {"status": "capture_stopped"}

    async def process_pcap_with_zeek(self, pcap_file: str) -> dict:
        """
        Process a PCAP file with Zeek to generate structured connection logs.
        """
        zeek_output_dir = f"/tmp/aiori/zeek_output"
        await self._run_wsl(f"mkdir -p {zeek_output_dir}", check=False)

        try:
            # Run Zeek on the PCAP
            await self._run_wsl(
                f"cd {zeek_output_dir} && zeek -r {pcap_file} "
                f"LogAscii::use_json=T 2>/dev/null"
            )

            conn_log = f"{zeek_output_dir}/conn.log"
            exists = await self._run_wsl(
                f"test -f {conn_log} && echo 'exists' || echo 'missing'",
                check=False,
            )

            if "exists" in exists:
                return {
                    "status": "zeek_processed",
                    "conn_log": conn_log,
                    "pcap_file": pcap_file,
                }
            else:
                return {
                    "status": "no_connections",
                    "message": "Zeek did not generate conn.log (no connections in PCAP).",
                }

        except Exception as e:
            return {"error": str(e)}

    async def parse_zeek_conn_log(
        self, conn_log_path: str, db: AsyncSession
    ) -> List[ConnectionLog]:
        """
        Parse a Zeek conn.log (JSON format) and insert records into the database.
        """
        import json as json_lib

        try:
            raw = await self._run_wsl(f"cat {conn_log_path}", check=False)
            if not raw:
                return []

            records = []
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                try:
                    entry = json_lib.loads(line)
                except json_lib.JSONDecodeError:
                    continue

                # Parse Zeek JSON fields
                ts = entry.get("ts", 0)
                if isinstance(ts, (int, float)):
                    timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                else:
                    timestamp = datetime.now(timezone.utc)

                log = ConnectionLog(
                    zeek_uid=entry.get("uid"),
                    timestamp=timestamp,
                    src_ipv6=entry.get("id.orig_h", "::"),
                    dst_ipv6=entry.get("id.resp_h", "::"),
                    src_port=entry.get("id.orig_p"),
                    dst_port=entry.get("id.resp_p"),
                    protocol=entry.get("proto", "unknown"),
                    duration=entry.get("duration"),
                    orig_bytes=entry.get("orig_bytes"),
                    resp_bytes=entry.get("resp_bytes"),
                    orig_pkts=entry.get("orig_pkts"),
                    resp_pkts=entry.get("resp_pkts"),
                    conn_state=entry.get("conn_state"),
                    service=entry.get("service"),
                    raw_log=line,
                )
                db.add(log)
                records.append(log)

                # Broadcast to dashboard
                from api.websocket import broadcast_connection_log
                await broadcast_connection_log({
                    "src_ipv6": log.src_ipv6,
                    "dst_ipv6": log.dst_ipv6,
                    "protocol": log.protocol,
                    "duration": log.duration,
                    "orig_bytes": log.orig_bytes,
                    "resp_bytes": log.resp_bytes,
                })

            await db.flush()
            logger.info(f"Parsed {len(records)} connection records from Zeek log.")
            return records

        except Exception as e:
            logger.error(f"Failed to parse Zeek conn.log: {e}")
            return []

    async def capture_and_process(
        self,
        duration_seconds: int,
        db: AsyncSession,
    ) -> dict:
        """
        Complete pipeline: capture traffic -> process with Zeek -> parse logs.
        """
        # Start capture
        capture_result = await self.start_capture(duration_seconds=duration_seconds)
        if "error" in capture_result:
            return capture_result

        # Wait for capture to complete
        await asyncio.sleep(duration_seconds + 2)
        await self.stop_capture()

        # Find the latest PCAP file
        pcap_file = await self._run_wsl(
            f"ls -t {self._pcap_dir}/capture_*.pcap 2>/dev/null | head -1",
            check=False,
        )
        if not pcap_file:
            return {"error": "No PCAP file found."}

        # Process with Zeek
        zeek_result = await self.process_pcap_with_zeek(pcap_file)
        if "error" in zeek_result:
            return zeek_result

        if zeek_result.get("status") == "no_connections":
            return zeek_result

        # Parse conn.log
        records = await self.parse_zeek_conn_log(zeek_result["conn_log"], db)

        return {
            "status": "completed",
            "pcap_file": pcap_file,
            "connections_parsed": len(records),
        }

    async def process_latest_pcap(self, db: AsyncSession) -> dict:
        """Process the newest completed capture without starting another capture."""
        pcap_file = await self._run_wsl(
            f"ls -t {self._pcap_dir}/capture_*.pcap 2>/dev/null | head -1",
            check=False,
        )
        if not pcap_file:
            return {"error": "No completed PCAP file found."}

        zeek_result = await self.process_pcap_with_zeek(pcap_file)
        if "error" in zeek_result or zeek_result.get("status") == "no_connections":
            return zeek_result

        records = await self.parse_zeek_conn_log(zeek_result["conn_log"], db)
        return {
            "status": "completed",
            "pcap_file": pcap_file,
            "connections_parsed": len(records),
        }


# Singleton instance
traffic_monitor = TrafficMonitor()
