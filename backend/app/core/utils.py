"""Shared utility functions used across the application."""
from __future__ import annotations

from datetime import date


def compute_age(birth_date: date | None) -> int | None:
    """Compute age in years from birth_date (may be date or None)."""
    if not birth_date:
        return None
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


# Standard metric name → Chinese label mapping
_METRIC_LABELS: dict[str, str] = {
    "systolic_blood_pressure": "收缩压",
    "diastolic_blood_pressure": "舒张压",
    "fasting_glucose": "空腹血糖",
    "postmeal_glucose": "餐后2h血糖",
    "postmeal_1h_glucose": "餐后1h血糖",
    "random_glucose": "随机血糖",
    "bedtime_glucose": "睡前血糖",
    "heart_rate": "心率",
    "total_cholesterol": "总胆固醇",
    "triglycerides": "甘油三酯",
    "ldl_cholesterol": "LDL-C",
    "hdl_cholesterol": "HDL-C",
    "weight": "体重",
    "bmi": "BMI",
}


def metric_label(name: str) -> str:
    """Convert a metric_name to a human-readable Chinese label.

    For lab:/exam: prefixed names, returns the part after the prefix.
    For standard metric names, returns the mapped label.
    Otherwise returns the name as-is.
    """
    if name.startswith("lab:") or name.startswith("exam:"):
        return name.split(":", 1)[-1]
    return _METRIC_LABELS.get(name, name)
