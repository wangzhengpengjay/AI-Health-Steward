"""Health metric endpoints: manual entry and history queries."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.utils import compute_age as _age
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

    # Normalize aliases and reject unknown metric names. Previously any string
    # was accepted, so a typo (e.g. "systolic_bp") was stored as a row that has
    # no reference range, is never flagged abnormal, and never appears in any
    # trend chart — silently unmonitored health data.
    #
    # The accepted set is the UI's fixed tabs PLUS every metric the backend can
    # actually evaluate (blood lipids have reference ranges but no input tab).
    from app.core.reference_ranges import known_metric_names
    from app.services.extraction_rules import ALLOWED_METRIC_NAMES, METRIC_NAME_ALIASES

    accepted = set(ALLOWED_METRIC_NAMES) | known_metric_names()
    metric_name = data.get("metric_name", "")
    metric_name = METRIC_NAME_ALIASES.get(metric_name, metric_name)
    if metric_name not in accepted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"不支持的指标名称：{metric_name}。"
                f"可选：{', '.join(sorted(accepted))}"
            ),
        )
    data["metric_name"] = metric_name
    value = data.get("value")
    age = _age(member.birth_date)

    # 服务端统一计算参考范围与异常/危急标记：不信任客户端传入的
    # is_abnormal / is_critical，并且单侧参考范围也能正确判定（P0）。
    from app.core.reference_ranges import evaluate_metric

    lo, hi, abnormal, critical = evaluate_metric(
        metric_name,
        float(value),
        age,
        explicit_lower=data.get("reference_lower"),
        explicit_upper=data.get("reference_upper"),
    )
    data["reference_lower"] = lo
    data["reference_upper"] = hi
    data["is_abnormal"] = abnormal
    data["is_critical"] = critical

    metric = MetricRecord(member_id=member_id, **data)
    db.add(metric)
    await db.flush()
    await db.refresh(metric)

    # 功能①: 异常/危急指标自动生成复测/就医待办
    try:
        from app.services import task_service
        await task_service.handle_metric_recorded(
            db, member_id, metric.metric_name,
            metric.is_abnormal, metric.is_critical, metric.id,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("task generation failed for metric %s", metric.id)
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
    # Recompute abnormal/critical from the *effective* value and bounds, using
    # the same server-side rules as create_metric so the two paths can never
    # disagree. Guard against an explicit null value (optional in the schema)
    # which previously reached the comparison and raised TypeError -> 500.
    new_value = data.get("value")
    if new_value is None:
        new_value = metric.value
        data.pop("value", None)
    new_lower = data.get("reference_lower", metric.reference_lower)
    new_upper = data.get("reference_upper", metric.reference_upper)
    if new_value is not None:
        from app.core.reference_ranges import evaluate_metric, plausible_range_error

        # The payload has no metric_name, so validate against the stored one.
        error = plausible_range_error(metric.metric_name, float(new_value))
        if error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error
            )
        member = await db.get(FamilyMember, metric.member_id)
        age = _age(member.birth_date) if member else None
        lo, hi, abnormal, critical = evaluate_metric(
            metric.metric_name, float(new_value), age, new_lower, new_upper
        )
        data["reference_lower"] = lo
        data["reference_upper"] = hi
        data["is_abnormal"] = abnormal
        data["is_critical"] = critical
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
