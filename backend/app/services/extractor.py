"""Model-based health metric extractor.

Calls text model to extract structured metrics from user messages,
then persists them. Limited to blood pressure, blood glucose,
height, and weight.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import MetricRecord
from app.providers.base import Message
from app.providers.router import ModelRouter

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = """\
你是一个健康数据提取助手。分析用户的消息，提取其中提到的健康指标数值。

只提取以下指标，没有提及的不要输出：
- 血压（收缩压 systolic_blood_pressure / 舒张压 diastolic_blood_pressure，单位 mmHg）
- 血糖（空腹 fasting_glucose，单位 mmol/L）
- 身高（height，单位 cm）
- 体重（weight，单位 kg）
- 心率（heart_rate，单位 bpm）

严格按以下 JSON 格式返回，不要包含任何其他文字或 markdown 标记：
{"metrics": [{"metric_name": "systolic_blood_pressure", "value": 180, "unit": "mmHg"}, {"metric_name": "diastolic_blood_pressure", "value": 90, "unit": "mmHg"}]}

如果用户消息中没有提到任何上述指标数值，返回：{"metrics": []}

参考范围（用于判断是否异常）：
- 收缩压：90-140
- 舒张压：60-90
- 空腹血糖：3.9-6.1
- 心率：60-100
"""


async def extract_metrics_from_text(
    db: AsyncSession,
    router: ModelRouter,
    member_id: int,
    text: str,
) -> list[dict[str, Any]]:
    """Use model to extract metrics from text, save to DB.

    Returns list of saved metric dicts.
    """
    try:
        provider = router.get_text_provider()
        messages = [
            Message(role="system", content=EXTRACT_PROMPT),
            Message(role="user", content=text),
        ]
        response = await provider.chat(messages, temperature=0.0, max_tokens=512)
        raw = response.content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines)
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Metric extraction failed: %s", e)
        return []

    metrics = data.get("metrics", [])
    if not metrics:
        return []

    # Reference ranges for abnormality check
    ref_ranges = {
        "systolic_blood_pressure": (90, 140),
        "diastolic_blood_pressure": (60, 90),
        "fasting_glucose": (3.9, 6.1),
        "height": (None, None),
        "weight": (None, None),
        "heart_rate": (60, 100),
    }

    saved: list[dict[str, Any]] = []
    now = datetime.now(timezone(timedelta(hours=8)))

    for m in metrics:
        name = m.get("metric_name", "")
        value = m.get("value")
        if not name or value is None:
            continue

        ref_lo, ref_hi = ref_ranges.get(name, (None, None))
        is_abnormal = False
        if ref_lo is not None and ref_hi is not None:
            is_abnormal = float(value) < ref_lo or float(value) > ref_hi

        record = MetricRecord(
            member_id=member_id,
            metric_name=name,
            value=float(value),
            unit=m.get("unit", ""),
            reference_lower=ref_lo,
            reference_upper=ref_hi,
            is_abnormal=is_abnormal,
            measured_at=now,
            source_type="chat_extract",
            context="对话提取",
        )
        db.add(record)
        saved.append({
            "metric_name": name,
            "value": float(value),
            "unit": m.get("unit", ""),
            "is_abnormal": is_abnormal,
        })

    if saved:
        await db.flush()
        logger.info("Model-extracted %d metrics from chat", len(saved))

    return saved
