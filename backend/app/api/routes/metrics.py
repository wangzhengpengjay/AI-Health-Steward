"""Health metric endpoints: manual entry and history queries."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import MetricRecord
from app.schemas.health import MetricRecordCreate, MetricRecordResponse, MetricRecordUpdate

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
    member = await _ensure_member(db, member_id)
    # Force manual source on this endpoint
    data = payload.model_dump()
    data["source_type"] = "manual"

    # P0-2: 调用方未提供参考范围时，按成员年龄自动填充成人/儿童默认值
    if data.get("reference_lower") is None and data.get("reference_upper") is None:
        from app.core.reference_ranges import resolve_reference_range
        lo, hi = resolve_reference_range(data.get("metric_name", ""), _age(member.birth_date))
        data["reference_lower"] = lo
        data["reference_upper"] = hi

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



@router.put(
    "/metrics/{metric_id}",
    response_model=MetricRecordResponse,
)
async def update_metric(
    metric_id: int,
    payload: MetricRecordUpdate,
    db: AsyncSession = Depends(get_db),
) -> MetricRecord:
    result = await db.execute(
        select(MetricRecord).where(MetricRecord.id == metric_id)
    )
    metric = result.scalars().first()
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MetricRecord {metric_id} not found",
        )
    data = payload.model_dump(exclude_unset=True)
    # Re-compute abnormal/critical if value or references changed
    new_value = data.get("value", metric.value)
    new_lower = data.get("reference_lower", metric.reference_lower)
    new_upper = data.get("reference_upper", metric.reference_upper)
    if new_lower is not None and new_upper is not None:
        data["is_abnormal"] = not (new_lower <= new_value <= new_upper)
        data["is_critical"] = bool(
            data["is_abnormal"]
            and (new_value < new_lower * 0.5 or new_value > new_upper * 1.5)
        )
    for key, val in data.items():
        setattr(metric, key, val)
    await db.flush()
    await db.refresh(metric)
    return metric


@router.delete(
    "/metrics/{metric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_metric(
    metric_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MetricRecord).where(MetricRecord.id == metric_id)
    )
    metric = result.scalars().first()
    if metric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MetricRecord {metric_id} not found",
        )
    await db.delete(metric)


async def _ensure_member(db: AsyncSession, member_id: int) -> FamilyMember:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.is_deleted.is_(False),
        )
    )
    member = result.scalars().first()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FamilyMember {member_id} not found",
        )
    return member


def _age(birth_date) -> int | None:
    """Compute age in years from birth_date (may be date or None)."""
    if not birth_date:
        return None
    from datetime import date
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
