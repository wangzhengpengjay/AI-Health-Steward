"""Health summary routes — list and generate periodic review reports."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.summaries import HealthSummary
from app.services import summary_service

router = APIRouter()


class SummaryGenerate(BaseModel):
    period: str = Field(default="monthly", description="weekly/monthly/annual")
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class SummaryOut(BaseModel):
    id: int
    member_id: int
    summary_type: str
    period: str
    period_start: date
    period_end: date
    stats_json: Optional[str]
    abnormal_events: Optional[str]
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    from app.models.family import FamilyMember
    member = await db.get(FamilyMember, member_id)
    if member is None or member.is_deleted:
        raise HTTPException(status_code=404, detail="成员不存在")


def _out(s: HealthSummary) -> SummaryOut:
    return SummaryOut.model_validate(s)


@router.get("/members/{member_id}/summaries", response_model=list[SummaryOut])
async def list_summaries(
    member_id: int,
    db: AsyncSession = Depends(get_db),
    period: Optional[str] = Query(default=None),
):
    await _ensure_member(db, member_id)
    stmt = select(HealthSummary).where(HealthSummary.member_id == member_id)
    if period:
        stmt = stmt.where(HealthSummary.period == period)
    stmt = stmt.order_by(HealthSummary.created_at.desc())
    result = await db.execute(stmt)
    return [_out(s) for s in result.scalars().all()]


@router.get("/members/{member_id}/summaries/latest", response_model=Optional[SummaryOut])
async def latest_summary(
    member_id: int,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_member(db, member_id)
    result = await db.execute(
        select(HealthSummary)
        .where(HealthSummary.member_id == member_id)
        .order_by(HealthSummary.created_at.desc())
        .limit(1)
    )
    s = result.scalars().first()
    return _out(s) if s else None


@router.post("/members/{member_id}/summaries/generate", response_model=SummaryOut, status_code=201)
async def generate_summary(
    member_id: int,
    payload: SummaryGenerate,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_member(db, member_id)
    s = await summary_service.generate_summary(
        db, member_id, payload.period, payload.period_start, payload.period_end
    )
    await db.commit()
    await db.refresh(s)
    return _out(s)
