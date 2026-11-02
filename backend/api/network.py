"""
AIORI - Network Monitoring API
Endpoints for connection logs, traffic data, and Zeek integration.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, ConnectionLog

router = APIRouter()


class ConnectionLogResponse(BaseModel):
    id: int
    zeek_uid: Optional[str] = None
    timestamp: datetime
    src_ipv6: str
    dst_ipv6: str
    src_port: Optional[int] = None
    dst_port: Optional[int] = None
    protocol: str
    duration: Optional[float] = None
    orig_bytes: Optional[int] = None
    resp_bytes: Optional[int] = None
    orig_pkts: Optional[int] = None
    resp_pkts: Optional[int] = None
    conn_state: Optional[str] = None
    service: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/connections", response_model=List[ConnectionLogResponse])
async def list_connections(
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    protocol: Optional[str] = None,
    src_ipv6: Optional[str] = None,
    dst_ipv6: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List recent connection log entries from Zeek monitoring."""
    query = select(ConnectionLog).order_by(desc(ConnectionLog.timestamp))

    if protocol:
        query = query.where(ConnectionLog.protocol == protocol)
    if src_ipv6:
        query = query.where(ConnectionLog.src_ipv6 == src_ipv6)
    if dst_ipv6:
        query = query.where(ConnectionLog.dst_ipv6 == dst_ipv6)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [ConnectionLogResponse.model_validate(log) for log in logs]


@router.get("/connections/count")
async def connection_count(db: AsyncSession = Depends(get_db)):
    """Get total connection count."""
    result = await db.execute(select(func.count(ConnectionLog.id)))
    count = result.scalar()
    return {"total_connections": count}


@router.get("/traffic/summary")
async def traffic_summary(db: AsyncSession = Depends(get_db)):
    """Get aggregated traffic summary statistics."""
    result = await db.execute(
        select(
            func.count(ConnectionLog.id).label("total_connections"),
            func.sum(ConnectionLog.orig_bytes).label("total_orig_bytes"),
            func.sum(ConnectionLog.resp_bytes).label("total_resp_bytes"),
            func.sum(ConnectionLog.orig_pkts).label("total_orig_pkts"),
            func.sum(ConnectionLog.resp_pkts).label("total_resp_pkts"),
        )
    )
    row = result.one()
    return {
        "total_connections": row.total_connections or 0,
        "total_orig_bytes": row.total_orig_bytes or 0,
        "total_resp_bytes": row.total_resp_bytes or 0,
        "total_orig_pkts": row.total_orig_pkts or 0,
        "total_resp_pkts": row.total_resp_pkts or 0,
    }


@router.get("/traffic/by-protocol")
async def traffic_by_protocol(db: AsyncSession = Depends(get_db)):
    """Get connection counts grouped by protocol."""
    result = await db.execute(
        select(
            ConnectionLog.protocol,
            func.count(ConnectionLog.id).label("count"),
        )
        .group_by(ConnectionLog.protocol)
        .order_by(desc("count"))
    )
    rows = result.all()
    return [{"protocol": r.protocol, "count": r.count} for r in rows]


@router.get("/traffic/by-source")
async def traffic_by_source(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get connection counts grouped by source IPv6 address."""
    result = await db.execute(
        select(
            ConnectionLog.src_ipv6,
            func.count(ConnectionLog.id).label("count"),
            func.sum(ConnectionLog.orig_bytes).label("total_bytes"),
        )
        .group_by(ConnectionLog.src_ipv6)
        .order_by(desc("count"))
        .limit(limit)
    )
    rows = result.all()
    return [
        {"src_ipv6": r.src_ipv6, "count": r.count, "total_bytes": r.total_bytes or 0}
        for r in rows
    ]
