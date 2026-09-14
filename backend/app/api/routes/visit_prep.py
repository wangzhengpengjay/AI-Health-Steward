"""Visit preparation API routes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_auth
from app.providers.router import ModelRouter, get_model_router
from app.services.visit_prep import generate_visit_prep, suggest_dept

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/members", tags=["visit-prep"], dependencies=[Depends(require_auth)])


class SuggestDeptRequest(BaseModel):
    chief_complaint: str


class SuggestDeptResponse(BaseModel):
    department: str | None
    reason: str


class VisitPrepRequest(BaseModel):
    chief_complaint: str
    department: str
    selected_metrics: list[str] = []


class VisitPrepChecklistItem(BaseModel):
    item: str
    count: int = 0
    required: bool = False


class MetricTrendRecord(BaseModel):
    date: str
    value: float


class MetricTrend(BaseModel):
    metric_name: str
    label: str
    unit: str
    records: list[MetricTrendRecord]
    reference_lower: float | None = None
    reference_upper: float | None = None
    trend: str
    latest_value: float
    is_abnormal: bool


class VisitPrepResponse(BaseModel):
    department: str
    chief_complaint: str
    questions: list[str]
    checklist: list[VisitPrepChecklistItem]
    summary: str
    metrics_trend: list[MetricTrend]


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    """404 for missing / soft-deleted members instead of a 500 from deeper layers."""
    from app.models.family import FamilyMember

    member = await db.get(FamilyMember, member_id)
    if member is None or member.is_deleted:
        raise HTTPException(status_code=404, detail="成员不存在")


@router.post("/{member_id}/visit-prep/suggest-department", response_model=SuggestDeptResponse)
async def suggest_department(
    member_id: int,
    body: SuggestDeptRequest,
    db: AsyncSession = Depends(get_db),
) -> SuggestDeptResponse:
    """Suggest a clinical department based on chief complaint + diagnosis history."""
    await _ensure_member(db, member_id)
    result = await suggest_dept(db, member_id, body.chief_complaint)
    return SuggestDeptResponse(**result)


@router.post("/{member_id}/visit-prep", response_model=VisitPrepResponse)
async def create_visit_prep(
    member_id: int,
    body: VisitPrepRequest,
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> VisitPrepResponse:
    """Generate structured pre-visit guidance. Results are NOT persisted."""
    await _ensure_member(db, member_id)
    result = await generate_visit_prep(
        db=db,
        router=model_router,
        member_id=member_id,
        chief_complaint=body.chief_complaint,
        department=body.department,
        selected_metrics=body.selected_metrics,
    )
    return VisitPrepResponse(**result)
