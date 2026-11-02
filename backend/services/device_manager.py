"""
AIORI - Device Manager Service
Manages the lifecycle of virtual IoT devices using Linux network namespaces via WSL2.

Each device is represented as a network namespace with a virtual ethernet (veth) pair
connected to a central virtual bridge (OVS or Linux bridge).
"""

import asyncio
import os
import subprocess
import json
from typing import Dict, Optional
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Device, DeviceProfile, DeviceStatus, DeviceType, IPv6AddressRecord


class DeviceManager:
    """
    Manages virtual IoT devices implemented as Linux network namespaces in WSL2.

    Architecture:
        Host (Windows) -> WSL2 (Ubuntu) -> Network Namespaces (devices)
        Each device namespace has a veth pair:
            - veth-<name> (host side, attached to bridge)
            - eth0 (namespace side, device interface)
    """

    def __init__(self):
        self._running_devices: Dict[str, dict] = {}
        self._bridge_name = "aiori-br0"
        self._bridge_initialized = False
        self._wsl_distro = settings.wsl_distro

    async def _run_wsl(self, command: str, check: bool = True) -> subprocess.CompletedProcess:
        """Execute a Linux networking command in WSL or from Windows."""
        if os.name == "nt":
            full_cmd = f"wsl.exe -d {self._wsl_distro} -- bash -lc {subprocess.list2cmdline([f'sudo {command}'])}"
        else:
            full_cmd = f"sudo {command}"
        logger.debug(f"WSL command: {command}")

        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if check and proc.returncode != 0:
            error_msg = stderr.decode().strip()
            logger.error(f"WSL command failed: {command}\n{error_msg}")
            raise RuntimeError(f"WSL command failed: {error_msg}")

        return subprocess.CompletedProcess(
            args=command,
            returncode=proc.returncode,
            stdout=stdout.decode().strip(),
            stderr=stderr.decode().strip(),
        )

    async def initialize_bridge(self):
        """Create the central bridge for device connectivity."""
        if self._bridge_initialized:
            return

        try:
            # Create bridge
            await self._run_wsl(
                f"ip link show {self._bridge_name} 2>/dev/null || "
                f"(ip link add {self._bridge_name} type bridge && "
                f"ip link set {self._bridge_name} up)",
                check=False,
            )

            # Assign an IPv6 ULA prefix to the bridge (acts as router)
            await self._run_wsl(
                f"ip -6 addr show dev {self._bridge_name} | grep -q fd00:a101::1 || "
                f"ip -6 addr add fd00:a101::1/64 dev {self._bridge_name}",
                check=False,
            )

            # Enable IPv6 forwarding
            await self._run_wsl(
                "sysctl -w net.ipv6.conf.all.forwarding=1",
                check=False,
            )

            self._bridge_initialized = True
            logger.info(f"Bridge {self._bridge_name} initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize bridge: {e}")
            raise

    async def start_device(self, device: Device, db: AsyncSession) -> dict:
        """
        Start a virtual IoT device by creating a network namespace and veth pair.
        """
        if device.id in self._running_devices:
            logger.warning(f"Device {device.name} is already running.")
            return {"status": "already_running"}

        device.status = DeviceStatus.STARTING
        await db.flush()

        safe_name = "".join(
            character if character.isalnum() or character == "-" else "-"
            for character in device.name.lower()
        ).strip("-")
        ns_name = f"aiori-{safe_name}-{device.id[:8]}"
        veth_host = f"veth-{device.id[:8]}"
        veth_ns = "eth0"
        veth_peer = f"vns-{device.id[:11]}"

        try:
            # iproute2 stores persistent namespace handles here. Some WSL2
            # images do not create the directory until explicitly requested.
            await self._run_wsl("mkdir -p /run/netns")

            await self.initialize_bridge()

            # Create network namespace
            namespace_result = await self._run_wsl(
                f"ip netns add {ns_name}",
                check=False,
            )
            if namespace_result.returncode != 0:
                raise RuntimeError(
                    f"Unable to create network namespace {ns_name}: "
                    f"{namespace_result.stderr or 'unknown ip netns error'}"
                )

            # Create veth pair
            veth_result = await self._run_wsl(
                f"ip link add {veth_host} type veth peer name {veth_peer}",
                check=False,
            )
            if veth_result.returncode != 0:
                await self._run_wsl(f"ip netns delete {ns_name}", check=False)
                raise RuntimeError(
                    f"Unable to create virtual ethernet pair: "
                    f"{veth_result.stderr or 'unknown veth error'}"
                )

            # Move one end into the namespace
            await self._run_wsl(f"ip link set {veth_peer} netns {ns_name}")
            await self._run_wsl(
                f"ip netns exec {ns_name} ip link set {veth_peer} name {veth_ns}"
            )

            # Attach host end to bridge
            await self._run_wsl(f"ip link set {veth_host} master {self._bridge_name}")
            await self._run_wsl(f"ip link set {veth_host} up")

            # Configure namespace interface
            await self._run_wsl(f"ip netns exec {ns_name} ip link set lo up")
            await self._run_wsl(f"ip netns exec {ns_name} ip link set {veth_ns} up")

            # Assign IPv6 ULA address based on device index
            device_index = len(self._running_devices) + 2
            ipv6_addr = f"fd00:a101::{device_index:x}"
            await self._run_wsl(
                f"ip netns exec {ns_name} ip -6 addr add {ipv6_addr}/64 dev {veth_ns}"
            )

            # Enable IPv6 privacy extensions for the namespace
            await self._run_wsl(
                f"ip netns exec {ns_name} sysctl -w net.ipv6.conf.{veth_ns}.use_tempaddr=2",
                check=False,
            )

            # Update device record
            device.status = DeviceStatus.RUNNING
            device.current_ipv6 = ipv6_addr
            device.network_interface = veth_ns
            device.namespace_name = ns_name

            # Record IPv6 address assignment
            addr_record = IPv6AddressRecord(
                device_id=device.id,
                ipv6_address=ipv6_addr,
                address_type="ula_manual",
                is_current=True,
            )
            db.add(addr_record)

            # Create or link a device profile if none exists
            if not device.profile_id:
                profile = DeviceProfile(
                    label=f"Profile-{device.name}",
                    device_type_prediction=device.device_type,
                )
                db.add(profile)
                await db.flush()
                device.profile_id = profile.id

                from services.blockchain_service import blockchain_service
                await blockchain_service.record_profile_created(
                    profile_id=profile.id,
                    fingerprint=profile.fingerprint,
                    db=db,
                )

            # Track the running device
            self._running_devices[device.id] = {
                "ns_name": ns_name,
                "veth_host": veth_host,
                "ipv6_addr": ipv6_addr,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

            await db.flush()

            logger.info(f"Device {device.name} started at {ipv6_addr} in namespace {ns_name}")

            # Broadcast WebSocket event
            from api.websocket import broadcast_device_update
            await broadcast_device_update(device.id, "running", {
                "name": device.name,
                "ipv6": ipv6_addr,
                "namespace": ns_name,
            })

            return {
                "status": "started",
                "namespace": ns_name,
                "ipv6_address": ipv6_addr,
            }

        except Exception as e:
            await self._run_wsl(f"ip netns delete {ns_name}", check=False)
            await self._run_wsl(f"ip link delete {veth_host}", check=False)
            device.status = DeviceStatus.ERROR
            await db.flush()
            logger.error(f"Failed to start device {device.name}: {e}")
            raise

    async def stop_device(self, device_id: str) -> dict:
        """Stop a virtual device by tearing down its namespace."""
        if device_id not in self._running_devices:
            logger.warning(f"Device {device_id} is not in running devices list.")
            return {"status": "not_running"}

        info = self._running_devices[device_id]
        ns_name = info["ns_name"]
        veth_host = info["veth_host"]

        try:
            # Delete the namespace (also removes veth pair)
            await self._run_wsl(f"ip netns delete {ns_name}", check=False)
            # Clean up host-side veth if still present
            await self._run_wsl(f"ip link delete {veth_host}", check=False)
        except Exception as e:
            logger.error(f"Error stopping device: {e}")

        del self._running_devices[device_id]

        from api.websocket import broadcast_device_update
        await broadcast_device_update(device_id, "stopped")

        logger.info(f"Device {device_id} stopped.")
        return {"status": "stopped"}

    async def stop_all(self):
        """Stop all running devices."""
        device_ids = list(self._running_devices.keys())
        for device_id in device_ids:
            await self.stop_device(device_id)

    async def ping_device(self, src_device_id: str, dst_ipv6: str, count: int = 3) -> dict:
        """Ping from one device namespace to a target IPv6 address."""
        if src_device_id not in self._running_devices:
            return {"error": "Source device not running."}

        ns_name = self._running_devices[src_device_id]["ns_name"]
        result = await self._run_wsl(
            f"ip netns exec {ns_name} ping6 -c {count} {dst_ipv6}",
            check=False,
        )
        return {
            "success": result.returncode == 0,
            "output": result.stdout,
        }

    def get_running_devices(self) -> Dict[str, dict]:
        """Get info about all currently running devices."""
        return dict(self._running_devices)

    def is_running(self, device_id: str) -> bool:
        return device_id in self._running_devices


# Singleton instance
device_manager = DeviceManager()
