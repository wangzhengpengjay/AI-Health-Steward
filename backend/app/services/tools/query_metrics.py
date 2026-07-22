"""query_metrics tool — fetch a member's health metric history."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import MetricRecord
from app.services.tools.base import HealthTool


class QueryMetricsTool(HealthTool):
    """Query historical health metric records for a family member."""

    name: str = "query_metrics"
    description: str = (
        "查询家庭成员的健康指标数据，如血压、血糖、血脂、心率、体重等。"
        "可按指标名称查询历史记录。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "metric_name": {
                "type": "string",
                "description": (
                    "指标名称，如 systolic_blood_pressure, "
                    "fasting_glucose, total_cholesterol, heart_rate, weight"
                ),
            },
            "limit": {
                "type": "integer",
                "description": "返回最近N条记录，默认10",
            },
        },
        "required": [],
    }

    async def execute(
        self, db: AsyncSession, member_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        metric_name: str | None = kwargs.get("metric_name")
        limit: int = kwargs.get("limit", 10)

        stmt = select(MetricRecord).where(MetricRecord.member_id == member_id)
        if metric_name:
            stmt = stmt.where(MetricRecord.metric_name == metric_name)
        stmt = stmt.order_by(MetricRecord.measured_at.desc()).limit(limit)

        result = await db.execute(stmt)
        records = result.scalars().all()

        def _ref_range(r: MetricRecord) -> str | None:
            if r.reference_lower is not None and r.reference_upper is not None:
                return f"{r.reference_lower}-{r.reference_upper}"
            return None

        return {
            "metrics": [
                {
                    "metric_name": r.metric_name,
                    "value": r.value,
                    "unit": r.unit,
                    "measured_at": r.measured_at.isoformat() if r.measured_at else None,
                    "is_abnormal": r.is_abnormal,
                    "is_critical": r.is_critical,
                    "reference_range": _ref_range(r),
                    "context": r.context,
                }
                for r in records
            ],
            "count": len(records),
        }
