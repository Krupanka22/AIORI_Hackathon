"""
AIORI - Device Management API
CRUD operations and lifecycle controls for virtual IoT devices.
"""

from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db, Device, DeviceProfile, DeviceType, DeviceStatus
from services.device_manager import device_manager

router = APIRouter()


# --- Pydantic Schemas ---

class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    device_type: DeviceType
    traffic_config: Optional[dict] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    traffic_config: Optional[dict] = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    device_type: DeviceType
    status: DeviceStatus
    profile_id: Optional[str] = None
    current_ipv6: Optional[str] = None
    network_interface: Optional[str] = None
    namespace_name: Optional[str] = None
    traffic_config: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceListResponse(BaseModel):
    devices: List[DeviceResponse]
    total: int


class DeviceAction(BaseModel):
    action: str = Field(..., pattern="^(start|stop|restart)$")


# --- Endpoints ---

@router.get("/", response_model=DeviceListResponse)
async def list_devices(db: AsyncSession = Depends(get_db)):
    """List all virtual IoT devices."""
    result = await db.execute(select(Device).order_by(Device.created_at))
    devices = result.scalars().all()
    return DeviceListResponse(
        devices=[DeviceResponse.model_validate(d) for d in devices],
        total=len(devices),
    )


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceCreate, db: AsyncSession = Depends(get_db)):
    """Create a new virtual IoT device."""
    # Check for duplicate name
    existing = await db.execute(select(Device).where(Device.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Device with name '{payload.name}' already exists.",
        )

    device = Device(
        name=payload.name,
        device_type=payload.device_type,
        traffic_config=payload.traffic_config,
    )
    db.add(device)
    await db.flush()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific device by ID."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")
    return DeviceResponse.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    payload: DeviceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update device properties."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    if payload.name is not None:
        device.name = payload.name
    if payload.traffic_config is not None:
        device.traffic_config = payload.traffic_config
    device.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a virtual device."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    # Stop device if running
    if device.status == DeviceStatus.RUNNING:
        await device_manager.stop_device(device_id)

    await db.delete(device)


@router.post("/{device_id}/action", response_model=DeviceResponse)
async def device_action(
    device_id: str,
    action: DeviceAction,
    db: AsyncSession = Depends(get_db),
):
    """Perform an action on a device: start, stop, or restart."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    if action.action == "start":
        try:
            result_info = await device_manager.start_device(device, db)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
    elif action.action == "stop":
        result_info = await device_manager.stop_device(device_id)
        device.status = DeviceStatus.STOPPED
    elif action.action == "restart":
        await device_manager.stop_device(device_id)
        try:
            result_info = await device_manager.start_device(device, db)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
    else:
        raise HTTPException(status_code=400, detail="Invalid action.")

    await db.flush()
    await db.refresh(device)
    return DeviceResponse.model_validate(device)


@router.get("/{device_id}/stats")
async def get_device_stats(device_id: str, db: AsyncSession = Depends(get_db)):
    """Get traffic statistics for a device."""
    from database import TrafficStats

    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found.")

    stats_result = await db.execute(
        select(TrafficStats)
        .where(TrafficStats.device_id == device_id)
        .order_by(TrafficStats.window_start.desc())
        .limit(100)
    )
    stats = stats_result.scalars().all()

    return {
        "device_id": device_id,
        "device_name": device.name,
        "stats_count": len(stats),
        "stats": [
            {
                "window_start": s.window_start.isoformat(),
                "window_end": s.window_end.isoformat(),
                "total_packets": s.total_packets,
                "total_bytes": s.total_bytes,
                "avg_packet_size": s.avg_packet_size,
                "packet_frequency": s.packet_frequency,
                "upload_download_ratio": s.upload_download_ratio,
                "tcp_udp_ratio": s.tcp_udp_ratio,
                "unique_destinations": s.unique_destinations,
            }
            for s in stats
        ],
    }
