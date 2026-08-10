"""Age/group-aware default reference ranges (P0-2).

Provides default reference lower/upper bounds for common metrics, split by
age group so children's normal values are not mis-flagged as abnormal.

Design:
- 仅作为「默认值」：当调用方未提供 reference_lower/upper 时自动填充。
- 若调用方显式提供了参考范围，则以显式值为准（不覆盖）。
- 医学口径保守：分成人(>=18)/儿童(<18) 两档，避免过度细分带来的误判。
- 本表为默认兜底，正式参考范围应以权威指南为准；如需更精确可按配置扩展。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Range:
    lower: float | None
    upper: float | None


# metric_name -> (adult_range, child_range)
# 参考值来源为常见临床通用范围，用于默认判异常；危急值判定见 is_critical 逻辑。
ADULT_RANGES: dict[str, Range] = {
    "systolic_blood_pressure": Range(90, 140),   # mmHg
    "diastolic_blood_pressure": Range(60, 90),   # mmHg
    "fasting_glucose": Range(3.9, 6.1),          # mmol/L
    "postmeal_glucose": Range(0, 7.8),           # mmol/L (餐后2h <7.8)
    "heart_rate": Range(60, 100),                # bpm
    "total_cholesterol": Range(0, 5.2),          # mmol/L
    "triglycerides": Range(0, 1.7),              # mmol/L
    "ldl_cholesterol": Range(0, 3.4),            # mmol/L
    "hdl_cholesterol": Range(1.0, None),         # mmol/L (仅下限)
}

# 儿童参考范围（<18 岁），血压/血糖/心率与成人不同
CHILD_RANGES: dict[str, Range] = {
    # 儿童收缩压约 100-120（随年龄增长），舒张压 60-80
    "systolic_blood_pressure": Range(90, 120),
    "diastolic_blood_pressure": Range(50, 80),
    # 儿童空腹血糖与成人基本一致，但无需过高下限判断
    "fasting_glucose": Range(3.3, 6.1),
    "postmeal_glucose": Range(0, 7.8),
    # 儿童静息心率偏高（新生儿-幼儿更高，此处取儿童 6-12 岁大致区间）
    "heart_rate": Range(70, 120),
    "total_cholesterol": Range(0, 4.4),
    "triglycerides": Range(0, 1.5),
    "ldl_cholesterol": Range(0, 2.8),
    "hdl_cholesterol": Range(1.0, None),
}


def resolve_reference_range(
    metric_name: str,
    age: int | None,
    explicit_lower: float | None = None,
    explicit_upper: float | None = None,
) -> tuple[float | None, float | None]:
    """Resolve reference bounds for a metric.

    - Explicit (client-provided) values take precedence.
    - Otherwise fall back to age-aware defaults (adult vs child).
    - Returns (lower, upper); either may be None when no bound applies.
    """
    if explicit_lower is not None or explicit_upper is not None:
        return explicit_lower, explicit_upper

    table = ADULT_RANGES if age is None or age >= 18 else CHILD_RANGES
    rng = table.get(metric_name)
    if rng is None:
        return None, None
    return rng.lower, rng.upper