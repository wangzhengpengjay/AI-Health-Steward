"""Checkup recommendation endpoints."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import CheckupReport
from app.services.checkup_recommend import (
    build_health_profile,
    compute_completeness,
    generate_recommendation,
)

router = APIRouter(prefix="/members", tags=["checkup"])


# ---- Schemas ----

class CompletenessOut(BaseModel):
    score: int
    level: str
    missing_fields: list[str]


class ProfileCheckResponse(BaseModel):
    completeness: CompletenessOut


class SupplementRequest(BaseModel):
    region: Optional[str] = None
    occupation: Optional[str] = None
    is_pregnant: Optional[str] = None
    is_preparing_pregnancy: Optional[str] = None
    has_sexual_history: Optional[str] = None
    contrast_allergy: Optional[str] = None
    has_pacemaker: Optional[str] = None
    has_metal_implant: Optional[str] = None
    on_anticoagulant: Optional[str] = None
    claustrophobia: Optional[str] = None
    is_breastfeeding: Optional[str] = None
    has_coagulopathy: Optional[str] = None
    has_heart_failure: Optional[str] = None


class SupplementResponse(BaseModel):
    updated: bool
    completeness: CompletenessOut


class RecommendRequest(BaseModel):
    budget_tier: str = "core"  # basic / core / premium


class RecommendResponse(BaseModel):
    content: str
    completeness: CompletenessOut


# ---- Endpoints ----

@router.get("/{member_id}/checkup-profile-check", response_model=ProfileCheckResponse)
async def profile_check(member_id: int, db: AsyncSession = Depends(get_db)) -> ProfileCheckResponse:
    member = await db.get(FamilyMember, member_id)
    if not member or member.is_deleted:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")
    profile = await build_health_profile(db, member_id)
    completeness = compute_completeness(profile)
    return ProfileCheckResponse(completeness=CompletenessOut(**completeness))


@router.patch("/{member_id}/checkup-supplement", response_model=SupplementResponse)
async def supplement(
    member_id: int, payload: SupplementRequest, db: AsyncSession = Depends(get_db)
) -> SupplementResponse:
    member = await db.get(FamilyMember, member_id)
    if not member or member.is_deleted:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")

    data = payload.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(member, key, value)
    await db.flush()

    profile = await build_health_profile(db, member_id)
    completeness = compute_completeness(profile)
    return SupplementResponse(updated=True, completeness=CompletenessOut(**completeness))


@router.post("/{member_id}/checkup-recommend", response_model=RecommendResponse)
async def recommend(
    member_id: int, payload: RecommendRequest, db: AsyncSession = Depends(get_db)
) -> RecommendResponse:
    member = await db.get(FamilyMember, member_id)
    if not member or member.is_deleted:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")

    valid_tiers = {"basic", "core", "premium"}
    if payload.budget_tier not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"budget_tier must be one of {valid_tiers}")

    result = await generate_recommendation(db, member_id, payload.budget_tier)
    comp = result["completeness"]

    # persist to DB
    report = CheckupReport(
        member_id=member_id,
        budget_tier=payload.budget_tier,
        content=result["content"],
        completeness_score=comp["score"],
        completeness_level=comp["level"],
        missing_fields=json.dumps(comp["missing_fields"], ensure_ascii=False),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    # 功能①: 生成体检预约待办
    try:
        from app.services import task_service
        await task_service.handle_checkup_generated(
            db, member_id, "按体检推荐预约检查", report.id,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("task gen failed for checkup %s", report.id)

    return RecommendResponse(
        content=result["content"],
        completeness=CompletenessOut(**comp),
    )


@router.get("/{member_id}/checkup-latest", response_model=Optional[RecommendResponse])
async def get_latest_report(member_id: int, db: AsyncSession = Depends(get_db)):
    """Return the most recent checkup report for a member, or null."""
    r = await db.execute(
        select(CheckupReport)
        .where(CheckupReport.member_id == member_id)
        .order_by(CheckupReport.created_at.desc())
        .limit(1)
    )
    report = r.scalars().first()
    if not report:
        return None
    missing = json.loads(report.missing_fields) if report.missing_fields else []
    return RecommendResponse(
        content=report.content,
        completeness=CompletenessOut(
            score=report.completeness_score,
            level=report.completeness_level,
            missing_fields=missing,
        ),
    )
