"""
AIORI - Security Alerts API
Endpoints for security alerts and anomaly notifications.
"""

from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, SecurityAlert, AlertSeverity

router = APIRouter()


class AlertResponse(BaseModel):
    id: int
    profile_id: Optional[str] = None
    device_id: Optional[str] = None
    current_ipv6: Optional[str] = None
    severity: AlertSeverity
    category: str
    anomaly_score: Optional[float] = None
    observed_value: Optional[str] = None
    expected_baseline: Optional[str] = None
    explanation: str
    is_acknowledged: bool
    detected_at: datetime

    class Config:
        from_attributes = True


class AlertSummary(BaseModel):
    total: int
    critical: int
    high: int
    medium: int
    low: int
    unacknowledged: int


@router.get("/", response_model=List[AlertResponse])
async def list_alerts(
    severity: Optional[AlertSeverity] = None,
    acknowledged: Optional[bool] = None,
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List security alerts with optional filtering."""
    query = select(SecurityAlert).order_by(desc(SecurityAlert.detected_at))

    if severity:
        query = query.where(SecurityAlert.severity == severity)
    if acknowledged is not None:
        query = query.where(SecurityAlert.is_acknowledged == acknowledged)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    alerts = result.scalars().all()
    return [AlertResponse.model_validate(a) for a in alerts]


@router.get("/summary", response_model=AlertSummary)
async def alert_summary(db: AsyncSession = Depends(get_db)):
    """Get alert count summary by severity."""
    total_result = await db.execute(select(func.count(SecurityAlert.id)))
    total = total_result.scalar() or 0

    severity_counts = {}
    for sev in AlertSeverity:
        result = await db.execute(
            select(func.count(SecurityAlert.id)).where(
                SecurityAlert.severity == sev
            )
        )
        severity_counts[sev.value] = result.scalar() or 0

    unack_result = await db.execute(
        select(func.count(SecurityAlert.id)).where(
            SecurityAlert.is_acknowledged == False
        )
    )
    unacknowledged = unack_result.scalar() or 0

    return AlertSummary(
        total=total,
        critical=severity_counts.get("critical", 0),
        high=severity_counts.get("high", 0),
        medium=severity_counts.get("medium", 0),
        low=severity_counts.get("low", 0),
        unacknowledged=unacknowledged,
    )


@router.patch("/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Acknowledge a security alert."""
    result = await db.execute(
        select(SecurityAlert).where(SecurityAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    alert.is_acknowledged = True
    await db.flush()
    return {"message": "Alert acknowledged.", "alert_id": alert_id}


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific alert by ID."""
    result = await db.execute(
        select(SecurityAlert).where(SecurityAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return AlertResponse.model_validate(alert)
