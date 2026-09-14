"""Unit tests for AI consultation risk grading (P1-3).

Tests the S/A/B risk classifier used to gate medical advice output.
"""
import pytest
from app.services.consultation import ConsultationService


class TestRiskAssessment:
    def test_s_level_when_prescription_mentioned(self) -> None:
        # 开处方属 S 级（禁止）
        assert ConsultationService._assess_risk("帮我开个降压药", "我可以给您开处方") == "S"

    def test_s_level_when_medication_stop_advised(self) -> None:
        assert ConsultationService._assess_risk("我应该停药吗", "建议您停药") == "S"

    def test_a_level_when_drug_interaction_asked(self) -> None:
        assert ConsultationService._assess_risk("这两个药一起吃有相互作用吗", "可能存在相互作用，请遵医嘱") == "A"

    def test_a_level_when_chest_pain_mentioned(self) -> None:
        assert ConsultationService._assess_risk("我有点胸痛", "胸痛需警惕心脏问题，请尽快就医") == "A"

    def test_b_level_for_routine_advice(self) -> None:
        assert ConsultationService._assess_risk("高血压适合什么运动", "建议每周150分钟中等强度有氧运动") == "B"

    def test_empty_input_defaults_to_b(self) -> None:
        assert ConsultationService._assess_risk("", "") == "B"

    # -- false-positive regressions -------------------------------------
    # The classifier used to match keywords against user_message + reply
    # combined. An assistant answering a health question almost always writes
    # "诊断"/"用药", so virtually every reply was graded S ("禁止输出") once the
    # streaming endpoint started reporting the risk level.

    def test_clinical_vocabulary_in_reply_does_not_raise_level(self) -> None:
        assert ConsultationService._assess_risk(
            "我的血压正常吗？",
            "您的血压 120/80，属于正常范围。本建议不替代医生诊断，请遵医嘱用药。",
        ) == "B"

    def test_reply_mentioning_medication_is_not_s_level(self) -> None:
        assert ConsultationService._assess_risk(
            "高血压平时要注意什么",
            "建议低盐饮食、规律用药，并定期监测血压。",
        ) == "B"

    def test_report_review_is_not_s_level(self) -> None:
        assert ConsultationService._assess_risk(
            "帮我看看这份体检报告",
            "报告显示血脂偏高，诊断建议：复查血脂四项。",
        ) == "B"

    # -- genuine emergency wording in the reply --------------------------

    def test_reply_escalating_to_urgent_care_is_a_level(self) -> None:
        assert ConsultationService._assess_risk(
            "血糖有点高",
            "该数值已达到危急值，请立即就医。",
        ) == "A"

    def test_user_emergency_symptom_is_a_level(self) -> None:
        assert ConsultationService._assess_risk("我突然喘不上气", "请尽快处理。") == "A"

    # -- prescription requests are still S -------------------------------

    def test_drug_class_between_verb_and_object_is_s_level(self) -> None:
        """Chinese inserts the drug class: 帮我开点降压药."""
        assert ConsultationService._assess_risk("帮我开点降压药", "我不能开药。") == "S"

    def test_asking_what_to_take_is_s_level(self) -> None:
        assert ConsultationService._assess_risk("我该吃什么药", "请遵医嘱。") == "S"


@pytest.mark.asyncio
async def test_execute_tool_call_commits_after_success() -> None:
    """Ensure a successful tool execution persists via commit(), not just flush().

    Regression: SSE streaming /chat/stream runs tools inside an async event
    generator; the request-dependency commit is unreliable there, so flushed
    records (chat_extract metrics) were silently rolled back and lost.
    """
    from unittest.mock import AsyncMock, MagicMock

    tool = MagicMock()
    tool.name = "extract_and_save"
    tool.execute = AsyncMock(return_value={"saved": True, "record_id": 1})

    registry = MagicMock()
    registry.get_tool = MagicMock(return_value=tool)

    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()

    svc = ConsultationService.__new__(ConsultationService)
    svc.tools = registry
    svc.db = db

    call = MagicMock()
    call.name = "extract_and_save"
    call.arguments = '{"data_type": "metric", "metric_name": "heart_rate", "value": 75}'

    result = await svc._execute_tool_call(call, 6)

    tool.execute.assert_awaited_once()
    db.commit.assert_awaited_once()
    db.flush.assert_not_awaited()
    db.rollback.assert_not_awaited()
    assert result == {"saved": True, "record_id": 1}


@pytest.mark.asyncio
async def test_execute_tool_call_rolls_back_on_failure() -> None:
    """On tool failure the transaction must roll back and a friendly error returned."""
    from unittest.mock import AsyncMock, MagicMock

    tool = MagicMock()
    tool.name = "extract_and_save"
    tool.execute = AsyncMock(side_effect=RuntimeError("boom"))

    registry = MagicMock()
    registry.get_tool = MagicMock(return_value=tool)

    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    svc = ConsultationService.__new__(ConsultationService)
    svc.tools = registry
    svc.db = db

    call = MagicMock()
    call.name = "extract_and_save"
    call.arguments = '{}'

    result = await svc._execute_tool_call(call, 6)

    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
    assert result["error"] == "工具执行失败: boom"


