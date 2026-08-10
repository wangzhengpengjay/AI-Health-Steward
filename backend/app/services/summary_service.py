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


async def _load_latest_metrics(db: AsyncSession, member_id: int) -> dict[str, dict[str, Any]]:
    """Load each metric's global most-recent record (any time), for recheck judgment.

    Returns {metric_name: {value, text_value, unit, is_abnormal, is_critical,
    measured_at, context}} — the latest row per metric across all time.
    """
    result = await db.execute(
        select(MetricRecord).where(MetricRecord.member_id == member_id)
        .order_by(MetricRecord.measured_at.desc())
    )
    latest: dict[str, dict[str, Any]] = {}
    for m in result.scalars().all():
        if m.metric_name in latest:
            continue
        latest[m.metric_name] = {
            "metric": m.metric_name,
            "label": _metric_label(m.metric_name),
            "value": m.value,
            "text_value": m.text_value,
            "unit": m.unit or "",
            "is_abnormal": m.is_abnormal,
            "is_critical": m.is_critical,
            "measured_at": m.measured_at.isoformat() if m.measured_at else None,
            "context": m.context or "",
        }
    return latest


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
    """Compute per-metric trend for ALL user metrics (incl. lab:/exam: report metrics)."""
    by_name: dict[str, list[MetricRecord]] = {}
    for m in metrics:
        by_name.setdefault(m.metric_name, []).append(m)

    trends: list[dict[str, Any]] = []
    for name, recs in by_name.items():
        recs.sort(key=lambda r: r.measured_at)
        first, last = recs[0], recs[-1]
        # numeric trend only makes sense for records with a numeric value (text_value None)
        numeric_recs = [r for r in recs if r.value is not None and r.text_value is None]
        values = [r.value for r in numeric_recs]
        numeric = len(values) > 0
        if numeric:
            delta = values[-1] - values[0]
            direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        else:
            delta = None
            direction = "flat"
        trends.append({
            "metric": name,
            "label": _metric_label(name),
            "numeric": numeric,
            "first": values[0] if numeric else None,
            "last": values[-1] if numeric else None,
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


def _event_item(m: MetricRecord) -> dict[str, Any]:
    """Build an abnormal/critical event entry, preferring the readable text value and adding report source."""
    value = m.text_value if m.text_value is not None else m.value
    return {
        "metric": m.metric_name,
        "label": _metric_label(m.metric_name),
        "value": value,
        "unit": m.unit or "",
        "date": m.measured_at.date().isoformat(),
        "context": m.context or "",
    }


def _build_events(metrics: list[MetricRecord]) -> dict[str, Any]:
    """Group abnormal/critical events per metric.

    - critical: a metric that was ever critical in the period is kept for continued
      attention (even if it has since returned to normal), shown with its latest value.
    - abnormal: only metrics whose LATEST record is still abnormal are reported
      (historical/recovered abnormalities are not re-flagged). One row per metric.
    """
    by_name: dict[str, list[MetricRecord]] = {}
    for m in metrics:
        by_name.setdefault(m.metric_name, []).append(m)

    abnormal: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []
    for name, recs in by_name.items():
        recs.sort(key=lambda r: r.measured_at)
        last = recs[-1]
        ever_critical = any(r.is_critical for r in recs)
        if ever_critical:
            item = _event_item(last)
            item["had_critical"] = True  # was critical this period, needs continued attention
            item["latest_critical"] = last.is_critical
            critical.append(item)
        elif last.is_abnormal:
            item = _event_item(last)
            item["had_critical"] = False
            item["latest_critical"] = False
            abnormal.append(item)
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
            if not t.get("numeric", True):
                # non-numeric (text) metric: no value trend to show
                lines.append(f"- {t['label']}：{t['count']} 条记录" + (" ⚠ 最新值异常" if t.get("abnormal_last") else ""))
                continue
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
        lines.append("## 危急指标（请持续关注）")
        for e in events["critical"]:
            title = f"⛔ {e['label']}"
            if e.get("had_critical") and not e.get("latest_critical"):
                title += "（曾危急，需持续关注）"
            line = f"- {title}：{e['value']} {e['unit']}（最近 {e['date']}）"
            if e.get("context"):
                line += f"（来源：{e['context']}）"
            lines.append(line)
        lines.append("")
    if events.get("abnormal"):
        lines.append("## 异常指标（建议关注）")
        for e in events["abnormal"]:
            line = f"- ⚠ {e['label']}：{e['value']} {e['unit']}（最近 {e['date']}）"
            if e.get("context"):
                line += f"（来源：{e['context']}）"
            lines.append(line)
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
    latest_metrics = await _load_latest_metrics(db, member_id)
    diagnoses, medications = await _load_profile_events(db, member_id, period_start, period_end)

    stats = _build_stats(metrics)
    events = _build_events(metrics)
    content = _render_markdown(period, period_start, period_end, stats, events, diagnoses, medications)

    # Optional LLM enrichment — best-effort, never blocks generation.
    recheck_md = ""
    try:
        recheck_md, recheck_items = await _get_recheck_suggestions(period, stats, events, latest_metrics, period_start)
        if recheck_items:
            await _sync_recheck_tasks(db, member_id, recheck_items)
        content = await _maybe_enrich(period, content, stats, events, recheck_md)
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


async def _get_recheck_suggestions(
    period: str,
    stats: dict[str, Any],
    events: dict[str, Any],
    latest_metrics: dict[str, dict[str, Any]],
    period_start: date,
) -> tuple[str, list[dict[str, str]]]:
    """Get model-driven recheck suggestions; empty when no LLM is configured."""
    from app.providers.router import ModelRouter

    router = ModelRouter()
    provider = router.get_text_provider()
    if provider is None or not provider.is_configured:
        return "", []
    return await _model_recheck_suggestions(provider, period, stats, events, latest_metrics, period_start)


async def _maybe_enrich(
    period: str,
    rule_content: str,
    stats: dict[str, Any],
    events: dict[str, Any],
    recheck_md: str = "",
) -> str:
    """Optionally ask an LLM to add a natural-language interpretation."""
    from app.providers.router import ModelRouter
    from app.providers.base import Message

    router = ModelRouter()
    provider = router.get_text_provider()
    if provider is None or not provider.is_configured:
        return rule_content

    # Optional natural-language interpretation.
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
    parts = [rule_content]
    if recheck_md:
        parts.append("\n## 建议复查\n" + recheck_md)
    if resp and getattr(resp, "content", None):
        parts.append("\n## AI 解读\n" + resp.content.strip())
    return "\n".join(parts)


async def _model_recheck_suggestions(
    provider, period: str, stats: dict[str, Any], events: dict[str, Any],
    latest_metrics: dict[str, dict[str, Any]], period_start: date,
) -> tuple[str, list[dict[str, str]]]:
    """Ask the model which metrics need a recheck.

    Returns (markdown_summary, structured_items). The structured items are
    additionally persisted as health tasks so the plan-board can track them.
    """
    from app.providers.base import Message

    # Metrics already updated inside this period are covered by the trend section.
    updated = {t.get("metric") for t in stats.get("trends", [])}
    # Group not-updated metrics by check-category using REAL metric names (data layer),
    # so model shorthand like "HDL-C" cannot break categorization.
    cat_groups: dict[str, list[dict[str, Any]]] = {}
    for name, m in latest_metrics.items():
        if name in updated:
            continue
        cat = _metric_to_check_category(name)
        val = m.get("text_value") if m.get("text_value") is not None else m.get("value")
        cat_groups.setdefault(cat, []).append({
            "指标": m.get("label") or name,
            "上次值": f"{val} {m.get('unit','')}".strip(),
            "是否异常": m.get("is_abnormal"),
            "是否危急": m.get("is_critical"),
            "日期": (m.get("measured_at") or "")[:10],
        })
    if not cat_groups:
        return "本期所有指标均已更新，暂无需要复查的项目。", []

    system = (
        "你是家庭健康管家。以下是小结周期内\"未更新\"的指标，已按检查大类分组。"
        "结合医学知识判断：每个检查大类是否应当安排复查（距上次过久或上次结果异常需关注）。"
        "只输出需要复查的大类。"
        "严格只输出 JSON 数组，不要任何其他文字，字段为 指标/建议/理由，例如："
        "[{\"指标\":\"血脂四项\",\"建议\":\"建议1个月内复查\",\"理由\":\"甘油三酯/HDL异常，且超过半年未复查\"}]"
    )
    user_prompt = (
        f"本期起止：{period_start.isoformat()} 起\n"
        f"本期已更新指标：{sorted(updated)}\n"
        f"未更新指标（按检查大类分组）：{json.dumps(cat_groups, ensure_ascii=False)}\n"
        f"若某大类暂不需复查，不要输出该大类。"
    )
    try:
        resp = await provider.chat(
            [Message(role="system", content=system), Message(role="user", content=user_prompt)],
            temperature=0.2,
            max_tokens=600,
        )
        text = resp.content.strip() if resp and getattr(resp, "content", None) else ""
    except Exception:  # noqa: BLE001
        logger.exception("model recheck suggestion failed")
        text = ""

    items = _parse_recheck_json(text, list(cat_groups.keys()))
    if not items:
        return "本期暂无需要复查的指标。", []
    lines = [f"- ⏰ {i['指标']}：{i['建议']}（{i['理由']}）" for i in items]
    return "\n".join(lines), items


def _parse_recheck_json(text: str, candidates: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Best-effort parse of the model's recheck JSON; falls back to empty."""
    if not text:
        return []
    txt = text.strip()
    arr = txt[txt.find("[") : txt.rfind("]") + 1] if "[" in txt and "]" in txt else txt
    try:
        data = json.loads(arr)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    result = []
    for d in data:
        if isinstance(d, dict) and d.get("指标"):
            result.append({
                "指标": str(d.get("指标")),
                "建议": str(d.get("建议", "建议复查")),
                "理由": str(d.get("理由", "")),
            })
    return result


# 模型建议文案 → (复查天数, 优先级) 映射；默认 30 天复查
_RECHECK_DUE_HINTS: list[tuple[tuple[str, ...], int, str]] = [
    (("尽快", "立即", "马上", "现在就"), 0, "critical"),
    (("1周", "一周", "短期内"), 7, "high"),
    (("2周", "两周"), 14, "high"),
    (("1个月", "一个月", "1月", "一月"), 30, "normal"),
    (("2个月", "两个月", "1-2个月"), 60, "normal"),
    (("3个月", "三个月", "3-6个月"), 90, "normal"),
    (("半年", "6个月", "六个月"), 180, "normal"),
    (("1年", "一年"), 365, "normal"),
]


def _recheck_due(suggestion: str) -> tuple[int, str]:
    """Map a model's recheck suggestion to (days, priority); defaults to 30d/normal."""
    for hints, days, priority in _RECHECK_DUE_HINTS:
        if any(h in suggestion for h in hints):
            return days, priority
    return 30, "normal"


# 检查大类 → 关键词命中规则（顺序即优先级，前缀/类别名优先）
# 命中任一词即归入该大类。血脂类优先于“基础指标”，且血脂关键词要先于“生化”兜底。
_CHECK_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("血常规", ("血常规",)),
    ("尿常规", ("尿常规",)),
    ("肿瘤标志物", ("肿瘤标志物",)),
    ("血脂四项", ("甘油三酯", "胆固醇", "低密度脂蛋白", "高密度脂蛋白", "极低密度脂蛋白", "血脂", "triglyceride", "cholesterol", "lipoprotein")),
    ("肝功能", ("丙氨酸氨基转移酶", "天门冬氨酸氨基转移酶", "转氨酶", "胆红素", "白蛋白", "球蛋白")),
    ("肾功能", ("肌酐", "尿素", "尿酸", "肾小球滤过率")),
    ("血糖", ("fasting_glucose", "postmeal_glucose", "葡萄糖", "血糖")),
    ("甲状腺超声", ("甲状腺",)),
    ("胸部CT", ("肺", "胸部", "胸廓", "胸片")),
    ("血压", ("systolic_blood_pressure", "diastolic_blood_pressure", "血压")),
]

# 日常可自测/基础指标：归类为“基础指标”复查
_BASIC_METRICS: set[str] = {"bmi", "weight", "身高", "体重", "BMI", "心率", "heart_rate", "体温", "temperature"}


def _metric_to_check_category(metric_name: str) -> str:
    """Map a metric_name to a check-category for grouped recheck to-dos.

    Handles standard names, `lab:套餐:指标`, and `exam:类别:描述` formats.
    """
    if not metric_name:
        return "其他"
    name = metric_name
    # 剥离前缀以匹配类别名/关键词（保留套餐名：lab:血常规:血小板 → 血常规）
    body = name.split(":", 1)[-1] if ":" in name else name
    for category, kws in _CHECK_CATEGORY_KEYWORDS:
        if any(k.lower() in body.lower() for k in kws):
            return category
    if name in _BASIC_METRICS or body in _BASIC_METRICS:
        return "基础指标"
    return "其他"



async def _sync_recheck_tasks(
    db: AsyncSession, member_id: int, items: list[dict[str, str]]
) -> int:
    """Persist model-judged recheck items as plan-board health tasks (deduped).

    Uses task_service._add_task with a stable source_ref so re-running a summary
    does not create duplicate open tasks for the same metric. Returns count created.
    """
    from app.models.tasks import HealthTask
    from app.services import task_service

    # Group items by check-category so each category becomes ONE to-do.
    groups: dict[str, list[dict[str, str]]] = {}
    for it in items:
        metric = it.get("指标", "").strip()
        if not metric:
            continue
        mapped = _metric_to_check_category(metric)
        # 模型已按大类输出，通常可直接使用；若落到“其他”则保留模型给的大类名
        cat = mapped if mapped != "其他" else metric
        groups.setdefault(cat, []).append(it)

    # priority rank for picking the most urgent due among a group
    _PRIO_RANK = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    created = updated = 0
    for cat, grp in groups.items():
        # most urgent = min days; tie-break by higher priority
        best = min(grp, key=lambda it: (_recheck_due(it.get("建议", ""))[0], _PRIO_RANK.get(_recheck_due(it.get("建议", ""))[1], 2)))
        days, priority = _recheck_due(best.get("建议", ""))
        due = date.today() + timedelta(days=days) if days > 0 else date.today()
        title = f"复查{cat}"
        detail_lines = []
        for it in grp:
            m = it.get("指标", "").strip()
            reason = it.get("理由") or it.get("建议", "建议复查")
            detail_lines.append(f"{m}：{reason}")
        description = "；".join(detail_lines)
        source_ref = f"recheck:{cat}"

        existing = (await db.execute(
            select(HealthTask).where(
                HealthTask.member_id == member_id,
                HealthTask.source_ref == source_ref,
                HealthTask.status == "open",
            )
        )).scalars().first()
        if existing is not None:
            # 模型判断接管复查时间：校准已存在待办的到期日/优先级/说明
            existing.due_date = due
            existing.priority = priority
            existing.description = description
            updated += 1
            continue

        task = await task_service._add_task(
            db, member_id, "recheck",
            title=title,
            description=description,
            due_date=due,
            priority=priority,
            source_ref=source_ref,
            auto_generated=True,
        )
        if task is not None:
            created += 1
    return created
