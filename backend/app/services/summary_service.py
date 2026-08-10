"""Health summary service — generate periodic (weekly/monthly/annual) reviews.

Strategy: deterministic rule-based statistics (metric trends, abnormal/critical
events, new diagnoses/medications) always run first; an LLM pass (when a text
provider is configured) enriches the prose. If LLM fails, rules-only copy is
used so generation never blocks.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import Diagnosis, Medication, MetricRecord
from app.models.summaries import HealthSummary

logger = logging.getLogger(__name__)

_METRIC_LABELS: dict[str, str] = {
    "systolic_blood_pressure": "收缩压",
    "diastolic_blood_pressure": "舒张压",
    "fasting_glucose": "空腹血糖",
    "postmeal_glucose": "餐后血糖",
    "heart_rate": "心率",
    "total_cholesterol": "总胆固醇",
    "triglycerides": "甘油三酯",
    "ldl_cholesterol": "LDL-C",
    "hdl_cholesterol": "HDL-C",
    "weight": "体重",
    "bmi": "BMI",
}

_PERIOD_LABELS: dict[str, str] = {"weekly": "周报", "monthly": "月报", "annual": "年报"}
_PERIOD_DAYS: dict[str, int] = {"weekly": 7, "monthly": 30, "annual": 365}


def _metric_label(name: str) -> str:
    if name.startswith("lab:") or name.startswith("exam:"):
        return name.split(":", 1)[-1]
    return _METRIC_LABELS.get(name, name)


async def _load_metrics(db: AsyncSession, member_id: int, start: date, end: date) -> list[MetricRecord]:
    result = await db.execute(
        select(MetricRecord).where(
            MetricRecord.member_id == member_id,
            MetricRecord.measured_at >= datetime.combine(start, datetime.min.time()),
            MetricRecord.measured_at <= datetime.combine(end, datetime.max.time()),
        ).order_by(MetricRecord.measured_at.asc())
    )
    return list(result.scalars().all())


async def _load_profile_events(
    db: AsyncSession, member_id: int, start: date, end: date
) -> tuple[list[Diagnosis], list[Medication]]:
    d_res = await db.execute(
        select(Diagnosis).where(
            Diagnosis.member_id == member_id,
            Diagnosis.created_at >= datetime.combine(start, datetime.min.time()),
            Diagnosis.created_at <= datetime.combine(end, datetime.max.time()),
        )
    )
    m_res = await db.execute(
        select(Medication).where(
            Medication.member_id == member_id,
            Medication.created_at >= datetime.combine(start, datetime.min.time()),
            Medication.created_at <= datetime.combine(end, datetime.max.time()),
        )
    )
    return list(d_res.scalars().all()), list(m_res.scalars().all())


def _build_stats(metrics: list[MetricRecord]) -> dict[str, Any]:
    """Compute per-metric trend (first/last/min/max/avg, direction) for non-report metrics."""
    by_name: dict[str, list[MetricRecord]] = {}
    for m in metrics:
        if m.metric_name.startswith("lab:") or m.metric_name.startswith("exam:"):
            continue
        by_name.setdefault(m.metric_name, []).append(m)

    trends: list[dict[str, Any]] = []
    for name, recs in by_name.items():
        recs.sort(key=lambda r: r.measured_at)
        first, last = recs[0], recs[-1]
        values = [r.value for r in recs if r.value is not None]
        delta = (last.value - first.value) if first.value is not None and last.value is not None else None
        direction = "up" if (delta is not None and delta > 0) else ("down" if (delta is not None and delta < 0) else "flat")
        trends.append({
            "metric": name,
            "label": _metric_label(name),
            "first": first.value,
            "last": last.value,
            "unit": last.unit or "",
            "delta": round(delta, 2) if delta is not None else None,
            "direction": direction,
            "min": round(min(values), 2) if values else None,
            "max": round(max(values), 2) if values else None,
            "avg": round(sum(values) / len(values), 2) if values else None,
            "count": len(recs),
            "abnormal_last": last.is_abnormal,
            "reference_lower": last.reference_lower,
            "reference_upper": last.reference_upper,
        })
    return {"trends": trends}


def _build_events(metrics: list[MetricRecord]) -> dict[str, Any]:
    abnormal = [
        {"metric": m.metric_name, "label": _metric_label(m.metric_name), "value": m.value, "unit": m.unit or "", "date": m.measured_at.date().isoformat()}
        for m in metrics
        if m.is_abnormal and not m.metric_name.startswith("lab:") and not m.metric_name.startswith("exam:")
    ]
    critical = [
        {"metric": m.metric_name, "label": _metric_label(m.metric_name), "value": m.value, "unit": m.unit or "", "date": m.measured_at.date().isoformat()}
        for m in metrics
        if m.is_critical and not m.metric_name.startswith("lab:") and not m.metric_name.startswith("exam:")
    ]
    return {"abnormal": abnormal, "critical": critical}


def _render_markdown(
    period: str,
    period_start: date,
    period_end: date,
    stats: dict[str, Any],
    events: dict[str, Any],
    diagnoses: list[Diagnosis],
    medications: list[Medication],
) -> str:
    lines: list[str] = []
    period_label = _PERIOD_LABELS.get(period, period)
    lines.append(f"# {period_label}健康小结（{period_start.isoformat()} ~ {period_end.isoformat()}）")
    lines.append("")

    n_records = sum(t["count"] for t in stats.get("trends", []))
    n_abnormal = len(events.get("abnormal", []))
    n_critical = len(events.get("critical", []))
    lines.append("## 本期概览")
    lines.append(f"- 数据记录：{n_records} 条")
    lines.append(f"- 异常指标：{n_abnormal} 项")
    lines.append(f"- 危急指标：{n_critical} 项")
    if diagnoses:
        lines.append(f"- 新增诊断：{len(diagnoses)} 项")
    if medications:
        lines.append(f"- 新增用药：{len(medications)} 项")
    lines.append("")

    if stats.get("trends"):
        lines.append("## 指标趋势")
        for t in stats["trends"]:
            direction_str = {"up": "上升", "down": "下降", "flat": "平稳"}.get(t["direction"], "平稳")
            line = f"- {t['label']}：{t['first']} → {t['last']} {t['unit']}（{direction_str}"
            if t["delta"]:
                line += f" {abs(t['delta']):g} {t['unit']}"
            line += "）"
            if t.get("abnormal_last"):
                line += " ⚠ 最新值异常"
            lines.append(line)
        lines.append("")

    if events.get("critical"):
        lines.append("## 危急指标（请尽快就医）")
        for e in events["critical"]:
            lines.append(f"- ⛔ {e['label']}：{e['value']} {e['unit']}（{e['date']}）")
        lines.append("")
    if events.get("abnormal"):
        lines.append("## 异常指标（建议关注）")
        for e in events["abnormal"]:
            lines.append(f"- ⚠ {e['label']}：{e['value']} {e['unit']}（{e['date']}）")
        lines.append("")

    if diagnoses:
        lines.append("## 新增诊断")
        for d in diagnoses:
            lines.append(f"- {d.disease_name}")
        lines.append("")
    if medications:
        lines.append("## 新增用药")
        for m in medications:
            lines.append(f"- {m.drug_name} {m.dosage or ''} {m.frequency or ''}")
        lines.append("")

    suggestions: list[str] = []
    if events.get("critical"):
        suggestions.append("存在危急指标，请尽快就医复查。")
    if events.get("abnormal"):
        suggestions.append(f"有 {n_abnormal} 项指标异常，建议按需复查并调整生活方式。")
    if not events.get("critical") and not events.get("abnormal"):
        suggestions.append("本期指标整体平稳，请继续保持健康生活方式。")
    if suggestions:
        lines.append("## 建议")
        for s in suggestions:
            lines.append(f"- {s}")
        lines.append("")
    lines.append("---")
    lines.append("*本小结由系统自动生成，仅供参考，不构成医疗建议。*")
    return "\n".join(lines)


async def generate_summary(
    db: AsyncSession,
    member_id: int,
    period: str,
    period_start: date | None = None,
    period_end: date | None = None,
) -> HealthSummary:
    """Generate and persist a summary for a period (defaults to the recent period)."""
    if period not in _PERIOD_DAYS:
        period = "monthly"
    today = date.today()
    if period_end is None:
        period_end = today
    if period_start is None:
        period_start = today - timedelta(days=_PERIOD_DAYS[period])

    metrics = await _load_metrics(db, member_id, period_start, period_end)
    diagnoses, medications = await _load_profile_events(db, member_id, period_start, period_end)

    stats = _build_stats(metrics)
    events = _build_events(metrics)
    content = _render_markdown(period, period_start, period_end, stats, events, diagnoses, medications)

    # Optional LLM enrichment — best-effort, never blocks generation.
    try:
        content = await _maybe_enrich(period, content, stats, events)
    except Exception:  # noqa: BLE001
        logger.exception("LLM summary enrichment failed, using rule-based copy")

    summary = HealthSummary(
        member_id=member_id,
        summary_type="auto",
        period=period,
        period_start=period_start,
        period_end=period_end,
        stats_json=json.dumps(stats, ensure_ascii=False),
        abnormal_events=json.dumps(events, ensure_ascii=False),
        content=content,
    )
    db.add(summary)
    await db.flush()
    await db.refresh(summary)
    return summary


async def _maybe_enrich(
    period: str,
    rule_content: str,
    stats: dict[str, Any],
    events: dict[str, Any],
) -> str:
    """Optionally ask an LLM to add a natural-language interpretation."""
    from app.providers.router import ModelRouter
    from app.providers.base import Message

    router = ModelRouter()
    provider = router.get_text_provider()
    if provider is None or not provider.is_configured:
        return rule_content

    system = "你是一名家庭健康管家。请基于给定的结构化数据，写一段简洁、温和、实用的健康小结中文解读。保持客观，不做诊断。可用 Markdown 小标题。"
    user_prompt = (
        f"周期类型：{_PERIOD_LABELS.get(period, period)}\n"
        f"指标趋势：{json.dumps(stats.get('trends', []), ensure_ascii=False)}\n"
        f"异常事件：{json.dumps(events.get('abnormal', []), ensure_ascii=False)}\n"
        f"危急事件：{json.dumps(events.get('critical', []), ensure_ascii=False)}\n"
        f"请生成一段中文健康小结解读。"
    )
    resp = await provider.chat(
        [Message(role="system", content=system), Message(role="user", content=user_prompt)],
        temperature=0.4,
        max_tokens=800,
    )
    if resp and getattr(resp, "content", None):
        llm_part = resp.content.strip()
        return rule_content + "\n\n## AI 解读\n" + llm_part
    return rule_content
