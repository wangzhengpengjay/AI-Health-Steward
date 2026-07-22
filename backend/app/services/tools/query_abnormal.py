"""query_abnormal tool — fetch abnormal metric records."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import MetricRecord
from app.services.tools.base import HealthTool


class QueryAbnormalTool(HealthTool):
    """Query a member's abnormal health metrics (outside reference range)."""

    name: str = "query_abnormal"
    description: str = "查询家庭成员的异常健康指标，返回超出参考范围的指标列表。"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(
        self, db: AsyncSession, member_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        stmt = (
            select(MetricRecord)
            .where(
                MetricRecord.member_id == member_id,
                MetricRecord.is_abnormal.is_(True),
            )
            .order_by(MetricRecord.measured_at.desc())
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        def _ref_range(r: MetricRecord) -> str | None:
            if r.reference_lower is not None and r.reference_upper is not None:
                return f"{r.reference_lower}-{r.reference_upper}"
            return None

        return {
            "abnormal_metrics": [
                {
                    "metric_name": r.metric_name,
                    "value": r.value,
                    "unit": r.unit,
                    "measured_at": r.measured_at.isoformat() if r.measured_at else None,
                    "is_critical": r.is_critical,
                    "reference_range": _ref_range(r),
                    "context": r.context,
                }
                for r in records
            ],
            "count": len(records),
        }
