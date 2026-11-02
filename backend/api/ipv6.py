"""
AIORI - IPv6 Address History API
Endpoints for IPv6 address tracking and rotation history.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, IPv6AddressRecord, AddressAssociation, DeviceProfile

router = APIRouter()


class IPv6RecordResponse(BaseModel):
    id: int
    device_id: str
    ipv6_address: str
    address_type: str
    assigned_at: datetime
    expired_at: Optional[datetime] = None
    is_current: bool

    class Config:
        from_attributes = True


class AddressAssociationResponse(BaseModel):
    id: int
    profile_id: str
    ipv6_address: str
    similarity_score: float
    confidence: float
    resolution_method: str
    resolved_at: datetime
    is_verified: bool

    class Config:
        from_attributes = True


class ProfileAddressHistory(BaseModel):
    profile_id: str
    label: Optional[str] = None
    device_type_prediction: Optional[str] = None
    total_addresses: int
    associations: List[AddressAssociationResponse]


@router.get("/history", response_model=List[IPv6RecordResponse])
async def get_ipv6_history(
    device_id: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get IPv6 address history, optionally filtered by device."""
    query = select(IPv6AddressRecord).order_by(desc(IPv6AddressRecord.assigned_at))
    if device_id:
        query = query.where(IPv6AddressRecord.device_id == device_id)
    query = query.limit(limit)

    result = await db.execute(query)
    records = result.scalars().all()
    return [IPv6RecordResponse.model_validate(r) for r in records]


@router.get("/rotations")
async def get_rotation_events(
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get IPv6 rotation events (address changes)."""
    result = await db.execute(
        select(IPv6AddressRecord)
        .where(IPv6AddressRecord.expired_at.isnot(None))
        .order_by(desc(IPv6AddressRecord.expired_at))
        .limit(limit)
    )
    records = result.scalars().all()
    return [
        {
            "device_id": r.device_id,
            "old_address": r.ipv6_address,
            "address_type": r.address_type,
            "assigned_at": r.assigned_at.isoformat(),
            "expired_at": r.expired_at.isoformat() if r.expired_at else None,
        }
        for r in records
    ]


@router.get("/profiles/{profile_id}/addresses", response_model=ProfileAddressHistory)
async def get_profile_address_history(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all IPv6 addresses associated with a behavioral profile."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    assoc_result = await db.execute(
        select(AddressAssociation)
        .where(AddressAssociation.profile_id == profile_id)
        .order_by(desc(AddressAssociation.resolved_at))
    )
    associations = assoc_result.scalars().all()

    return ProfileAddressHistory(
        profile_id=profile.id,
        label=profile.label,
        device_type_prediction=(
            profile.device_type_prediction.value
            if profile.device_type_prediction
            else None
        ),
        total_addresses=profile.total_addresses,
        associations=[
            AddressAssociationResponse.model_validate(a) for a in associations
        ],
    )


@router.get("/rotation-count")
async def rotation_count(db: AsyncSession = Depends(get_db)):
    """Get total number of IPv6 rotations detected."""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(IPv6AddressRecord.id)).where(
            IPv6AddressRecord.expired_at.isnot(None)
        )
    )
    count = result.scalar()
    return {"total_rotations": count or 0}
