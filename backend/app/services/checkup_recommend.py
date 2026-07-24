"""Checkup recommendation service — aggregates health profile, builds prompt, calls model."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyMember
from app.models.health import (
    Allergy,
    Diagnosis,
    FamilyHistory,
    Lifestyle,
    Medication,
    MetricRecord,
)
from app.providers.base import Message
from app.providers.router import get_model_router

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "checkup_system_v1.md"

BUDGET_LABELS = {
    "basic": "基础健康筛查型(300-800元)",
    "core": "核心风险排查型(800-2,500元)",
    "premium": "深度防癌与慢病管理型(2,500-8,000元+)",
}


def _age(birth_date: Optional[date]) -> Optional[int]:
    if not birth_date:
        return None
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def _special_status(member: FamilyMember) -> dict[str, Any]:
    """Build the special-status block from member fields."""
    return {
        "is_pregnant": member.is_pregnant,
        "is_preparing_pregnancy": member.is_preparing_pregnancy,
        "has_sexual_history": member.has_sexual_history,
        "contrast_allergy": member.contrast_allergy,
        "has_pacemaker": member.has_pacemaker,
        "has_metal_implant": member.has_metal_implant,
        "eGFR": member.egfr,
        "on_anticoagulant": member.on_anticoagulant,
        "claustrophobia": member.claustrophobia,
        "is_breastfeeding": member.is_breastfeeding,
        "has_coagulopathy": member.has_coagulopathy,
        "has_heart_failure": member.has_heart_failure,
    }


async def build_health_profile(db: AsyncSession, member_id: int) -> dict[str, Any]:
    """Aggregate all health data for a member into a structured profile JSON."""
    member = await db.get(FamilyMember, member_id)
    if not member:
        raise ValueError(f"FamilyMember {member_id} not found")

    age = _age(member.birth_date)

    # Diagnoses (active)
    diag_result = await db.execute(
        select(Diagnosis)
        .where(Diagnosis.member_id == member_id, Diagnosis.status == "active")
        .order_by(Diagnosis.created_at.desc())
    )
    diagnoses = diag_result.scalars().all()

    # Abnormal metrics
    abn_result = await db.execute(
        select(MetricRecord)
        .where(MetricRecord.member_id == member_id, MetricRecord.is_abnormal.is_(True))
        .order_by(MetricRecord.measured_at.desc())
    )
    abnormal_metrics = abn_result.scalars().all()

    # Family history
    fh_result = await db.execute(
        select(FamilyHistory).where(FamilyHistory.member_id == member_id)
    )
    family_history = fh_result.scalars().all()

    # Lifestyle
    ls_result = await db.execute(
        select(Lifestyle).where(Lifestyle.member_id == member_id)
    )
    lifestyles = ls_result.scalars().all()

    # Latest standard metrics (exclude lab:/exam: prefixed)
    metric_result = await db.execute(
        select(MetricRecord)
        .where(MetricRecord.member_id == member_id)
        .order_by(MetricRecord.measured_at.desc())
    )
    all_metrics = metric_result.scalars().all()
    latest_standard: dict[str, Any] = {}
    recent_exams: list[dict] = []
    six_months_ago = datetime.now() - timedelta(days=180)

    for r in all_metrics:
        if r.metric_name.startswith("lab:") or r.metric_name.startswith("exam:"):
            if r.measured_at.replace(tzinfo=None) >= six_months_ago:
                recent_exams.append({
                    "name": r.metric_name,
                    "value": r.value,
                    "unit": r.unit,
                    "is_abnormal": r.is_abnormal,
                    "measured_at": r.measured_at.isoformat(),
                })
        else:
            if r.metric_name not in latest_standard:
                latest_standard[r.metric_name] = {
                    "value": r.value,
                    "unit": r.unit,
                    "is_abnormal": r.is_abnormal,
                    "measured_at": r.measured_at.isoformat(),
                }

    # Medications
    med_result = await db.execute(
        select(Medication).where(Medication.member_id == member_id)
    )
    medications = med_result.scalars().all()

    # Allergies
    allergy_result = await db.execute(
        select(Allergy).where(Allergy.member_id == member_id)
    )
    allergies = allergy_result.scalars().all()

    return {
        "基本信息": {
            "age": age,
            "sex": "男" if member.gender == "male" else "女" if member.gender == "female" else "其他",
            "region": member.region or "",
            "occupation": member.occupation or "",
        },
        "生理指标": {
            "height": member.height,
            "weight": member.weight,
            "bmi": member.bmi,
            "latest_metrics": latest_standard,
        },
        "既往史与现病史": {
            "medical_history": [
                {"disease_name": d.disease_name, "status": d.status, "diagnosed_date": d.diagnosed_date.isoformat() if d.diagnosed_date else None}
                for d in diagnoses
            ],
            "known_abnormalities": [
                {"name": m.metric_name, "value": m.value, "unit": m.unit}
                for m in abnormal_metrics
            ],
            "current_symptoms": [],
        },
        "家族史": {
            "family_history": [
                {"relation": f.relation, "disease_name": f.disease_name}
                for f in family_history
            ],
        },
        "生活方式": {
            item.category: {"status": item.status, "frequency": item.frequency}
            for item in lifestyles
        },
        "用药记录": [
            {"drug_name": m.drug_name, "dosage": m.dosage, "frequency": m.frequency}
            for m in medications
        ],
        "过敏信息": [
            {"type": a.type, "name": a.name, "severity": a.severity}
            for a in allergies
        ],
        "近期检查记录": {"recent_exams": recent_exams},
        "特殊状态": _special_status(member),
    }


def compute_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """Compute profile completeness score per PRD 2.4 algorithm."""
    checks: list[tuple[str, bool]] = []

    # Basic info (age 10%, sex 10%)
    age = profile.get("基本信息", {}).get("age")
    checks.append(("年龄", age is not None and age > 0))
    sex = profile.get("基本信息", {}).get("sex")
    checks.append(("性别", bool(sex) and sex != ""))

    # Past medical history (10%)
    has_diag = len(profile.get("既往史与现病史", {}).get("medical_history", [])) > 0
    checks.append(("既往史", has_diag))

    # Family history (10%)
    has_fh = len(profile.get("家族史", {}).get("family_history", [])) > 0
    checks.append(("家族史", has_fh))

    # Lifestyle: smoking, drinking, exercise (5% each)
    lifestyle = profile.get("生活方式", {})
    checks.append(("吸烟", "smoking" in lifestyle or "drinking" in lifestyle))
    checks.append(("饮酒", "drinking" in lifestyle))
    checks.append(("运动", "exercise" in lifestyle))

    # Special status: at least 1 non-unknown (10%)
    special = profile.get("特殊状态", {})
    has_special = any(
        v not in ("unknown", None) for v in special.values()
    )
    checks.append(("特殊状态", has_special))

    # Also count region & occupation
    region = profile.get("基本信息", {}).get("region")
    checks.append(("地域", bool(region)))
    occupation = profile.get("基本信息", {}).get("occupation")
    checks.append(("职业", bool(occupation)))

    weights = [10, 10, 10, 10, 5, 5, 5, 10, 5, 5]
    total_weight = sum(weights)
    filled_weight = sum(w for (_, filled), w in zip(checks, weights) if filled)
    score = round(filled_weight / total_weight * 100)

    if score >= 80:
        level = "🟢"
    elif score >= 50:
        level = "🟡"
    else:
        level = "🔴"

    missing = [name for (name, filled), _ in zip(checks, weights) if not filled]
    return {"score": score, "level": level, "missing_fields": missing}


async def generate_recommendation(
    db: AsyncSession, member_id: int, budget_tier: str
) -> dict[str, Any]:
    """Build profile, construct prompt, call text model, return markdown + completeness."""
    profile = await build_health_profile(db, member_id)
    completeness = compute_completeness(profile)

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    budget_label = BUDGET_LABELS.get(budget_tier, BUDGET_LABELS["core"])

    # Inject profile JSON and budget into the user message
    profile_json = json.dumps(profile, ensure_ascii=False, indent=2, default=str)
    user_message = (
        f"请使用以下用户健康画像进行体检推荐。\n\n"
        f"经济预算档位：{budget_label}\n\n"
        f"【用户健康画像】\n{profile_json}"
    )

    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=user_message),
    ]

    router = get_model_router()
    provider = router.get_text_provider()
    response = await provider.chat(messages, tools=None)

    return {
        "content": response.content or "",
        "completeness": completeness,
    }
