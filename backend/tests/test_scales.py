"""Tests for risk assessment scales (scoring, tiers, tool, frequency control)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core import assessment_scales
from app.core.assessment_scales import get_scale, list_scales
from app.services.tools.assess_scale import AssessScaleTool
from app.api.routes.scales import _should_push


def test_all_scales_registered():
    codes = {s.code for s in list_scales()}
    assert {"phq9", "gad7", "diabetes", "ascvd"} <= codes


def test_phq9_min_no_depression():
    s = get_scale("phq9")
    answers = {f"phq{i}": 0 for i in range(1, 10)}
    total, detail = s.score(answers)
    assert total == 0
    assert detail["tier"]["level"] == "none"


def test_phq9_severe():
    s = get_scale("phq9")
    answers = {f"phq{i}": 3 for i in range(1, 10)}
    total, detail = s.score(answers)
    assert total == 27
    assert detail["tier"]["level"] == "severe"


def test_gad7_tier_boundaries():
    s = get_scale("gad7")
    answers = {f"gad{i}": 0 for i in range(1, 8)}
    _, d = s.score(answers)
    assert d["tier"]["level"] == "none"
    answers = {f"gad{i}": 3 for i in range(1, 8)}
    _, d = s.score(answers)
    assert d["tier"]["level"] == "severe"


def test_diabetes_high():
    s = get_scale("diabetes")
    answers = {"age": 3, "bmi": 3, "family": 2, "exercise": 2,
               "diet": 2, "hypertension": 1, "gestational": 0, "thirst": 2}
    total, detail = s.score(answers)
    assert total >= 8
    assert detail["tier"]["level"] == "high"


def test_ascvd_low_and_high():
    s = get_scale("ascvd")
    low = {"age": 0, "gender": 0, "systolic": 0, "ldl": 0, "hdl": 0,
           "smoke": 0, "diabetes": 0, "family": 0}
    total, d = s.score(low)
    assert d["tier"]["level"] == "low"
    high = {"age": 3, "gender": 1, "systolic": 3, "ldl": 3, "hdl": 2,
            "smoke": 2, "diabetes": 2, "family": 1}
    total, d = s.score(high)
    assert d["tier"]["level"] == "high"


def test_assess_scale_tool_questions_mode():
    # questions path uses get_scale to return questions; validate via scale directly
    scale = get_scale("phq9")
    assert len(scale.questions) == 9
    assert "options" in scale.questions[0]


def test_assess_scale_tool_result():
    from unittest.mock import AsyncMock, MagicMock
    import asyncio

    tool = AssessScaleTool()
    db = AsyncMock()

    async def _execute(stmt):
        res = MagicMock()
        res.scalars.return_value.first.return_value = None
        return res

    db.execute.side_effect = _execute
    db.flush = AsyncMock()

    result = asyncio.run(tool.execute(db, 6, scale_code="phq9",
                          answers={"phq1": 3, "phq2": 3, "phq3": 3, "phq4": 3,
                                   "phq5": 3, "phq6": 3, "phq7": 3, "phq8": 3, "phq9": 3}))
    assert result["ok"] is True
    assert result["mode"] == "result"
    assert result["risk_level"] == "severe"
    assert db.add.called


def test_should_push_frequency_control():
    now = datetime.now(timezone.utc)

    # None -> push
    assert _should_push(None) == (True, None) or _should_push(None)[0] is True

    # low risk, recent (<180d) -> no push
    recent_low = type("R", (), {"risk_level": "low", "created_at": now - timedelta(days=10)})()
    push, reason = _should_push(recent_low)
    assert push is False

    # low risk, old (>180d) -> push
    recent_low_old = type("R", (), {"risk_level": "low", "created_at": now - timedelta(days=200)})()
    push, _ = _should_push(recent_low_old)
    assert push is True

    # high risk, recent (<7d) -> no push (see doctor)
    recent_high = type("R", (), {"risk_level": "high", "created_at": now - timedelta(days=2)})()
    push, _ = _should_push(recent_high)
    assert push is False

    # high risk, old (>7d) -> push
    recent_high_old = type("R", (), {"risk_level": "high", "created_at": now - timedelta(days=30)})()
    push, _ = _should_push(recent_high_old)
    assert push is True
