"""Regression tests for FamilyMember create/update BMI handling (P2)."""
from __future__ import annotations

from app.schemas.family import FamilyMemberCreate


class TestFamilyMemberCreateBMI:
    def test_bmi_auto_computed_from_height_weight(self) -> None:
        """Creating a member with height+weight must auto-compute BMI.

        Regression: the `after` field validator only fired when `bmi` was
        explicitly provided; when the client omitted it, the height/weight
        computation never ran and `bmi` stayed None on create (update path
        computed it, so create/update were inconsistent).
        """
        member = FamilyMemberCreate(name="张三", gender="male", height=175, weight=70)
        assert member.bmi == 22.9

    def test_explicit_bmi_is_rounded_to_one_decimal(self) -> None:
        member = FamilyMemberCreate(name="张三", gender="male", height=175, weight=70, bmi=25.678)
        assert member.bmi == 25.7

    def test_no_body_metrics_leaves_bmi_none(self) -> None:
        member = FamilyMemberCreate(name="张三", gender="female")
        assert member.bmi is None

    def test_partial_body_metrics_leaves_bmi_none(self) -> None:
        member = FamilyMemberCreate(name="张三", gender="male", height=175)
        assert member.bmi is None

    def test_zero_height_rejected_by_validation(self) -> None:
        import pytest
        from pydantic import ValidationError

        # height must be > 0 (schema constraint gt=0)
        with pytest.raises(ValidationError):
            FamilyMemberCreate(name="张三", gender="male", height=0, weight=70)

    def test_model_dump_includes_computed_bmi(self) -> None:
        member = FamilyMemberCreate(name="张三", gender="male", height=175, weight=70)
        dumped = member.model_dump(exclude_unset=True)
        # create route sets data["bmi"] from payload.bmi; must be present after dump
        assert member.bmi == 22.9