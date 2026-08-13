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
    assert {"phq9", "gad7", "diabetes", "ascvd", "isi", "hypertension", "dyslipidemia", "ad8", "stroke"} <= codes


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


def test_result_out_has_scale_name_and_answers():
    from app.api.routes.scales import _result_out
    from app.models.assessments import ScaleResult

    from datetime import datetime, timezone
    r = ScaleResult(
        id=99, member_id=6, scale_code="phq9",
        answers='{"phq1": 2.0, "phq2": 1.0}', total_score=3.0,
        risk_level="none", risk_label="无明显抑郁",
        created_at=datetime.now(timezone.utc),
    )
    out = _result_out(r)
    assert out.scale_name == "抑郁自评量表（PHQ-9）"
    assert '"phq1"' in out.answers


# ---- 新增量表边界测试 ----

def test_isi_no_insomnia_and_severe():
    s = get_scale("isi")
    # 全部选 0 → 无明显失眠
    answers_low = {f"isi{i}": 0 for i in range(1, 8)}
    total, d = s.score(answers_low)
    assert total == 0
    assert d["tier"]["level"] == "none"
    # 全部选 4 → 重度失眠
    answers_high = {f"isi{i}": 4 for i in range(1, 8)}
    total, d = s.score(answers_high)
    assert total == 28
    assert d["tier"]["level"] == "severe"


def test_hypertension_low_and_high():
    s = get_scale("hypertension")
    low = {"age": 0, "family": 0, "salt": 0, "weight": 0,
           "alcohol": 0, "exercise": 0, "stress": 0, "bp": 0}
    total, d = s.score(low)
    assert d["tier"]["level"] == "low"
    high = {"age": 3, "family": 2, "salt": 2, "weight": 2,
            "alcohol": 2, "exercise": 2, "stress": 2, "bp": 2}
    total, d = s.score(high)
    assert d["tier"]["level"] == "high"


def test_dyslipidemia_low_and_high():
    s = get_scale("dyslipidemia")
    low = {"age": 0, "family": 0, "weight": 0, "smoke": 0,
           "alcohol": 0, "exercise": 0, "diet": 0}
    total, d = s.score(low)
    assert d["tier"]["level"] == "low"
    high = {"age": 3, "family": 2, "weight": 2, "smoke": 2,
            "alcohol": 2, "exercise": 2, "diet": 2}
    total, d = s.score(high)
    assert d["tier"]["level"] == "high"


def test_ad8_normal_and_positive():
    s = get_scale("ad8")
    # 全部 0 → 未见明显认知变化
    answers_normal = {f"ad8_{i}": 0 for i in range(1, 9)}
    total, d = s.score(answers_normal)
    assert total == 0
    assert d["tier"]["level"] == "none"
    # ≥2 项有变化 → 可疑认知障碍
    answers_positive = {f"ad8_{i}": 1 for i in range(1, 9)}
    total, d = s.score(answers_positive)
    assert total == 8
    assert d["tier"]["level"] == "high"


def test_stroke_low_and_high():
    s = get_scale("stroke")
    low = {"bp": 0, "afib": 0, "smoke": 0, "lipid": 0,
           "diabetes": 0, "exercise": 0, "weight": 0, "history": 0}
    total, d = s.score(low)
    assert d["tier"]["level"] == "low"
    high = {"bp": 3, "afib": 3, "smoke": 2, "lipid": 2,
            "diabetes": 2, "exercise": 1, "weight": 1, "history": 3}
    total, d = s.score(high)
    assert d["tier"]["level"] == "high"
