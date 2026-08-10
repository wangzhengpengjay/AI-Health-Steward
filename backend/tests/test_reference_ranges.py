"""Unit tests for age-aware reference ranges (P0-2 / P1-3)."""
from app.core.reference_ranges import resolve_reference_range


class TestResolveReferenceRange:
    def test_adult_glucose(self) -> None:
        assert resolve_reference_range("fasting_glucose", 40) == (3.9, 6.1)

    def test_child_glucose_uses_pediatric_range(self) -> None:
        assert resolve_reference_range("fasting_glucose", 10) == (3.3, 6.1)

    def test_child_bp_upper_bound_lower_than_adult(self) -> None:
        # 儿童收缩压上限应低于成人（140 → 120）
        child_lo, child_hi = resolve_reference_range("systolic_blood_pressure", 8)
        adult_lo, adult_hi = resolve_reference_range("systolic_blood_pressure", 40)
        assert child_hi < adult_hi

    def test_child_heart_rate_higher_than_adult(self) -> None:
        # 儿童心率下限/上限高于成人
        c_lo, c_hi = resolve_reference_range("heart_rate", 6)
        a_lo, a_hi = resolve_reference_range("heart_rate", 40)
        assert c_lo > a_lo and c_hi > a_hi

    def test_no_age_falls_back_to_adult(self) -> None:
        assert resolve_reference_range("heart_rate", None) == (60, 100)

    def test_explicit_range_wins_over_default(self) -> None:
        assert resolve_reference_range(
            "fasting_glucose", 10, explicit_lower=2.0, explicit_upper=8.0
        ) == (2.0, 8.0)

    def test_unknown_metric_returns_none(self) -> None:
        assert resolve_reference_range("some_unknown_metric", 40) == (None, None)

    def test_hdl_has_lower_bound_only(self) -> None:
        lo, hi = resolve_reference_range("hdl_cholesterol", 40)
        assert lo is not None and hi is None