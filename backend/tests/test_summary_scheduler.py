"""Tests for summary scheduler (period detection) and empty-summary behavior."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import summary_scheduler
from app.services import summary_service


# ---------------------------------------------------------------------------
# Period detection
# ---------------------------------------------------------------------------

def test_due_periods_monday_weekly():
    # 2026-08-10 is a Monday -> previous week's weekly summary is due
    due = summary_scheduler._due_periods(date(2026, 8, 10))
    assert ("weekly", date(2026, 8, 3), date(2026, 8, 9)) in due


def test_due_periods_first_of_month_monthly():
    due = summary_scheduler._due_periods(date(2026, 8, 1))
    assert ("monthly", date(2026, 7, 1), date(2026, 7, 31)) in due


def test_due_periods_new_year_annual():
    due = summary_scheduler._due_periods(date(2026, 1, 1))
    assert ("annual", date(2025, 1, 1), date(2025, 12, 31)) in due


def test_due_periods_first_monday_both():
    # 2026-06-01 is a Monday AND the 1st -> weekly + monthly both due
    due = summary_scheduler._due_periods(date(2026, 6, 1))
    periods = {p for p, _, _ in due}
    assert periods == {"weekly", "monthly"}


def test_due_periods_plain_day_empty():
    # 2026-08-11 is a Tuesday, day 11 -> nothing due
    assert summary_scheduler._due_periods(date(2026, 8, 11)) == []


def test_due_periods_year_start_monthly_and_weekly():
    # 2026-01-01 is a Thursday (weekday=3) -> only annual; verify no weekly
    due = summary_scheduler._due_periods(date(2026, 1, 1))
    periods = {p for p, _, _ in due}
    assert "annual" in periods
    assert "weekly" not in periods


def test_previous_week_boundaries():
    s, e = summary_scheduler._previous_week(date(2026, 8, 10))
    assert s == date(2026, 8, 3) and e == date(2026, 8, 9)


def test_previous_month_boundaries():
    s, e = summary_scheduler._previous_month(date(2026, 8, 1))
    assert s == date(2026, 7, 1) and e == date(2026, 7, 31)


# ---------------------------------------------------------------------------
# Idempotency helper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_exists_true_when_present():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = 42
    db.execute.return_value = result
    assert await summary_scheduler._summary_exists(db, 6, "monthly", date(2026, 7, 1), date(2026, 7, 31)) is True


@pytest.mark.asyncio
async def test_summary_exists_false_when_absent():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute.return_value = result
    assert await summary_scheduler._summary_exists(db, 6, "monthly", date(2026, 7, 1), date(2026, 7, 31)) is False


# ---------------------------------------------------------------------------
# Empty-period -> no-LLM default page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_has_substantive_content_metric_present():
    db = AsyncMock()
    metrics = [MagicMock()]
    assert await summary_service._has_substantive_content(db, 6, metrics, {"abnormal": [], "critical": []}, [], []) is True


@pytest.mark.asyncio
async def test_has_substantive_content_empty_returns_false():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None  # no open tasks
    db.execute.return_value = result
    assert await summary_service._has_substantive_content(db, 6, [], {"abnormal": [], "critical": []}, [], []) is False


@pytest.mark.asyncio
async def test_has_substantive_content_open_task_true():
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = 1  # open task exists
    db.execute.return_value = result
    assert await summary_service._has_substantive_content(db, 6, [], {"abnormal": [], "critical": []}, [], []) is True


def test_render_empty_contains_no_update_notice():
    md = summary_service._render_empty("monthly", date(2026, 7, 1), date(2026, 7, 31))
    assert "月报健康小结" in md
    assert "本周期无更新" in md
    assert "LLM" not in md
