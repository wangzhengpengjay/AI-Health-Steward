"""Health metric endpoints: manual entry and history queries."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import MetricRecord
from app.schemas.health import MetricRecordCreate, MetricRecordResponse

router = APIRouter(prefix="/members", tags=["metrics"])


@router.post(
    "/{member_id}/metrics",
    response_model=MetricRecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_metric(
    member_id: int,
    payload: MetricRecordCreate,
    db: AsyncSession = Depends(get_db),
) -> MetricRecord:
    await _ensure_member(db, member_id)
    # Force manual source on this endpoint
    data = payload.model_dump()
    data["source_type"] = "manual"
    metric = MetricRecord(member_id=member_id, **data)
    db.add(metric)
    await db.flush()
    await db.refresh(metric)
    return metric


@router.get("/{member_id}/metrics", response_model=List[MetricRecordResponse])
async def list_metrics(
    member_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[MetricRecord]:
    await _ensure_member(db, member_id)
    result = await db.execute(
        select(MetricRecord)
        .where(MetricRecord.member_id == member_id)
        .order_by(MetricRecord.measured_at.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/{member_id}/metrics/{metric_name}",
    response_model=List[MetricRecordResponse],
)
async def get_metric_history(
    member_id: int,
    metric_name: str,
    db: AsyncSession = Depends(get_db),
) -> List[MetricRecord]:
    await _ensure_member(db, member_id)
    result = await db.execute(
        select(MetricRecord)
        .where(
            MetricRecord.member_id == member_id,
            MetricRecord.metric_name == metric_name,
        )
        .order_by(MetricRecord.measured_at.desc())
    )
    return list(result.scalars().all())


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    result = await db.execute(
        select(FamilyMember.id).where(
            FamilyMember.id == member_id,
            FamilyMember.is_deleted.is_(False),
        )
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FamilyMember {member_id} not found",
        )
