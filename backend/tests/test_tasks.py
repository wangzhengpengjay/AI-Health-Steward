"""Tests for health task service (auto-generation + overview logic)."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import task_service
from app.models.tasks import HealthTask


def _mock_db():
    """Return an AsyncSession-like mock whose execute() returns empty scalars()."""
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    return db


def _task(**kw):
    defaults = dict(
        member_id=6,
        task_type="recheck",
        title="t",
        priority="normal",
        status="open",
        auto_generated=True,
    )
    defaults.update(kw)
    return HealthTask(**defaults)


@pytest.mark.asyncio
async def test_critical_metric_generates_immediate_task():
    db = _mock_db()
    task = await task_service.handle_metric_recorded(
        db, 6, "systolic_blood_pressure", True, True, 101
    )
    assert task is not None
    assert task.task_type == "recheck"
    assert task.priority == "critical"
    assert task.due_date == date.today()
    assert "血压" in task.title


@pytest.mark.asyncio
async def test_abnormal_metric_generates_recheck_in_30d():
    db = _mock_db()
    task = await task_service.handle_metric_recorded(
        db, 6, "fasting_glucose", True, False, 102
    )
    assert task is not None
    assert task.task_type == "recheck"
    assert task.priority == "normal"
    assert task.due_date == date.today() + timedelta(days=30)


@pytest.mark.asyncio
async def test_normal_metric_no_task():
    db = _mock_db()
    task = await task_service.handle_metric_recorded(
        db, 6, "fasting_glucose", False, False, 103
    )
    assert task is None


@pytest.mark.asyncio
async def test_duplicate_source_ref_dedup():
    db = _mock_db()
    db.execute.return_value.scalars.return_value.first.return_value = _task(source_ref="metric:101")
    task = await task_service.handle_metric_recorded(
        db, 6, "systolic_blood_pressure", True, True, 101
    )
    assert task is None  # deduped


@pytest.mark.asyncio
async def test_ongoing_medication_generates_reminder():
    db = _mock_db()
    task = await task_service.handle_medication_added(db, 6, "氨氯地平", 7, None)
    assert task is not None
    assert task.task_type == "medication"
    assert "氨氯地平" in task.title


@pytest.mark.asyncio
async def test_finished_medication_no_task():
    db = _mock_db()
    task = await task_service.handle_medication_added(db, 6, "头孢", 8, date(2026, 1, 1))
    assert task is None


@pytest.mark.asyncio
async def test_active_diagnosis_generates_followup():
    db = _mock_db()
    task = await task_service.handle_diagnosis_added(db, 6, "高血压", 3, "active")
    assert task is not None
    assert task.task_type == "followup"
    assert "高血压" in task.title


@pytest.mark.asyncio
async def test_past_diagnosis_no_task():
    db = _mock_db()
    task = await task_service.handle_diagnosis_added(db, 6, "感冒", 4, "cured")
    assert task is None


@pytest.mark.asyncio
async def test_checkup_generates_task():
    db = _mock_db()
    task = await task_service.handle_checkup_generated(db, 6, "预约CT", 2)
    assert task is not None
    assert task.task_type == "checkup"
    assert task.due_date == date.today() + timedelta(days=90)


def test_overview_counts_open_and_overdue():
    today = date.today()
    tasks = [
        _task(member_id=6, due_date=today - timedelta(days=1), priority="critical"),
        _task(member_id=6, due_date=today + timedelta(days=5), priority="normal"),
        _task(member_id=6, due_date=None, priority="normal"),
        _task(member_id=7, due_date=today + timedelta(days=2), priority="normal"),
    ]
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = tasks
    db.execute.side_effect = lambda *a, **k: result

    import asyncio
    res = asyncio.run(task_service.overview(db, [6, 7]))

    by_member = {r["member_id"]: r for r in res}
    assert by_member[6]["open"] == 3
    assert by_member[6]["overdue"] == 1
    assert by_member[6]["critical"] == 1
    assert by_member[7]["open"] == 1
    assert by_member[7]["overdue"] == 0
