"""Unit tests for AI consultation risk grading (P1-3).

Tests the S/A/B risk classifier used to gate medical advice output.
"""
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