# ---------------------------------------------------------------------------
# 方案A: 同轮收缩压+舒张压强制统一 measured_at (防前端拆成残缺记录)
# ---------------------------------------------------------------------------
from app.providers.base import ToolCall
import json


def _bp_call(metric_name: str, measured_at: str | None) -> ToolCall:
    args = {"data_type": "metric", "metric_name": metric_name, "value": 100}
    if measured_at is not None:
        args["measured_at"] = measured_at
    return ToolCall(id=metric_name, name="extract_and_save", arguments=json.dumps(args))


class TestBpTimestampAlignment:
    def test_same_round_systolic_diastolic_share_timestamp(self) -> None:
        """同一轮同时提取收缩压+舒张压时, 两者 measured_at 必须一致. """
        sys = _bp_call("systolic_blood_pressure", "2026-07-22T08:00:00")
        dia = _bp_call("diastolic_blood_pressure", "2026-07-22T08:00:30")  # 时间戳不一致
        ConsultationService._align_bp_measured_at([sys, dia])
        a1 = json.loads(sys.arguments)
        a2 = json.loads(dia.arguments)
        assert a1["measured_at"] == a2["measured_at"]
        # 优先取先出现的已给时间戳
        assert a1["measured_at"] == "2026-07-22T08:00:00"

    def test_single_side_not_modified(self) -> None:
        """只有单侧血压(如只提收缩压)时不做对齐, 保留原值. """
        sys = _bp_call("systolic_blood_pressure", "2026-07-22T08:00:00")
        ConsultationService._align_bp_measured_at([sys])
        assert json.loads(sys.arguments)["measured_at"] == "2026-07-22T08:00:00"

    def test_missing_timestamp_filled_with_now(self) -> None:
        """同轮双侧血压均无 measured_at 时, 统一填充当前时间. """
        sys = _bp_call("systolic_blood_pressure", None)
        dia = _bp_call("diastolic_blood_pressure", None)
        ConsultationService._align_bp_measured_at([sys, dia])
        a1 = json.loads(sys.arguments)["measured_at"]
        a2 = json.loads(dia.arguments)["measured_at"]
        assert a1 and a2
        assert a1 == a2

    def test_two_measurements_in_one_round_keep_separate_timestamps(self) -> None:
        """一条消息报告两次血压时, 两组测量必须各自对齐, 不能压成同一时间点.

        Regression: alignment used to run across every blood-pressure call in the
        round, so "早上 130/85, 晚上 145/95" collapsed to one timestamp and the
        systolic/diastolic values were paired wrongly by the frontend.
        """
        sys1 = _bp_call("systolic_blood_pressure", "2026-07-22T08:00:00")
        dia1 = _bp_call("diastolic_blood_pressure", "2026-07-22T08:00:00")
        sys2 = _bp_call("systolic_blood_pressure", "2026-07-22T20:00:00")
        dia2 = _bp_call("diastolic_blood_pressure", "2026-07-22T20:00:00")
        ConsultationService._align_bp_measured_at([sys1, dia1, sys2, dia2])

        morning = json.loads(sys1.arguments)["measured_at"]
        assert morning == json.loads(dia1.arguments)["measured_at"] == "2026-07-22T08:00:00"
        evening = json.loads(sys2.arguments)["measured_at"]
        assert evening == json.loads(dia2.arguments)["measured_at"] == "2026-07-22T20:00:00"
        assert morning != evening

    def test_two_measurements_missing_timestamps_do_not_collapse(self) -> None:
        sys1 = _bp_call("systolic_blood_pressure", None)
        dia1 = _bp_call("diastolic_blood_pressure", None)
        sys2 = _bp_call("systolic_blood_pressure", None)
        dia2 = _bp_call("diastolic_blood_pressure", None)
        ConsultationService._align_bp_measured_at([sys1, dia1, sys2, dia2])
        t1 = json.loads(sys1.arguments)["measured_at"]
        t2 = json.loads(sys2.arguments)["measured_at"]
        assert t1 and t2
        # Each pair is internally consistent.
        assert t1 == json.loads(dia1.arguments)["measured_at"]
        assert t2 == json.loads(dia2.arguments)["measured_at"]

    def test_non_bp_metric_not_modified(self) -> None:
        """非血压指标(如血糖)不受影响. """
        glu = _bp_call("fasting_glucose", "2026-07-22T08:00:00")
        ConsultationService._align_bp_measured_at([glu])
        assert json.loads(glu.arguments)["measured_at"] == "2026-07-22T08:00:00"