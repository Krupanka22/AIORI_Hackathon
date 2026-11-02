"""
AIORI - Blockchain Audit API
Endpoints for blockchain-based identity audit records.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, BlockchainRecord

router = APIRouter()


class BlockchainRecordResponse(BaseModel):
    id: int
    profile_id: str
    ipv6_address: Optional[str] = None
    event_type: str
    fingerprint_digest: Optional[str] = None
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    is_verified: bool
    recorded_at: datetime

    class Config:
        from_attributes = True


@router.get("/records", response_model=List[BlockchainRecordResponse])
async def list_blockchain_records(
    profile_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List blockchain audit records."""
    query = select(BlockchainRecord).order_by(desc(BlockchainRecord.recorded_at))

    if profile_id:
        query = query.where(BlockchainRecord.profile_id == profile_id)
    if event_type:
        query = query.where(BlockchainRecord.event_type == event_type)

    query = query.limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()
    return [BlockchainRecordResponse.model_validate(r) for r in records]


@router.get("/records/{record_id}", response_model=BlockchainRecordResponse)
async def get_blockchain_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific blockchain record."""
    result = await db.execute(
        select(BlockchainRecord).where(BlockchainRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")
    return BlockchainRecordResponse.model_validate(record)


@router.post("/verify/{record_id}")
async def verify_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """Verify a blockchain record against the ledger."""
    from config import settings

    result = await db.execute(
        select(BlockchainRecord).where(BlockchainRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found.")

    from services.blockchain_service import blockchain_service

    verification = await blockchain_service.verify_record(record)
    return verification


@router.get("/status")
async def blockchain_status():
    """Get blockchain integration status."""
    from config import settings

    return {
        "enabled": settings.blockchain_enabled,
        "network": settings.hlf_channel_name if settings.blockchain_enabled else None,
        "chaincode": (
            settings.hlf_chaincode_name if settings.blockchain_enabled else None
        ),
        "status": "active" if settings.blockchain_enabled else "disabled",
    }
