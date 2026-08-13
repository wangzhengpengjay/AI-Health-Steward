"""Shared extraction classification rules for report parsing."""

ALLOWED_METRIC_NAMES = {
    "systolic_blood_pressure",
    "diastolic_blood_pressure",
    "fasting_glucose",
    "postmeal_glucose",
    "random_glucose",
    "postmeal_1h_glucose",
    "bedtime_glucose",
    "heart_rate",
    "weight",
    "bmi",
}

METRIC_NAME_HINT = ", ".join(sorted(ALLOWED_METRIC_NAMES))

ECG_METRIC_LABELS = {
    "pr_interval": "P-R间期",
    "qrs_duration": "QRS时限",
    "qt_qtc": "QT/QTc",
    "sv1": "SV1",
    "rv5": "RV5",
    "rv5_plus_sv1": "RV5+SV1",
    "cardiac_axis": "心电轴",
}


def filter_metrics(metrics: list[dict]) -> list[dict]:
    """Keep only fixed-tab metric names; everything else must go to lab/exam."""
    return [m for m in metrics if m.get("metric_name") in ALLOWED_METRIC_NAMES]


def normalize_extraction(data: dict) -> dict:
    """Move known check-up metrics to exam findings; drop unknown metric names."""
    metrics = data.get("metrics") or []
    kept: list[dict] = []
    exam_items: list[dict] = []
    for m in metrics:
        name = m.get("metric_name")
        if name in ALLOWED_METRIC_NAMES:
            kept.append(m)
        elif name in ECG_METRIC_LABELS:
            exam_items.append({
                "finding_category": "心电图",
                "finding_desc": ECG_METRIC_LABELS[name],
                "value_num": m.get("value"),
                "unit": m.get("unit"),
                "conclusion": None,
            })
    data["metrics"] = kept
    if exam_items:
        data["exam_findings"] = list(data.get("exam_findings") or []) + exam_items
    return data
