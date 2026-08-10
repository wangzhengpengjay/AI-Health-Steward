"""Risk assessment scale routes — list scales, submit answers, view results."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import assessment_scales
from app.core.assessment_scales import get_scale
from app.core.database import get_db
from app.models.assessments import ScaleResult

router = APIRouter()


class ScaleSubmit(BaseModel):
    answers: dict[str, float] = Field(default_factory=dict)


class ScaleQuestion(BaseModel):
    id: str
    text: str
    options: list[dict]


class ScaleOut(BaseModel):
    code: str
    name: str
    description: str
    question_count: int
    trigger_keywords: list[str]
    caveat: str
    should_push: bool = False
    reason: Optional[str] = None


class ScaleResultOut(BaseModel):
    id: int
    member_id: int
    scale_code: str
    total_score: float
    risk_level: str
    risk_label: Optional[str]
    advice: Optional[str]
    interpretation: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    from app.models.family import FamilyMember
    member = await db.get(FamilyMember, member_id)
    if member is None or member.is_deleted:
        raise HTTPException(status_code=404, detail="成员不存在")


async def _recent_result(db: AsyncSession, member_id: int, scale_code: str) -> ScaleResult | None:
    result = await db.execute(
        select(ScaleResult)
        .where(ScaleResult.member_id == member_id, ScaleResult.scale_code == scale_code)
        .order_by(ScaleResult.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


def _should_push(recent: ScaleResult | None) -> tuple[bool, str | None]:
    """Frequency control: push if no recent result, or last result was not low-risk & >7 days ago."""
    if recent is None:
        return True, "尚未测评过，建议完成一次。"
    created = recent.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - created).days
    if recent.risk_level in ("low", "none"):
        if days < 180:
            return False, f"上次测评（{created.date()}）为低风险，暂无需重复。"
        return True, "距上次低风险测评已超过半年，可重新评估。"
    if days < 7:
        return False, f"上次测评（{created.date()}）已提示风险，建议 7 天后复测或咨询医生。"
    return True, "建议定期复测，跟踪风险变化。"


@router.get("/scales", response_model=list[ScaleOut])
async def list_scales(db: AsyncSession = Depends(get_db), member_id: Optional[int] = None):
    out = []
    for s in assessment_scales.list_scales():
        should_push = True
        reason = None
        if member_id is not None:
            recent = await _recent_result(db, member_id, s.code)
            should_push, reason = _should_push(recent)
        out.append(ScaleOut(
            code=s.code,
            name=s.name,
            description=s.description,
            question_count=len(s.questions),
            trigger_keywords=s.trigger_keywords,
            caveat=s.caveat,
            should_push=should_push,
            reason=reason,
        ))
    return out


@router.get("/members/{member_id}/scales/{code}", response_model=dict)
async def get_scale_questions(
    member_id: int,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_member(db, member_id)
    scale = get_scale(code)
    if scale is None:
        raise HTTPException(status_code=404, detail="量表不存在")
    recent = await _recent_result(db, member_id, code)
    should_push, reason = _should_push(recent)
    return {
        "code": scale.code,
        "name": scale.name,
        "description": scale.description,
        "questions": scale.questions,
        "scoring": scale.scoring,
        "caveat": scale.caveat,
        "should_push": should_push,
        "reason": reason,
    }


@router.post("/members/{member_id}/scales/{code}/submit", response_model=ScaleResultOut, status_code=201)
async def submit_scale(
    member_id: int,
    code: str,
    payload: ScaleSubmit,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_member(db, member_id)
    scale = get_scale(code)
    if scale is None:
        raise HTTPException(status_code=404, detail="量表不存在")

    # frequency control: block duplicate same-day submission
    recent = await _recent_result(db, member_id, code)
    if recent is not None:
        created = recent.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - created).total_seconds() < 3600 * 12:
            raise HTTPException(status_code=429, detail="今日已测评过该量表，请稍后再试")

    total, detail = scale.score(payload.answers)
    tier = detail["tier"]
    result = ScaleResult(
        member_id=member_id,
        scale_code=code,
        answers=json.dumps(payload.answers, ensure_ascii=False),
        total_score=total,
        risk_level=tier["level"],
        risk_label=tier["label"],
        advice=tier.get("advice"),
    )
    db.add(result)
    await db.flush()
    await db.refresh(result)
    await db.commit()
    await db.refresh(result)
    return ScaleResultOut.model_validate(result)


@router.get("/members/{member_id}/scales/results", response_model=list[ScaleResultOut])
async def list_results(member_id: int, db: AsyncSession = Depends(get_db)):
    await _ensure_member(db, member_id)
    result = await db.execute(
        select(ScaleResult)
        .where(ScaleResult.member_id == member_id)
        .order_by(ScaleResult.created_at.desc())
    )
    return [ScaleResultOut.model_validate(r) for r in result.scalars().all()]
