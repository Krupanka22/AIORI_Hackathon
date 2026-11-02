"""
AIORI - Traffic Generator Service
Generates actual network traffic between virtual devices using iPerf3 and custom UDP generators.

IMPORTANT: Does NOT use Scapy (as per project requirements).
"""

import asyncio
import json
import os
import subprocess
from typing import Optional, Dict
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Device, DeviceStatus, DeviceType


# Traffic profiles per device type: defines typical communication patterns
TRAFFIC_PROFILES = {
    DeviceType.CCTV_CAMERA: {
        "description": "Continuous video stream upload, periodic control commands",
        "tcp_ratio": 0.8,
        "udp_ratio": 0.2,
        "avg_bandwidth_kbps": 2000,
        "packet_size_range": (500, 1400),
        "burst_interval_sec": 0,  # Continuous
        "iperf_args": "-t {duration} -b 2M -l 1400",
    },
    DeviceType.TEMPERATURE_SENSOR: {
        "description": "Small periodic UDP readings every few seconds",
        "tcp_ratio": 0.1,
        "udp_ratio": 0.9,
        "avg_bandwidth_kbps": 5,
        "packet_size_range": (50, 200),
        "burst_interval_sec": 5,
        "iperf_args": "-u -t {duration} -b 5K -l 100 --pacing-timer 5000000",
    },
    DeviceType.SMART_DOOR_LOCK: {
        "description": "Infrequent TCP bursts for lock/unlock events",
        "tcp_ratio": 0.95,
        "udp_ratio": 0.05,
        "avg_bandwidth_kbps": 10,
        "packet_size_range": (100, 500),
        "burst_interval_sec": 15,
        "iperf_args": "-t {duration} -b 10K -l 256",
    },
    DeviceType.SMART_LIGHT: {
        "description": "Small TCP control commands, periodic status updates",
        "tcp_ratio": 0.7,
        "udp_ratio": 0.3,
        "avg_bandwidth_kbps": 8,
        "packet_size_range": (50, 300),
        "burst_interval_sec": 10,
        "iperf_args": "-t {duration} -b 8K -l 150",
    },
    DeviceType.MOTION_SENSOR: {
        "description": "Event-driven UDP bursts when motion detected",
        "tcp_ratio": 0.2,
        "udp_ratio": 0.8,
        "avg_bandwidth_kbps": 20,
        "packet_size_range": (100, 400),
        "burst_interval_sec": 8,
        "iperf_args": "-u -t {duration} -b 20K -l 200",
    },
}


