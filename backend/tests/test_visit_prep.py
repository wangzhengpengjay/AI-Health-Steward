"""Tests for visit preparation service and department mapping."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.department_mapping import suggest_department, DEPARTMENTS


class TestSuggestDepartment:
    """Tests for the department suggestion rules."""

    def test_chest_pain_to_cardiology(self):
        dept, reason = suggest_department("胸痛胸闷", [])
        assert dept == "心内科"
        assert "胸痛" in reason

    def test_dizziness_with_hypertension_to_cardiology(self):
        """Cross-rule: 头晕 + 高血压 → 心内科 (not 神经内科)."""
        dept, reason = suggest_department("最近头晕", ["高血压3年"])
        assert dept == "心内科"
        assert "头晕" in reason

    def test_dizziness_without_hypertension_to_neurology(self):
        dept, _ = suggest_department("最近头晕", [])
        assert dept == "神经内科"

    def test_blood_sugar_to_endocrinology(self):
        dept, _ = suggest_department("血糖控制不好", ["糖尿病"])
        assert dept == "内分泌科"

    def test_diagnosis_fallback(self):
        """When complaint doesn't match, fall back to diagnosis."""
        dept, _ = suggest_department("想开点药", ["高血压"])
        assert dept == "心内科"

    def test_no_match_returns_none(self):
        dept, reason = suggest_department("随便看看", [])
        assert dept is None
        assert "手动" in reason

    def test_departments_list_not_empty(self):
        assert len(DEPARTMENTS) >= 10
        assert "心内科" in DEPARTMENTS


class TestVisitPrepService:
    """Tests for the visit prep generation service."""

    @pytest.mark.asyncio
    async def test_suggest_dept_calls_db(self):
        from app.services.visit_prep import suggest_dept

        db = AsyncMock()
        member = MagicMock()
        member.birth_date = None
        member.gender = "male"
        db.get = AsyncMock(return_value=member)
        db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))

        result = await suggest_dept(db, 1, "胸痛")
        assert result["department"] == "心内科"

    @pytest.mark.asyncio
    async def test_generate_visit_prep_returns_structure(self):
        from app.services.visit_prep import generate_visit_prep

        db = AsyncMock()
        member = MagicMock()
        member.birth_date = None
        member.gender = "male"
        db.get = AsyncMock(return_value=member)

        # Mock all DB queries to return empty
        mock_scalars = MagicMock(all=MagicMock(return_value=[]))
        mock_result = MagicMock(scalars=MagicMock(return_value=mock_scalars))
        db.execute = AsyncMock(return_value=mock_result)

        # Mock the model router and provider
        router = MagicMock()
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=MagicMock(
            content=json.dumps({
                "questions": ["问题1", "问题2"],
                "checklist": [{"item": "血压记录", "count": 5, "required": True}],
                "summary": "患者男，50岁。",
            })
        ))
        router.get_text_provider = MagicMock(return_value=provider)

        result = await generate_visit_prep(
            db=db,
            router=router,
            member_id=1,
            chief_complaint="头晕",
            department="心内科",
            selected_metrics=[],
        )

        assert result["department"] == "心内科"
        assert result["chief_complaint"] == "头晕"
        assert len(result["questions"]) == 2
        assert result["questions"][0] == "问题1"
        assert result["checklist"][0]["item"] == "血压记录"
        assert result["summary"] == "患者男，50岁。"
        assert result["metrics_trend"] == []

    @pytest.mark.asyncio
    async def test_generate_visit_prep_handles_bad_json(self):
        from app.services.visit_prep import generate_visit_prep

        db = AsyncMock()
        member = MagicMock()
        member.birth_date = None
        member.gender = "male"
        db.get = AsyncMock(return_value=member)

        mock_scalars = MagicMock(all=MagicMock(return_value=[]))
        mock_result = MagicMock(scalars=MagicMock(return_value=mock_scalars))
        db.execute = AsyncMock(return_value=mock_result)

        router = MagicMock()
        provider = AsyncMock()
        provider.chat = AsyncMock(return_value=MagicMock(
            content="This is not JSON"
        ))
        router.get_text_provider = MagicMock(return_value=provider)

        result = await generate_visit_prep(
            db=db,
            router=router,
            member_id=1,
            chief_complaint="头晕",
            department="心内科",
            selected_metrics=[],
        )

        # Should fall back gracefully
        assert result["questions"] == []
        assert result["checklist"] == []
        assert "This is not JSON" in result["summary"]
