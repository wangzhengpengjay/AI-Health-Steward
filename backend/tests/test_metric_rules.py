"""Regression tests for server-side metric reference-range rules.

Covers:
- one-sided ranges (hdl_cholesterol) being flagged abnormal
- explicit single-sided bounds no longer disabling detection
- the previously missing glucose metrics (random / postmeal_1h / bedtime)
- clinical critical thresholds and the plausibility guard
"""
from __future__ import annotations

import pytest

from app.core.reference_ranges import (
    ADULT_RANGES,
    CRITICAL_THRESHOLDS,
    evaluate_metric,
    is_abnormal_value,
    is_critical_value,
    plausible_range_error,
    resolve_reference_range,
)

ADULT = 40
CHILD = 10


def test_all_prompt_emitted_glucose_metrics_have_ranges():
    """Every metric the extraction prompt can emit must have a reference range.

    random_glucose / postmeal_1h_glucose / bedtime_glucose were emitted by the
    prompt and shown in the UI but absent from the range table, so a value of
    15 mmol/L was silently stored as "normal".
    """
    required = {
        "systolic_blood_pressure",
        "diastolic_blood_pressure",
        "fasting_glucose",
        "postmeal_glucose",
        "postmeal_1h_glucose",
        "random_glucose",
        "bedtime_glucose",
        "heart_rate",
    }
    missing = sorted(m for m in required if m not in ADULT_RANGES)
    assert missing == [], f"metrics without an adult reference range: {missing}"


@pytest.mark.parametrize(
    "metric,value",
    [
        ("random_glucose", 15.0),
        ("postmeal_1h_glucose", 15.0),
        ("bedtime_glucose", 15.0),
        ("fasting_glucose", 15.0),
        ("postmeal_glucose", 15.0),
    ],
)
def test_hyperglycaemia_is_flagged_abnormal(metric, value):
    lower, upper, abnormal, _ = evaluate_metric(metric, value, ADULT)
    assert upper is not None, f"{metric} has no upper bound"
    assert abnormal is True


@pytest.mark.parametrize("metric", ["random_glucose", "bedtime_glucose", "postmeal_1h_glucose"])
def test_severe_hyperglycaemia_is_critical(metric):
    _, _, _, critical = evaluate_metric(metric, 18.0, ADULT)
    assert critical is True


@pytest.mark.parametrize("metric", ["random_glucose", "bedtime_glucose", "postmeal_1h_glucose"])
def test_hypoglycaemia_is_critical(metric):
    _, _, abnormal, critical = evaluate_metric(metric, 2.0, ADULT)
    assert abnormal is True
    assert critical is True


# --------------------------------------------------------------------------
# One-sided ranges
# --------------------------------------------------------------------------

def test_hdl_low_value_is_abnormal():
    """hdl_cholesterol defines a lower bound only; it must still be flagged."""
    lower, upper, abnormal, _ = evaluate_metric("hdl_cholesterol", 0.4, ADULT)
    assert lower == 1.0
    assert upper is None
    assert abnormal is True


def test_hdl_normal_value_is_not_abnormal():
    _, _, abnormal, _ = evaluate_metric("hdl_cholesterol", 1.5, ADULT)
    assert abnormal is False


def test_is_abnormal_value_handles_single_bounds():
    assert is_abnormal_value(0.5, 1.0, None) is True   # below lower only
    assert is_abnormal_value(2.0, 1.0, None) is False
    assert is_abnormal_value(9.0, None, 5.0) is True   # above upper only
    assert is_abnormal_value(3.0, None, 5.0) is False
    assert is_abnormal_value(3.0, None, None) is False


def test_explicit_upper_only_still_uses_default_lower():
    """A single explicit bound used to skip default filling entirely."""
    lower, upper, abnormal, _ = evaluate_metric("ldl_cholesterol", 6.0, ADULT, None, 3.4)
    assert upper == 3.4
    assert abnormal is True


def test_explicit_lower_only_still_uses_default_upper():
    lower, upper, abnormal, _ = evaluate_metric("systolic_blood_pressure", 200, ADULT, 90, None)
    assert lower == 90
    assert upper == 140          # default upper, not None
    assert abnormal is True


def test_explicit_bounds_win_over_defaults():
    lower, upper, _, _ = evaluate_metric("systolic_blood_pressure", 100, ADULT, 95, 130)
    assert (lower, upper) == (95, 130)


def test_resolve_reference_range_unknown_metric():
    assert resolve_reference_range("lab:血常规:白细胞", ADULT) == (None, None)