class TrafficGenerator:
    """
    Generates actual network traffic using iPerf3 running inside device namespaces.

    For each device pair, spawns:
    - An iPerf3 server in the destination namespace
    - An iPerf3 client in the source namespace
    """

    def __init__(self):
        self._wsl_distro = settings.wsl_distro
        self._active_generators: Dict[str, asyncio.Task] = {}

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
            raise RuntimeError(f"Traffic gen failed: {stderr.decode().strip()}")
        return stdout.decode().strip()

    async def generate(
        self,
        device_id: Optional[str],
        duration_seconds: int,
        traffic_type: str,
        db: AsyncSession,
    ) -> dict:
        """
        Generate traffic from a device (or all devices).

        Starts iPerf3 server on the bridge and clients in each device namespace.
        """
        from services.device_manager import device_manager

        running = device_manager.get_running_devices()
        if not running:
            return {"error": "No running devices."}

        if device_id:
            if device_id not in running:
                return {"error": "Specified device is not running."}
            device_ids = [device_id]
        else:
            device_ids = list(running.keys())

        # Start iPerf3 server on the bridge namespace (host side)
        server_port = 5201
        await self._run_wsl(
            f"pkill -f 'iperf3 -s' 2>/dev/null; "
            f"iperf3 -s -D -p {server_port} --one-off",
            check=False,
        )

        bridge_ipv6 = "fd00:a101::1"
        results = []

        for did in device_ids:
            info = running[did]
            ns_name = info["ns_name"]

            # Get device type for traffic profile
            dev_result = await db.execute(select(Device).where(Device.id == did))
            device = dev_result.scalar_one_or_none()
            if not device:
                continue

            profile = TRAFFIC_PROFILES.get(device.device_type)
            if not profile:
                continue

            iperf_args = profile["iperf_args"].format(duration=duration_seconds)

            # Apply traffic_type modifications
            if traffic_type == "heavy":
                iperf_args = iperf_args.replace("-b ", "-b ").replace(
                    "K", "0K"  # 10x bandwidth
                ).replace("M", "0M")
            elif traffic_type == "burst":
                iperf_args += " --bidir"
            elif traffic_type == "periodic":
                iperf_args += f" -i 1"

            try:
                # Run iPerf3 client in the device namespace
                task_key = f"traffic-{did}"
                cmd = (
                    f"ip netns exec {ns_name} "
                    f"iperf3 -c {bridge_ipv6} -p {server_port} {iperf_args} "
                    f"--json 2>/dev/null || echo '{{\"error\": \"iperf3 failed\"}}'"
                )

                # Run asynchronously
                task = asyncio.create_task(self._run_traffic_task(cmd, did, device.name))
                self._active_generators[task_key] = task

                results.append({
                    "device_id": did,
                    "device_name": device.name,
                    "status": "traffic_started",
                    "traffic_type": traffic_type,
                    "duration": duration_seconds,
                    "profile": profile["description"],
                })

                # Stagger starts slightly
                await asyncio.sleep(0.2)

            except Exception as e:
                results.append({
                    "device_id": did,
                    "device_name": device.name,
                    "error": str(e),
                })

        return {
            "traffic_sessions": len(results),
            "devices": results,
        }

    async def _run_traffic_task(self, command: str, device_id: str, device_name: str):
        """Background task to run traffic generation."""
        try:
            output = await self._run_wsl(command, check=False)
            logger.info(f"Traffic generation completed for {device_name}")

            # Try to parse iPerf3 JSON output
            try:
                data = json.loads(output)
                if "end" in data:
                    summary = data["end"].get("sum_sent", data["end"].get("sum", {}))
                    logger.info(
                        f"  {device_name}: "
                        f"{summary.get('bytes', 0)} bytes, "
                        f"{summary.get('bits_per_second', 0)/1000:.1f} Kbps"
                    )
            except (json.JSONDecodeError, KeyError):
                pass

        except Exception as e:
            logger.error(f"Traffic task error for {device_name}: {e}")
        finally:
            task_key = f"traffic-{device_id}"
            self._active_generators.pop(task_key, None)

    async def generate_anomalous_traffic(
        self,
        device_id: str,
        anomaly_type: str,
        duration_seconds: int = 10,
    ) -> dict:
        """
        Generate anomalous/attack-like traffic for security testing.

        Anomaly types:
        - flood: High-bandwidth flood
        - port_scan: Rapid connections to sequential ports
        - unusual_outbound: Large outbound data transfer
        """
        from services.device_manager import device_manager

        running = device_manager.get_running_devices()
        if device_id not in running:
            return {"error": "Device not running."}

        ns_name = running[device_id]["ns_name"]
        bridge_ipv6 = "fd00:a101::1"

        if anomaly_type == "flood":
            cmd = (
                f"ip netns exec {ns_name} "
                f"iperf3 -c {bridge_ipv6} -u -b 100M -t {duration_seconds} "
                f"--json 2>/dev/null"
            )
        elif anomaly_type == "port_scan":
            # Simulate port scanning using ncat/bash
            cmd = (
                f"ip netns exec {ns_name} bash -c '"
                f"for port in $(seq 1 100); do "
                f"(echo scan | nc -6 -w 1 {bridge_ipv6} $port) 2>/dev/null & "
                f"done; wait'"
            )
        elif anomaly_type == "unusual_outbound":
            cmd = (
                f"ip netns exec {ns_name} "
                f"iperf3 -c {bridge_ipv6} -t {duration_seconds} -b 50M -R "
                f"--json 2>/dev/null"
            )
        else:
            return {"error": f"Unknown anomaly type: {anomaly_type}"}

        try:
            task = asyncio.create_task(self._run_wsl(cmd, check=False))
            return {
                "status": "anomalous_traffic_started",
                "device_id": device_id,
                "anomaly_type": anomaly_type,
                "duration": duration_seconds,
            }
        except Exception as e:
            return {"error": str(e)}

    async def stop_all_traffic(self):
        """Cancel all active traffic generation tasks."""
        for key, task in self._active_generators.items():
            task.cancel()
        self._active_generators.clear()

        # Kill any lingering iPerf3 processes
        await self._run_wsl("pkill -f iperf3 2>/dev/null", check=False)


# Singleton instance
traffic_generator = TrafficGenerator()
