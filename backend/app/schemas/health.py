"""Pydantic schemas for health metrics."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.core.reference_ranges import plausible_range_error


class MetricRecordBase(BaseModel):
    metric_name: str = Field(..., min_length=1)
    value: float
    text_value: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=32)
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    measured_at: datetime
    context: Optional[str] = None


class MetricRecordCreate(MetricRecordBase):
    source_type: str = Field("manual", pattern=r"^(manual|report|chat_extract)$")
    # Accepted for backwards compatibility but always recomputed server-side
    # from the reference-range rules (app.core.reference_ranges.evaluate_metric).
    is_abnormal: Optional[bool] = None
    is_critical: Optional[bool] = None

    @model_validator(mode="after")
    def _validate_plausible_value(self) -> "MetricRecordCreate":
        """Reject physiologically impossible values.

        Without this, a typo such as weight=-10 or systolic=99999 was stored and
        immediately raised a fake "危急值，请尽快就医" alert, which erodes trust
        in the alerting mechanism.

        Note: this lives on the *Create* schema only. Putting it on the shared
        base would also run during response serialization and make every read
        endpoint fail with a 500 as soon as one legacy out-of-range row exists.
        """
        error = plausible_range_error(self.metric_name, self.value)
        if error:
            raise ValueError(error)
        return self


class MetricRecordUpdate(BaseModel):
    """Partial update for a metric record.

    ``is_abnormal`` / ``is_critical`` are declared (but ignored) so the router
    can assign its server-computed values without tripping Pydantic. Previously
    they were missing, so any update that carried both reference bounds failed
    with a 422 "object has no field" error.
    """
    value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=32)
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    measured_at: Optional[datetime] = None
    context: Optional[str] = None
    is_abnormal: Optional[bool] = None
    is_critical: Optional[bool] = None


class MetricRecordResponse(MetricRecordBase):
    id: int
    member_id: int
    is_abnormal: bool
    is_critical: bool
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}

