"""extract_and_save tool — extract health data from chat and persist it."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.family import FamilyMember
from app.models.health import Lifestyle, MetricRecord
from app.services.tools.base import HealthTool


class ExtractAndSaveTool(HealthTool):
    """Extract health data mentioned in conversation and save it to the profile."""

    name: str = "extract_and_save"
    description: str = (
        "从用户对话中提取健康数据并保存到健康画像。"
        "当用户在对话中提到自己的健康指标值（如'我今天测了血压130/85'）、"
        "症状（如'最近头晕'）、用药变化等信息时，使用此工具提取并保存。"
        "注意：调用此工具后需要告知用户已记录，并在响应中提示数据已保存。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "data_type": {
                "type": "string",
                "enum": ["metric", "symptom", "medication"],
                "description": "数据类型：metric=指标值, symptom=症状, medication=用药",
            },
            "metric_name": {
                "type": "string",
                "description": "指标名称（data_type=metric时必填），如 systolic_blood_pressure",
            },
            "value": {
                "type": "number",
                "description": "指标数值（data_type=metric时必填）",
            },
            "unit": {
                "type": "string",
                "description": "单位，如 mmHg, mmol/L",
            },
            "measured_at": {
                "type": "string",
                "description": "测量时间，ISO格式，如 2026-07-22T08:00:00",
            },
            "description": {
                "type": "string",
                "description": "症状或用药的描述（data_type=symptom/medication时必填）",
            },
        },
        "required": ["data_type"],
    }

    async def execute(
        self, db: AsyncSession, member_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        data_type: str = kwargs.get("data_type", "")

        if data_type == "metric":
            return await self._save_metric(db, member_id, kwargs)
        if data_type == "symptom":
            return await self._save_symptom(db, member_id, kwargs)
        if data_type == "medication":
            return await self._save_medication(db, member_id, kwargs)
        return {"saved": False, "error": f"未知 data_type: {data_type}"}

    async def _save_metric(
        self, db: AsyncSession, member_id: int, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        metric_name = kwargs.get("metric_name")
        value = kwargs.get("value")
        if not metric_name or value is None:
            return {
                "saved": False,
                "data_type": "metric",
                "error": "metric_name 和 value 为必填项",
            }

        measured_at_str = kwargs.get("measured_at")
        measured_at = self._parse_datetime(measured_at_str) if measured_at_str else datetime.now(timezone.utc)

        # P0-2: 按成员年龄自动填充默认参考范围并计算异常/危急
        from app.core.reference_ranges import is_critical_value, resolve_reference_range
        member = await db.get(FamilyMember, member_id)
        age = _age(member.birth_date) if member else None
        ref_lo, ref_hi = resolve_reference_range(metric_name, age)
        value_f = float(value)
        is_abnormal = False
        is_critical = False
        if ref_lo is not None and ref_hi is not None:
            is_abnormal = not (ref_lo <= value_f <= ref_hi)
            is_critical = is_critical_value(metric_name, value_f, age)

        record = MetricRecord(
            member_id=member_id,
            metric_name=metric_name,
            value=value_f,
            unit=kwargs.get("unit"),
            reference_lower=ref_lo,
            reference_upper=ref_hi,
            is_abnormal=is_abnormal,
            is_critical=is_critical,
            measured_at=measured_at,
            source_type="chat_extract",
            context=kwargs.get("context"),
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)

        flag = "（异常）" if is_abnormal else ""
        return {
            "saved": True,
            "data_type": "metric",
            "record_id": record.id,
            "is_abnormal": is_abnormal,
            "is_critical": is_critical,
            "message": f"已记录您的{metric_name}数据：{value}{kwargs.get('unit', '')}{flag}",
        }

    async def _save_symptom(
        self, db: AsyncSession, member_id: int, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        description = kwargs.get("description")
        if not description:
            return {
                "saved": False,
                "data_type": "symptom",
                "error": "description 为必填项",
            }

        # Store symptoms as a lifestyle record with category="symptom"
        record = Lifestyle(
            member_id=member_id,
            category="symptom",
            status=description,
            recorded_at=None,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)

        return {
            "saved": True,
            "data_type": "symptom",
            "record_id": record.id,
            "message": f"已记录您的症状描述：{description}",
        }

    async def _save_medication(
        self, db: AsyncSession, member_id: int, kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        description = kwargs.get("description")
        if not description:
            return {
                "saved": False,
                "data_type": "medication",
                "error": "description 为必填项",
            }

        # Store medication mentions as a lifestyle record with category="medication_mention"
        # for lightweight tracking. Full medication records should use the dedicated API.
        record = Lifestyle(
            member_id=member_id,
            category="medication_mention",
            status=description,
            recorded_at=None,
        )
        db.add(record)
        await db.flush()
        await db.refresh(record)

        return {
            "saved": True,
            "data_type": "medication",
            "record_id": record.id,
            "message": f"已记录您的用药信息：{description}",
        }

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        """Parse an ISO datetime string, falling back to now on failure."""
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)


def _age(birth_date) -> int | None:
    """Compute age in years from birth_date (date or None)."""
    if not birth_date:
        return None
    from datetime import date
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
