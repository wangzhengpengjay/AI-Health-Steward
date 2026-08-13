from app.services.extraction_rules import ALLOWED_METRIC_NAMES, filter_metrics, normalize_extraction


def test_filter_metrics_keeps_only_fixed_tab_names():
    metrics = [
        {"metric_name": "systolic_blood_pressure", "value": 120},
        {"metric_name": "pr_interval", "value": 189},
        {"metric_name": "total_cholesterol", "value": 5.0},
    ]
    result = filter_metrics(metrics)
    assert [m["metric_name"] for m in result] == ["systolic_blood_pressure"]


def test_allowed_names_cover_fixed_tabs():
    required = {
        "systolic_blood_pressure",
        "diastolic_blood_pressure",
        "fasting_glucose",
        "postmeal_glucose",
        "heart_rate",
        "weight",
        "bmi",
    }
    assert required <= ALLOWED_METRIC_NAMES


def test_normalize_extraction_moves_ecg_to_exam():
    data = {
        "metrics": [
            {"metric_name": "systolic_blood_pressure", "value": 120},
            {"metric_name": "pr_interval", "value": 189, "unit": "ms"},
        ],
        "lab_tests": [],
        "exam_findings": [],
    }
    out = normalize_extraction(data)
    assert [m["metric_name"] for m in out["metrics"]] == ["systolic_blood_pressure"]
    assert out["exam_findings"] == [{
        "finding_category": "心电图",
        "finding_desc": "P-R间期",
        "value_num": 189,
        "unit": "ms",
        "conclusion": None,
    }]


def test_filter_metrics_normalizes_glucose_alias():
    result = filter_metrics([
        {"metric_name": "postprandial_glucose_2h", "value": 7.9},
        {"metric_name": "random_glucose", "value": 8.0},
    ])
    assert [m["metric_name"] for m in result] == ["postmeal_glucose", "random_glucose"]
