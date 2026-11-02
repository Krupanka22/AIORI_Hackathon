"""
AIORI - AI Analysis API
Endpoints for behavioral fingerprinting, similarity matching, and identity resolution.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, DeviceProfile, AddressAssociation, TrafficStats

router = APIRouter()


class ProfileResponse(BaseModel):
    id: str
    label: Optional[str] = None
    device_type_prediction: Optional[str] = None
    fingerprint: Optional[dict] = None
    baseline_features: Optional[dict] = None
    confidence: float
    first_seen: datetime
    last_seen: datetime
    total_addresses: int
    is_active: bool

    class Config:
        from_attributes = True


class IdentityResolutionRequest(BaseModel):
    ipv6_address: str
    force: bool = False


class IdentityResolutionResponse(BaseModel):
    ipv6_address: str
    matched_profile_id: Optional[str] = None
    similarity_score: float
    confidence: float
    is_new_profile: bool
    resolution_method: str


class SimilarityResult(BaseModel):
    profile_id: str
    label: Optional[str] = None
    similarity_score: float
    confidence: float


@router.get("/profiles", response_model=List[ProfileResponse])
async def list_profiles(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """List all behavioral device profiles."""
    query = select(DeviceProfile).order_by(desc(DeviceProfile.last_seen))
    if active_only:
        query = query.where(DeviceProfile.is_active == True)

    result = await db.execute(query)
    profiles = result.scalars().all()

    return [
        ProfileResponse(
            id=p.id,
            label=p.label,
            device_type_prediction=(
                p.device_type_prediction.value if p.device_type_prediction else None
            ),
            fingerprint=p.fingerprint,
            baseline_features=p.baseline_features,
            confidence=p.confidence,
            first_seen=p.first_seen,
            last_seen=p.last_seen,
            total_addresses=p.total_addresses,
            is_active=p.is_active,
        )
        for p in profiles
    ]


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific behavioral profile."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    return ProfileResponse(
        id=profile.id,
        label=profile.label,
        device_type_prediction=(
            profile.device_type_prediction.value
            if profile.device_type_prediction
            else None
        ),
        fingerprint=profile.fingerprint,
        baseline_features=profile.baseline_features,
        confidence=profile.confidence,
        first_seen=profile.first_seen,
        last_seen=profile.last_seen,
        total_addresses=profile.total_addresses,
        is_active=profile.is_active,
    )


@router.post("/resolve", response_model=IdentityResolutionResponse)
async def resolve_identity(
    request: IdentityResolutionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Attempt to resolve the identity of a device at a given IPv6 address.
    Compares behavioral features against existing profiles.
    """
    from services.identity_resolver import identity_resolver

    result = await identity_resolver.resolve(request.ipv6_address, db, force=request.force)
    return IdentityResolutionResponse(**result)


@router.get("/similarity/{profile_id}", response_model=List[SimilarityResult])
async def get_similar_profiles(
    profile_id: str,
    threshold: float = Query(0.5, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """Get profiles similar to the given profile based on behavioral fingerprints."""
    from services.ai_fingerprint import fingerprint_engine

    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    similarities = await fingerprint_engine.find_similar_profiles(
        profile, threshold, db
    )
    return [SimilarityResult(**s) for s in similarities]


@router.get("/features/{device_id}")
async def get_device_features(
    device_id: str,
    window_seconds: int = Query(30),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get extracted behavioral features for a device."""
    result = await db.execute(
        select(TrafficStats)
        .where(TrafficStats.device_id == device_id)
        .where(TrafficStats.window_seconds == window_seconds)
        .order_by(desc(TrafficStats.window_start))
        .limit(limit)
    )
    stats = result.scalars().all()
    return {
        "device_id": device_id,
        "window_seconds": window_seconds,
        "feature_count": len(stats),
        "features": [
            {
                "window_start": s.window_start.isoformat(),
                "window_end": s.window_end.isoformat(),
                "avg_packet_size": s.avg_packet_size,
                "avg_inter_arrival_time": s.avg_inter_arrival_time,
                "packet_frequency": s.packet_frequency,
                "upload_download_ratio": s.upload_download_ratio,
                "tcp_udp_ratio": s.tcp_udp_ratio,
                "unique_destinations": s.unique_destinations,
                "avg_connection_duration": s.avg_connection_duration,
                "periodicity_score": s.periodicity_score,
                "duty_cycle": s.duty_cycle,
            }
            for s in stats
        ],
    }
