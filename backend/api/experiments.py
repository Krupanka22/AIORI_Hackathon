"""
AIORI - Experiment Management API
Endpoints for running and managing network experiments.
"""

from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Experiment, ExperimentStatus

router = APIRouter()


class ExperimentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    experiment_type: str = Field(
        ...,
        pattern="^(normal_traffic|ipv6_rotation|anomaly_injection|attack_test|full_pipeline)$",
    )
    config: Optional[dict] = None


class ExperimentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    experiment_type: str
    status: ExperimentStatus
    config: Optional[dict] = None
    results: Optional[dict] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ExperimentAction(BaseModel):
    action: str = Field(
        ..., pattern="^(start|stop|cancel)$"
    )


@router.get("/", response_model=List[ExperimentResponse])
async def list_experiments(
    status_filter: Optional[ExperimentStatus] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List experiments with optional status filtering."""
    query = select(Experiment).order_by(desc(Experiment.created_at))
    if status_filter:
        query = query.where(Experiment.status == status_filter)
    query = query.limit(limit)

    result = await db.execute(query)
    experiments = result.scalars().all()
    return [ExperimentResponse.model_validate(e) for e in experiments]


@router.post("/", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    payload: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new experiment."""
    experiment = Experiment(
        name=payload.name,
        description=payload.description,
        experiment_type=payload.experiment_type,
        config=payload.config,
    )
    db.add(experiment)
    await db.flush()
    await db.refresh(experiment)
    return ExperimentResponse.model_validate(experiment)


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific experiment."""
    result = await db.execute(
        select(Experiment).where(Experiment.id == experiment_id)
    )
    experiment = result.scalar_one_or_none()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found.")
    return ExperimentResponse.model_validate(experiment)


@router.post("/{experiment_id}/action", response_model=ExperimentResponse)
async def experiment_action(
    experiment_id: str,
    action: ExperimentAction,
    db: AsyncSession = Depends(get_db),
):
    """Perform an action on an experiment: start, stop, or cancel."""
    result = await db.execute(
        select(Experiment).where(Experiment.id == experiment_id)
    )
    experiment = result.scalar_one_or_none()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found.")

    if action.action == "start":
        if experiment.status not in (ExperimentStatus.PENDING, ExperimentStatus.FAILED):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start experiment in {experiment.status.value} state.",
            )
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = datetime.now(timezone.utc)

        # Launch experiment in background
        from services.experiment_runner import experiment_runner
        import asyncio

        asyncio.create_task(
            experiment_runner.run_experiment(experiment_id, experiment.experiment_type, experiment.config)
        )

    elif action.action == "stop":
        if experiment.status != ExperimentStatus.RUNNING:
            raise HTTPException(
                status_code=400, detail="Experiment is not running."
            )
        from services.experiment_runner import experiment_runner

        await experiment_runner.stop_experiment(experiment_id)
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = datetime.now(timezone.utc)

    elif action.action == "cancel":
        if experiment.status == ExperimentStatus.RUNNING:
            from services.experiment_runner import experiment_runner

            await experiment_runner.stop_experiment(experiment_id)
        experiment.status = ExperimentStatus.CANCELLED

    await db.flush()
    await db.refresh(experiment)
    return ExperimentResponse.model_validate(experiment)


@router.post("/trigger-rotation")
async def trigger_ipv6_rotation(
    device_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an IPv6 address rotation for testing."""
    from services.ipv6_manager import ipv6_manager

    result = await ipv6_manager.trigger_rotation(device_id, db)
    return result


@router.post("/generate-traffic")
async def generate_traffic(
    device_id: Optional[str] = None,
    duration_seconds: int = Query(30, ge=5, le=300),
    traffic_type: str = Query("normal", pattern="^(normal|heavy|periodic|burst)$"),
    db: AsyncSession = Depends(get_db),
):
    """Generate network traffic for testing."""
    from services.traffic_generator import traffic_generator

    result = await traffic_generator.generate(
        device_id=device_id,
        duration_seconds=duration_seconds,
        traffic_type=traffic_type,
        db=db,
    )
    return result
