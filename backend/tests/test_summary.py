"""Tests for health summary service (rule-based stats + markdown rendering)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.health import MetricRecord
from app.services import summary_service


def _metric(name, value, measured_at, abnormal=False, critical=False, unit="", lo=None, hi=None):
    return MetricRecord(
        member_id=6,
        metric_name=name,
        value=value,
        unit=unit,
        is_abnormal=abnormal,
        is_critical=critical,
        reference_lower=lo,
        reference_upper=hi,
        measured_at=measured_at,
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


def test_report_metrics_excluded_from_stats():
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    metrics = [
        _metric("lab:血常规", 10.0, now),
        _metric("exam:B超", 1.0, now),
        _metric("heart_rate", 70.0, now, unit="bpm"),
    ]
    stats = _build_stats(metrics)
    assert len(stats["trends"]) == 1
    assert stats["trends"][0]["metric"] == "heart_rate"


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
