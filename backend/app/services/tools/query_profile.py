"""query_profile tool — fetch member health profile sections on demand."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import (
    Allergy,
    Diagnosis,
    FamilyHistory,
    Lifestyle,
    Medication,
    Surgery,
    Vaccination,
)
from app.services.tools.base import HealthTool


class QueryProfileTool(HealthTool):
    """Query a member's health profile sections."""

    name: str = "query_profile"
    description: str = (
        "查询家庭成员的健康画像：诊断、用药、过敏、生活方式、家族史、手术史、疫苗接种史。可指定查询类别。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": [
                    "diagnosis",
                    "medication",
                    "allergy",
                    "lifestyle",
                    "family_history",
                    "surgery",
                    "vaccination",
                ],
                "description": "查询类别",
            }
        },
        "required": ["category"],
    }

    async def execute(
        self, db: AsyncSession, member_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        category: str = kwargs.get("category", "")

        if category == "diagnosis":
            result = await db.execute(
                select(Diagnosis)
                .where(Diagnosis.member_id == member_id)
                .order_by(Diagnosis.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "diagnosis",
                "records": [
                    {
                        "id": r.id,
                        "disease_name": r.disease_name,
                        "icd_code": r.icd_code,
                        "diagnosed_date": r.diagnosed_date.isoformat() if r.diagnosed_date else None,
                        "severity": r.severity,
                        "status": r.status,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "medication":
            result = await db.execute(
                select(Medication)
                .where(Medication.member_id == member_id)
                .order_by(Medication.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "medication",
                "records": [
                    {
                        "id": r.id,
                        "drug_name": r.drug_name,
                        "generic_name": r.generic_name,
                        "dosage": r.dosage,
                        "frequency": r.frequency,
                        "route": r.route,
                        "start_date": r.start_date.isoformat() if r.start_date else None,
                        "end_date": r.end_date.isoformat() if r.end_date else None,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "allergy":
            result = await db.execute(
                select(Allergy)
                .where(Allergy.member_id == member_id)
                .order_by(Allergy.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "allergy",
                "records": [
                    {
                        "id": r.id,
                        "type": r.type,
                        "name": r.name,
                        "severity": r.severity,
                        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "lifestyle":
            result = await db.execute(
                select(Lifestyle)
                .where(Lifestyle.member_id == member_id)
                .order_by(Lifestyle.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "lifestyle",
                "records": [
                    {
                        "id": r.id,
                        "category": r.category,
                        "status": r.status,
                        "frequency": r.frequency,
                        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "family_history":
            result = await db.execute(
                select(FamilyHistory)
                .where(FamilyHistory.member_id == member_id)
                .order_by(FamilyHistory.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "family_history",
                "records": [
                    {
                        "id": r.id,
                        "relation": r.relation,
                        "disease_name": r.disease_name,
                        "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "surgery":
            result = await db.execute(
                select(Surgery)
                .where(Surgery.member_id == member_id)
                .order_by(Surgery.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "surgery",
                "records": [
                    {
                        "id": r.id,
                        "surgery_name": r.surgery_name,
                        "surgery_date": r.surgery_date.isoformat() if r.surgery_date else None,
                        "hospital": r.hospital,
                        "notes": r.notes,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        if category == "vaccination":
            result = await db.execute(
                select(Vaccination)
                .where(Vaccination.member_id == member_id)
                .order_by(Vaccination.created_at.desc())
            )
            rows = result.scalars().all()
            return {
                "category": "vaccination",
                "records": [
                    {
                        "id": r.id,
                        "vaccine_name": r.vaccine_name,
                        "dose_no": r.dose_no,
                        "vaccinated_date": r.vaccinated_date.isoformat() if r.vaccinated_date else None,
                    }
                    for r in rows
                ],
                "count": len(rows),
            }

        return {"error": f"未知类别: {category}", "category": category, "records": [], "count": 0}
