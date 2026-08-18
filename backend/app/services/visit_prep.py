"""Visit preparation service — generates structured pre-visit guidance.

Does NOT persist results. Returns a dict for the API to send to the client.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.department_mapping import suggest_department
from app.core.reference_ranges import resolve_reference_range
from app.core.utils import compute_age, metric_label
from app.models.family import FamilyMember
from app.models.health import (
    Allergy,
    Diagnosis,
    FamilyHistory,
    Lifestyle,
    Medication,
    MetricRecord,
    Surgery,
    Vaccination,
)
from app.providers.base import Message
from app.providers.router import ModelRouter

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "visit_prep_v1.md"


async def _load_member_info(db: AsyncSession, member_id: int) -> dict[str, Any]:
    """Load basic member info + diagnoses for department suggestion."""
    member = await db.get(FamilyMember, member_id)
    if not member:
        raise ValueError(f"FamilyMember {member_id} not found")

    diag_result = await db.execute(
        select(Diagnosis)
        .where(Diagnosis.member_id == member_id)
        .order_by(Diagnosis.created_at.desc())
    )
    diagnoses = [d.disease_name for d in diag_result.scalars().all()]

    return {
        "member": member,
        "diagnoses": diagnoses,
    }


async def suggest_dept(
    db: AsyncSession, member_id: int, chief_complaint: str
) -> dict[str, Any]:
    """Suggest a department based on chief complaint + diagnosis history."""
    info = await _load_member_info(db, member_id)
    dept, reason = suggest_department(chief_complaint, info["diagnoses"])
    return {"department": dept, "reason": reason}


async def _load_metrics_trend(
    db: AsyncSession,
    member_id: int,
    metric_names: list[str],
    days: int = 90,
) -> list[dict[str, Any]]:
    """Load trend data for selected metrics over the past N days."""
    if not metric_names:
        return []

    since = datetime.now() - timedelta(days=days)
    result = await db.execute(
        select(MetricRecord)
        .where(
            MetricRecord.member_id == member_id,
            MetricRecord.metric_name.in_(metric_names),
            MetricRecord.measured_at >= since,
        )
        .order_by(MetricRecord.measured_at.asc())
    )
    records = result.scalars().all()

    # Group by metric_name
    grouped: dict[str, list[MetricRecord]] = {}
    for r in records:
        grouped.setdefault(r.metric_name, []).append(r)

    # Get age for reference range resolution
    member = await db.get(FamilyMember, member_id)
    age = compute_age(member.birth_date) if member else None

    trends: list[dict[str, Any]] = []
    for name, recs in grouped.items():
        ref_lower, ref_upper = resolve_reference_range(name, age)
        values = [r.value for r in recs if r.value is not None]
        if not values:
            continue

        if len(values) > 1:
            if values[-1] > values[0]:
                trend_dir = "up"
            elif values[-1] < values[0]:
                trend_dir = "down"
            else:
                trend_dir = "flat"
        else:
            trend_dir = "flat"

        trends.append({
            "metric_name": name,
            "label": metric_label(name),
            "unit": recs[-1].unit or "",
            "records": [
                {"date": r.measured_at.strftime("%Y-%m-%d"), "value": r.value}
                for r in recs
            ],
            "reference_lower": ref_lower,
            "reference_upper": ref_upper,
            "trend": trend_dir,
            "latest_value": values[-1],
            "is_abnormal": recs[-1].is_abnormal,
        })

    return trends


async def _build_profile_for_prompt(
    db: AsyncSession, member_id: int
) -> dict[str, Any]:
    """Build a condensed health profile for the LLM prompt."""
    member = await db.get(FamilyMember, member_id)
    if not member:
        raise ValueError(f"FamilyMember {member_id} not found")

    age = compute_age(member.birth_date)
    gender = member.gender or "未知"

    # Diagnoses
    diag_result = await db.execute(
        select(Diagnosis)
        .where(Diagnosis.member_id == member_id)
        .order_by(Diagnosis.created_at.desc())
    )
    diagnoses = [
        {"name": d.disease_name, "date": str(d.diagnosed_date or "")}
        for d in diag_result.scalars().all()
    ]

    # Medications
    med_result = await db.execute(
        select(Medication).where(Medication.member_id == member_id)
    )
    medications = [
        {"name": m.drug_name, "dosage": m.dosage, "frequency": m.frequency}
        for m in med_result.scalars().all()
    ]

    # Allergies
    allergy_result = await db.execute(
        select(Allergy).where(Allergy.member_id == member_id)
    )
    allergies = [a.allergen for a in allergy_result.scalars().all()]

    # Family history
    fh_result = await db.execute(
        select(FamilyHistory).where(FamilyHistory.member_id == member_id)
    )
    family_history = [fh.condition for fh in fh_result.scalars().all()]

    # Lifestyle
    ls_result = await db.execute(
        select(Lifestyle).where(Lifestyle.member_id == member_id)
    )
    lifestyles = [
        {"type": ls.lifestyle_type, "detail": ls.detail}
        for ls in ls_result.scalars().all()
    ]

    # Surgeries
    surgery_result = await db.execute(
        select(Surgery).where(Surgery.member_id == member_id)
    )
    surgeries = [
        {"name": s.surgery_name, "date": str(s.surgery_date or "")}
        for s in surgery_result.scalars().all()
    ]

    # Latest standard metrics
    metric_result = await db.execute(
        select(MetricRecord)
        .where(MetricRecord.member_id == member_id)
        .order_by(MetricRecord.measured_at.desc())
    )
    all_metrics = metric_result.scalars().all()
    latest_standard: dict[str, Any] = {}
    for r in all_metrics:
        if r.metric_name.startswith("lab:") or r.metric_name.startswith("exam:"):
            continue
        if r.metric_name not in latest_standard:
            latest_standard[r.metric_name] = {
                "value": r.value,
                "unit": r.unit,
                "is_abnormal": r.is_abnormal,
                "measured_at": r.measured_at.strftime("%Y-%m-%d"),
            }

    return {
        "basic_info": {"gender": gender, "age": age},
        "diagnoses": diagnoses,
        "medications": medications,
        "allergies": allergies,
        "family_history": family_history,
        "lifestyle": lifestyles,
        "surgeries": surgeries,
        "latest_metrics": latest_standard,
    }


async def _build_user_prompt(
    chief_complaint: str,
    department: str,
    profile: dict[str, Any],
    metrics_trend: list[dict[str, Any]],
) -> str:
    """Build the user message for the LLM."""
    profile_json = json.dumps(profile, ensure_ascii=False, default=str)
    trend_json = json.dumps(metrics_trend, ensure_ascii=False, default=str)

    return (
        f"## 就诊主诉\n{chief_complaint}\n\n"
        f"## 就诊科室\n{department}\n\n"
        f"## 健康画像\n{profile_json}\n\n"
        f"## 指标趋势\n{trend_json}\n\n"
        "请根据以上信息生成就医指导方案。"
    )


def _parse_json_response(content: str) -> dict[str, Any]:
    """Parse LLM JSON response, stripping markdown code blocks if present."""
    text = content.strip()
    # Strip markdown code block
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return json.loads(text)


async def generate_visit_prep(
    db: AsyncSession,
    router: ModelRouter,
    member_id: int,
    chief_complaint: str,
    department: str,
    selected_metrics: list[str],
) -> dict[str, Any]:
    """Generate structured pre-visit guidance. Does NOT persist results."""
    # 1. Load health profile
    profile = await _build_profile_for_prompt(db, member_id)

    # 2. Load metrics trend
    metrics_trend = await _load_metrics_trend(db, member_id, selected_metrics)

    # 3. Build prompt
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_prompt = await _build_user_prompt(
        chief_complaint, department, profile, metrics_trend
    )

    # 4. Call LLM
    provider = router.get_text_provider()
    response = await provider.chat(
        [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        temperature=0.3,
        max_tokens=2000,
    )

    # 5. Parse response
    try:
        result = _parse_json_response(response.content)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.exception("Failed to parse visit prep JSON: %s", exc)
        result = {
            "questions": [],
            "checklist": [],
            "summary": response.content[:500] if response.content else "",
        }

    # 6. Attach metadata (trend data comes from DB, not LLM)
    result["metrics_trend"] = metrics_trend
    result["department"] = department
    result["chief_complaint"] = chief_complaint

    return result
