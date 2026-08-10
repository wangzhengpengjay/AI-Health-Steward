"""Tests for health summary service (rule-based stats + markdown rendering)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.health import MetricRecord
from app.services import summary_service


def _metric(name, value, measured_at, abnormal=False, critical=False, unit="", lo=None, hi=None, text_value=None, context=""):
    return MetricRecord(
        member_id=6,
        metric_name=name,
        value=value,
        text_value=text_value,
        unit=unit,
        is_abnormal=abnormal,
        is_critical=critical,
        reference_lower=lo,
        reference_upper=hi,
        measured_at=measured_at,
        context=context or None,
    )


def _build_stats(metrics):
    return summary_service._build_stats(metrics)


def test_trend_up_flat_and_delta():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("fasting_glucose", 5.0, now, unit="mmol/L"),
        _metric("fasting_glucose", 6.0, now.replace(day=2), unit="mmol/L"),
    ]
    stats = _build_stats(metrics)
    t = stats["trends"][0]
    assert t["metric"] == "fasting_glucose"
    assert t["first"] == 5.0
    assert t["last"] == 6.0
    assert t["delta"] == 1.0
    assert t["direction"] == "up"
    assert t["count"] == 2


def test_trend_down():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("weight", 80.0, now, unit="kg"),
        _metric("weight", 78.0, now.replace(day=2), unit="kg"),
    ]
    t = _build_stats(metrics)["trends"][0]
    assert t["direction"] == "down"


def test_all_metrics_included_in_stats():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("lab:血常规:白细胞计数", 10.0, now, unit="10^9/L"),
        _metric("exam:B超:肝囊肿", 1.0, now, text_value="有", abnormal=True),
        _metric("heart_rate", 70.0, now, unit="bpm"),
    ]
    stats = _build_stats(metrics)
    names = {t["metric"] for t in stats["trends"]}
    assert names == {"lab:血常规:白细胞计数", "exam:B超:肝囊肿", "heart_rate"}
    # numeric lab metric gets a real trend
    lab = next(t for t in stats["trends"] if t["metric"] == "lab:血常规:白细胞计数")
    assert lab["numeric"] is True and lab["first"] == 10.0
    # non-numeric exam metric is counted but has no meaningless numeric trend
    exam = next(t for t in stats["trends"] if t["metric"] == "exam:B超:肝囊肿")
    assert exam["numeric"] is False and exam["count"] == 1 and exam["first"] is None


def test_lab_exam_events_include_context_and_text_value():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("lab:肝功能:谷丙转氨酶", 80.0, now, abnormal=True, unit="U/L", context="血生化"),
        _metric("exam:眼底检查:视网膜病变", 1.0, now, text_value="阳性", abnormal=True, context="眼底检查"),
        _metric("heart_rate", 200.0, now, critical=True, unit="bpm"),
    ]
    events = summary_service._build_events(metrics)
    abnormal = events["abnormal"]
    assert len(abnormal) == 2
    # text value preferred, context attached
    exam = next(e for e in abnormal if e["metric"].startswith("exam:"))
    assert exam["value"] == "阳性" and exam["context"] == "眼底检查"
    lab = next(e for e in abnormal if e["metric"].startswith("lab:"))
    assert lab["value"] == 80.0 and lab["context"] == "血生化"
    assert events["critical"][0]["metric"] == "heart_rate"


def test_render_markdown_shows_context_and_non_numeric():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("lab:血常规:白细胞计数", 12.5, now, abnormal=True, unit="10^9/L", context="血常规"),
        _metric("exam:尿检:蛋白尿", 1.0, now, text_value="阳性", abnormal=True, context="尿常规"),
        _metric("fasting_glucose", 5.0, now, unit="mmol/L"),
    ]
    stats = summary_service._build_stats(metrics)
    events = summary_service._build_events(metrics)
    md = summary_service._render_markdown("monthly", date(2026, 8, 1), date(2026, 8, 10), stats, events, [], [])
    assert "白细胞计数" in md
    assert "来源：血常规" in md
    assert "来源：尿常规" in md
    assert "蛋白尿" in md


def test_events_collect_abnormal_and_critical():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("fasting_glucose", 7.5, now, abnormal=True, unit="mmol/L"),
        _metric("systolic_blood_pressure", 200.0, now, critical=True, unit="mmHg"),
        _metric("heart_rate", 70.0, now, unit="bpm"),
    ]
    events = summary_service._build_events(metrics)
    assert len(events["abnormal"]) == 1
    assert len(events["critical"]) == 1
    assert events["critical"][0]["metric"] == "systolic_blood_pressure"


def test_render_markdown_structure():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("fasting_glucose", 5.0, now, unit="mmol/L"),
        _metric("fasting_glucose", 6.5, now.replace(day=2), abnormal=True, unit="mmol/L"),
    ]
    stats = summary_service._build_stats(metrics)
    events = summary_service._build_events(metrics)
    md = summary_service._render_markdown("monthly", date(2026, 8, 1), date(2026, 8, 10), stats, events, [], [])
    assert "月报健康小结" in md
    assert "空腹血糖" in md
    assert "异常指标" in md
    assert "建议" in md
    assert "不构成医疗建议" in md


def test_render_markdown_no_data_peaceful():
    md = summary_service._render_markdown("weekly", date(2026, 8, 1), date(2026, 8, 7), {"trends": []}, {"abnormal": [], "critical": []}, [], [])
    assert "指标整体平稳" in md


def test_generate_summary_commits():
    from unittest.mock import AsyncMock, MagicMock, patch

    db = AsyncMock()
    db.add = MagicMock()

    async def _execute(stmt):
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        return res

    db.execute.side_effect = _execute
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    with patch.object(summary_service, "_maybe_enrich", AsyncMock(return_value="md")):
        import asyncio
        s = asyncio.run(summary_service.generate_summary(db, 6, "monthly"))
    assert s.member_id == 6
    assert s.period == "monthly"
    assert s.period_start is not None
    assert s.period_end is not None
    assert s.content == "md"
    assert db.add.called


def test_events_aggregate_by_metric_latest_only():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        # bmi: latest is normal -> should NOT appear in abnormal (historical abnormality not re-flagged)
        _metric("bmi", 26.3, now, abnormal=True),
        _metric("bmi", 24.0, now.replace(day=2), abnormal=False),
        # fasting_glucose: latest still abnormal -> appears once
        _metric("fasting_glucose", 7.5, now, abnormal=True, unit="mmol/L"),
        _metric("fasting_glucose", 7.8, now.replace(day=2), abnormal=True, unit="mmol/L"),
        # systolic: ever critical, latest normal -> stays in critical (continued attention)
        _metric("systolic_blood_pressure", 200.0, now, critical=True, unit="mmHg"),
        _metric("systolic_blood_pressure", 130.0, now.replace(day=2), unit="mmHg"),
    ]
    events = summary_service._build_events(metrics)
    # abnormal: only fasting_glucose (latest abnormal), one row
    abnormal_metrics = {e["metric"] for e in events["abnormal"]}
    assert abnormal_metrics == {"fasting_glucose"}
    assert len(events["abnormal"]) == 1
    # critical: systolic kept for continued attention, latest no longer critical
    crit = events["critical"]
    assert len(crit) == 1 and crit[0]["metric"] == "systolic_blood_pressure"
    assert crit[0]["had_critical"] is True and crit[0]["latest_critical"] is False
    # bmi not reported at all
    reported = abnormal_metrics | {e["metric"] for e in events["critical"]}
    assert "bmi" not in reported


def test_parse_recheck_json_valid():
    from app.services.summary_service import _parse_recheck_json

    text = '[{"指标":"甘油三酯","建议":"建议1个月内复查","理由":"上次异常"}]'
    items = _parse_recheck_json(text, [])
    assert len(items) == 1 and items[0]["指标"] == "甘油三酯"


def test_parse_recheck_json_embedded_and_invalid():
    from app.services.summary_service import _parse_recheck_json

    embedded = '好的，结果如下：[{"指标":"谷丙转氨酶","建议":"建议复查","理由":"偏高"}] 以上就是。'
    items = _parse_recheck_json(embedded, [])
    assert len(items) == 1 and items[0]["指标"] == "谷丙转氨酶"
    assert _parse_recheck_json("", []) == []
    assert _parse_recheck_json("无法解析", []) == []


@pytest.mark.asyncio
async def test_load_latest_metrics_takes_newest_per_metric():
    from unittest.mock import AsyncMock, MagicMock

    from app.services.summary_service import _load_latest_metrics

    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    older = datetime(2025, 7, 26, tzinfo=timezone.utc)
    # mock returns rows in the same order SQL's order_by(measured_at.desc()) would
    recs = [
        _metric("triglycerides", 1.5, now, abnormal=False, unit="mmol/L"),
        _metric("triglycerides", 2.05, older, abnormal=True, unit="mmol/L"),
        _metric("heart_rate", 70.0, now, unit="bpm"),
    ]
    scalars_result = MagicMock()
    scalars_result.all.return_value = recs
    result_obj = MagicMock()
    result_obj.scalars.return_value = scalars_result
    db = AsyncMock()
    db.execute.return_value = result_obj

    latest = await _load_latest_metrics(db, 6)
    assert latest["triglycerides"]["value"] == 1.5
    assert latest["triglycerides"]["is_abnormal"] is False
    assert latest["heart_rate"]["value"] == 70.0
    assert len(latest) == 2


def test_recheck_due_mapping():
    from app.services.summary_service import _recheck_due

    # 尽快/立即 -> 当天 critical
    days, prio = _recheck_due("建议尽快复查")
    assert days == 0 and prio == "critical"
    # 1个月内 -> 30 天
    days, prio = _recheck_due("建议1个月内复查")
    assert days == 30 and prio == "normal"
    # 3个月 -> 90 天
    days, prio = _recheck_due("建议3个月内复查")
    assert days == 90
    # 未匹配 -> 默认 30 天
    days, prio = _recheck_due("请关注")
    assert days == 30 and prio == "normal"


@pytest.mark.asyncio
async def test_sync_recheck_tasks_creates_new(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from app.models.tasks import HealthTask
    from app.services import summary_service


    created_rows: list[HealthTask] = []
    db = AsyncMock()
    # db.execute -> empty (no existing open task) so it should create
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute.return_value = result

    from app.services import task_service as ts

    async def fake_add_task(db_, member_id, task_type, title, description=None, due_date=None, priority="normal", source_ref=None, auto_generated=True):
        t = HealthTask(
            member_id=member_id, task_type=task_type, title=title,
            description=description, priority=priority, due_date=due_date,
            status="open", source_ref=source_ref, auto_generated=auto_generated,
        )
        created_rows.append(t)
        return t

    try:
        orig = ts._add_task
    except AttributeError:
        orig = None
    ts._add_task = fake_add_task
    try:
        items = [{"指标": "甘油三酯", "建议": "建议尽快复查", "理由": "上次异常"}]
        n = await summary_service._sync_recheck_tasks(db, 6, items)
        assert n == 1
        assert created_rows[0].due_date == date.today()
        assert created_rows[0].priority == "critical"
    finally:
        if orig is not None:
            ts._add_task = orig


@pytest.mark.asyncio
async def test_sync_recheck_tasks_updates_existing():
    from unittest.mock import AsyncMock, MagicMock

    from app.models.tasks import HealthTask
    from app.services import summary_service

    existing = HealthTask(
        member_id=6, task_type="recheck", title="复查甘油三酯",
        priority="normal", due_date=date(2026, 9, 9), status="open",
        source_ref="recheck:甘油三酯", auto_generated=True,
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = existing
    db.execute.return_value = result

    items = [{"指标": "甘油三酯", "建议": "建议3个月内复查", "理由": "偏高"}]
    n = await summary_service._sync_recheck_tasks(db, 6, items)
    # existing updated, not re-created
    assert n == 0
    assert existing.due_date == date.today() + timedelta(days=90)
    assert existing.description == "偏高"