# --------------------------------------------------------------------------
# Age groups
# --------------------------------------------------------------------------

def test_child_ranges_are_used_below_18():
    adult_upper = resolve_reference_range("heart_rate", ADULT)[1]
    child_upper = resolve_reference_range("heart_rate", CHILD)[1]
    # A child heart rate of 110 is normal for a child but abnormal for an adult.
    assert child_upper > adult_upper
    assert evaluate_metric("heart_rate", 110, CHILD)[2] is False
    assert evaluate_metric("heart_rate", 110, ADULT)[2] is True


def test_age_boundary_18_is_adult():
    assert resolve_reference_range("heart_rate", 17) == resolve_reference_range("heart_rate", CHILD)
    assert resolve_reference_range("heart_rate", 18) == resolve_reference_range("heart_rate", ADULT)


# --------------------------------------------------------------------------
# Clinical critical thresholds
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "metric,value,expected",
    [
        ("systolic_blood_pressure", 185, True),
        ("systolic_blood_pressure", 175, False),
        ("diastolic_blood_pressure", 115, True),
        ("diastolic_blood_pressure", 95, False),
        ("fasting_glucose", 20.0, True),
        ("fasting_glucose", 8.0, False),
        ("heart_rate", 30, True),
        ("heart_rate", 150, True),
        ("heart_rate", 80, False),
    ],
)
def test_critical_thresholds(metric, value, expected):
    assert is_critical_value(metric, value, ADULT) is expected


def test_every_critical_threshold_metric_has_a_range():
    """Critical thresholds are only meaningful next to a reference range."""
    orphans = sorted(m for m in CRITICAL_THRESHOLDS if m not in ADULT_RANGES)
    assert orphans == [], f"critical thresholds without a reference range: {orphans}"


def test_critical_implies_abnormal():
    """is_critical is derived from is_abnormal, so it can never stand alone."""
    for metric in ADULT_RANGES:
        _, _, abnormal, critical = evaluate_metric(metric, 1e6, ADULT)
        if critical:
            assert abnormal, f"{metric} critical without abnormal"


# --------------------------------------------------------------------------
# Plausibility guard
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "metric,value",
    [
        ("weight", -10),
        ("weight", 0),
        ("weight", 99999),
        ("systolic_blood_pressure", 99999),
        ("systolic_blood_pressure", 10),
        ("heart_rate", 0),
        ("random_glucose", -1),
    ],
)
def test_implausible_values_are_rejected(metric, value):
    assert plausible_range_error(metric, value) is not None


@pytest.mark.parametrize(
    "metric,value",
    [
        ("weight", 70),
        ("systolic_blood_pressure", 120),
        ("systolic_blood_pressure", 205),   # crisis, but physiologically real
        ("heart_rate", 40),
        ("random_glucose", 2.5),            # severe hypoglycaemia is still real
    ],
)
def test_plausible_values_are_accepted(metric, value):
    assert plausible_range_error(metric, value) is None


def test_unknown_metrics_are_not_restricted():
    """Free-form lab/exam metrics must not be blocked by the plausibility table."""
    assert plausible_range_error("lab:血常规:白细胞", 45.0) is None
    assert plausible_range_error("exam:心电图:ST段抬高", 0.0) is None


# --------------------------------------------------------------------------
# Accepted metric-name set (write-path validation)
# --------------------------------------------------------------------------

def test_known_metric_names_covers_every_ranged_metric():
    from app.core.reference_ranges import known_metric_names

    known = known_metric_names()
    assert set(ADULT_RANGES).issubset(known)
    assert set(CRITICAL_THRESHOLDS).issubset(known)


def test_accepted_names_include_lipids_but_reject_typos():
    """The write-path whitelist is the UI tabs PLUS everything with a range.

    Regression: validating against extraction_rules.ALLOWED_METRIC_NAMES alone
    rejected hdl_cholesterol / ldl_cholesterol / total_cholesterol /
    triglycerides, which do have reference ranges and were previously accepted.
    """
    from app.core.reference_ranges import known_metric_names
    from app.services.extraction_rules import ALLOWED_METRIC_NAMES

    accepted = set(ALLOWED_METRIC_NAMES) | known_metric_names()
    for name in ("hdl_cholesterol", "ldl_cholesterol", "total_cholesterol", "triglycerides"):
        assert name in accepted, f"{name} must remain a valid manual entry"
    for typo in ("systolic_bp", "blood_sugar", "definitely_not_a_metric"):
        assert typo not in accepted

