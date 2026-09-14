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
    "postmeal_1h_glucose": Range(3.9, 8.9),      # mmol/L (餐后1h <8.9)
    "random_glucose": Range(3.9, 11.1),          # mmol/L (随机血糖 <11.1)
    "bedtime_glucose": Range(3.9, 8.0),          # mmol/L (睡前 3.9~8.0)
    "heart_rate": Range(60, 100),                # bpm
    "total_cholesterol": Range(0, 5.2),          # mmol/L
    "triglycerides": Range(0, 1.7),              # mmol/L
    "ldl_cholesterol": Range(0, 3.4),            # mmol/L
    "hdl_cholesterol": Range(1.0, None),         # mmol/L (仅下限)
}

# 危急值阈值（P1-2）：用于把「异常」进一步区分为需立即就医的「危急」。
# 采用权威指南常用危急值，取代原先“<下限*0.5 或 >上限*1.5”的相对启发式，
# 更贴近临床（例如高血压危急值 180/110，而非 140*1.5=210）。
# metric_name -> (critical_lower, critical_upper)，None 表示不适用该侧。
CRITICAL_THRESHOLDS: dict[str, tuple[float | None, float | None]] = {
    "systolic_blood_pressure": (None, 180),   # >=180 高血压急症
    "diastolic_blood_pressure": (None, 110),  # >=110 重度
    "fasting_glucose": (2.8, 16.7),           # <2.8 低血糖危象; >=16.7 高血糖危象
    "postmeal_glucose": (None, 16.7),
    "postmeal_1h_glucose": (2.8, 16.7),
    "random_glucose": (2.8, 16.7),
    "bedtime_glucose": (2.8, 16.7),
    "heart_rate": (40, 130),                  # <40 心动过缓; >130 心动过速
}


def is_critical_value(
    metric_name: str, value: float, age: int | None
) -> bool:
    """Return True if a metric value is clinically critical (needs urgent care).

    Falls back to a relative heuristic for metrics without a defined critical
    threshold. The heuristic is one-sided aware: a metric that only defines a
    lower bound (or only an upper bound) still gets a critical test on that side.
    """
    thr = CRITICAL_THRESHOLDS.get(metric_name)
    if thr:
        c_lo, c_hi = thr
        if c_lo is not None and value < c_lo:
            return True
        if c_hi is not None and value > c_hi:
            return True
        return False

    # 无明确危急值定义时，退回相对启发式（单侧缺失也能判定）
    lo, hi = resolve_reference_range(metric_name, age)
    is_abn = is_abnormal_value(value, lo, hi)
    if not is_abn:
        return False
    if lo is not None and value < lo * 0.5:
        return True
    if hi is not None and value > hi * 1.5:
        return True
    return False


def is_abnormal_value(value: float, lower: float | None, upper: float | None) -> bool:
    """One-sided-aware abnormality test.

    Consumers previously required BOTH bounds to be non-None before flagging
    anything, which silently disabled detection for metrics that legitimately
    define only one bound (e.g. hdl_cholesterol has a lower bound only).
    """
    if lower is not None and value < lower:
        return True
    if upper is not None and value > upper:
        return True
    return False


# 儿童参考范围（<18 岁），血压/血糖/心率与成人不同
CHILD_RANGES: dict[str, Range] = {
    # 儿童收缩压约 100-120（随年龄增长），舒张压 60-80
    "systolic_blood_pressure": Range(90, 120),
    "diastolic_blood_pressure": Range(50, 80),
    # 儿童空腹血糖与成人基本一致，但无需过高下限判断
    "fasting_glucose": Range(3.3, 6.1),
    "postmeal_glucose": Range(0, 7.8),
    "postmeal_1h_glucose": Range(3.3, 8.9),
    "random_glucose": Range(3.3, 11.1),
    "bedtime_glucose": Range(3.3, 8.0),
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

    Bounds are resolved **per side**: an explicitly provided side wins, and a
    side left as None falls back to the age-aware default table. Either side may
    legitimately end up None (e.g. hdl_cholesterol defines a lower bound only).

    Previously a single explicit side caused the whole function to return the
    explicit pair, so callers that required both sides non-None stopped flagging
    abnormalities entirely (e.g. LDL 6.0 sent with only reference_upper=3.4 was
    stored as normal).
    """
    table = ADULT_RANGES if age is None or age >= 18 else CHILD_RANGES
    rng = table.get(metric_name)
    default_lower = rng.lower if rng is not None else None
    default_upper = rng.upper if rng is not None else None
    lower = explicit_lower if explicit_lower is not None else default_lower
    upper = explicit_upper if explicit_upper is not None else default_upper
    return lower, upper


def evaluate_metric(
    metric_name: str,
    value: float,
    age: int | None,
    explicit_lower: float | None = None,
    explicit_upper: float | None = None,
) -> tuple[float | None, float | None, bool, bool]:
    """Server-side source of truth for a metric's flags.

    Returns ``(reference_lower, reference_upper, is_abnormal, is_critical)``.

    This is the single entry point that every write path (manual entry, report
    archival, chat extraction) should use, so that client- or LLM-supplied
    ``is_abnormal`` / ``is_critical`` values are never trusted, and so the
    clinical critical thresholds are applied consistently.
    """
    lower, upper = resolve_reference_range(
        metric_name, age, explicit_lower, explicit_upper
    )
    abnormal = is_abnormal_value(value, lower, upper)
    critical = abnormal and is_critical_value(metric_name, value, age)
    return lower, upper, abnormal, critical


# 生理学上「不可能」的取值边界（宽于参考范围，只拦截明显的输入错误/脏数据）。
# 用途：防止 weight=-10、systolic=99999 这类值入库并立刻触发假的「危急值」告警。
# 未列出的指标（lab:/exam: 等自由文本指标）不做限制。
PLAUSIBLE_BOUNDS: dict[str, tuple[float, float]] = {
    "systolic_blood_pressure": (40, 400),
    "diastolic_blood_pressure": (20, 300),
    "fasting_glucose": (0.5, 60),
    "postmeal_glucose": (0.5, 60),
    "postmeal_1h_glucose": (0.5, 60),
    "random_glucose": (0.5, 60),
    "bedtime_glucose": (0.5, 60),
    "heart_rate": (20, 300),
    "weight": (1, 500),
    "bmi": (5, 200),
    "total_cholesterol": (0.5, 30),
    "triglycerides": (0.1, 50),
    "ldl_cholesterol": (0.1, 20),
    "hdl_cholesterol": (0.1, 10),
}


def plausible_range_error(metric_name: str, value: float) -> str | None:
    """Return a human-readable error when a value is physiologically impossible."""
    bounds = PLAUSIBLE_BOUNDS.get(metric_name)
    if bounds is None:
        return None
    low, high = bounds
    if value != value:  # NaN
        return f"{metric_name} 数值无效"
    if value < low or value > high:
        return f"{metric_name} 数值 {value:g} 超出合理范围（{low:g}~{high:g}），请检查输入"
    return None


def known_metric_names() -> set[str]:
    """Every metric this module can evaluate.

    Used to validate metric names on write. Note this is deliberately broader
    than the fixed UI tabs (extraction_rules.ALLOWED_METRIC_NAMES): blood lipids
    have reference ranges here but no dedicated input tab, so they are valid
    manual entries even though they are not in the tab list.
    """
    return set(ADULT_RANGES) | set(CHILD_RANGES) | set(PLAUSIBLE_BOUNDS)


