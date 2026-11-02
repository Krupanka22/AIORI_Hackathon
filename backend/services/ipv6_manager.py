"""
AIORI - IPv6 Address Manager
Handles IPv6 address assignment, privacy extensions, and controlled rotation.
"""

import asyncio
import os
import random
import subprocess
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import Device, IPv6AddressRecord, DeviceStatus


class IPv6Manager:
    """
    Manages IPv6 addressing for virtual IoT devices.

    In the WSL2 environment, we use ULA (Unique Local Address) prefix fd00:a101::/64.
    Privacy-extension-style rotation is implemented by periodically reassigning
    addresses from within the ULA prefix with randomized interface identifiers.
    """

    ULA_PREFIX = "fd00:a101::"

    def __init__(self):
        self._wsl_distro = settings.wsl_distro

    async def _run_wsl(self, command: str, check: bool = True):
        """Execute a Linux networking command in WSL or from Windows."""
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
            raise RuntimeError(f"WSL command failed: {stderr.decode().strip()}")
        return stdout.decode().strip()

    def _generate_privacy_address(self) -> str:
        """Generate a random IPv6 interface identifier (simulating privacy extensions)."""
        iid = ":".join(
            f"{random.randint(0, 0xFFFF):04x}" for _ in range(4)
        )
        return f"{self.ULA_PREFIX.rstrip(':')}:{iid}"

    async def trigger_rotation(
        self,
        device_id: Optional[str],
        db: AsyncSession,
    ) -> dict:
        """
        Trigger IPv6 address rotation for one or all devices.

        Steps:
        1. Generate a new random IPv6 address in the ULA prefix.
        2. Assign the new address to the device's namespace interface.
        3. Remove the old address.
        4. Update database records.
        5. Broadcast the rotation event.
        """
        from services.device_manager import device_manager

        if device_id:
            devices_to_rotate = []
            result = await db.execute(
                select(Device).where(Device.id == device_id)
            )
            device = result.scalar_one_or_none()
            if device and device.status == DeviceStatus.RUNNING:
                devices_to_rotate.append(device)
            else:
                return {"error": "Device not found or not running."}
        else:
            # Rotate all running devices
            result = await db.execute(
                select(Device).where(Device.status == DeviceStatus.RUNNING)
            )
            devices_to_rotate = list(result.scalars().all())

        rotated = []

        for device in devices_to_rotate:
            if not device_manager.is_running(device.id):
                continue

            old_ipv6 = device.current_ipv6
            new_ipv6 = self._generate_privacy_address()
            ns_name = device.namespace_name
            iface = device.network_interface or "eth0"

            try:
                # Add new address
                await self._run_wsl(
                    f"ip netns exec {ns_name} ip -6 addr add {new_ipv6}/64 dev {iface}",
                )

                # Wait briefly for address to be usable
                await asyncio.sleep(0.5)

                # Remove old address
                if old_ipv6:
                    await self._run_wsl(
                        f"ip netns exec {ns_name} ip -6 addr del {old_ipv6}/64 dev {iface}",
                        check=False,
                    )

                # Update database: expire old record
                now = datetime.now(timezone.utc)
                await db.execute(
                    update(IPv6AddressRecord)
                    .where(IPv6AddressRecord.device_id == device.id)
                    .where(IPv6AddressRecord.is_current == True)
                    .values(is_current=False, expired_at=now)
                )

                # Create new record
                new_record = IPv6AddressRecord(
                    device_id=device.id,
                    ipv6_address=new_ipv6,
                    address_type="privacy_rotation",
                    is_current=True,
                )
                db.add(new_record)

                # Update device
                device.current_ipv6 = new_ipv6
                device.updated_at = now

                # Update running device info
                device_manager._running_devices[device.id]["ipv6_addr"] = new_ipv6

                await db.flush()

                # Broadcast event
                from api.websocket import broadcast_ipv6_rotation
                await broadcast_ipv6_rotation(device.id, old_ipv6, new_ipv6)

                rotated.append({
                    "device_id": device.id,
                    "device_name": device.name,
                    "old_ipv6": old_ipv6,
                    "new_ipv6": new_ipv6,
                    "timestamp": now.isoformat(),
                })

                logger.info(
                    f"IPv6 rotation for {device.name}: {old_ipv6} -> {new_ipv6}"
                )

            except Exception as e:
                logger.error(f"Rotation failed for {device.name}: {e}")
                rotated.append({
                    "device_id": device.id,
                    "device_name": device.name,
                    "error": str(e),
                })

        return {
            "rotated_count": len([r for r in rotated if "error" not in r]),
            "devices": rotated,
        }

    async def get_current_addresses(self, ns_name: str) -> list:
        """Get all current IPv6 addresses from a namespace interface."""
        try:
            output = await self._run_wsl(
                f"ip netns exec {ns_name} ip -6 addr show dev eth0 scope global"
                " | grep inet6 | awk '{{print $2}}'",
                check=False,
            )
            return [addr.split("/")[0] for addr in output.splitlines() if addr]
        except Exception:
            return []


# Singleton instance
ipv6_manager = IPv6Manager()
