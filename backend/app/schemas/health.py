"""Pydantic schemas for health metrics."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class MetricRecordBase(BaseModel):
    metric_name: str = Field(..., min_length=1, max_length=64)
    value: float
    text_value: Optional[str] = Field(None, max_length=128)
    unit: Optional[str] = Field(None, max_length=32)
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    measured_at: datetime
    context: Optional[str] = Field(None, max_length=64)


class MetricRecordCreate(MetricRecordBase):
    source_type: str = Field("manual", pattern=r"^(manual|report|chat_extract)$")
    # is_abnormal / is_critical are computed server-side, not accepted from client
    is_abnormal: Optional[bool] = None
    is_critical: Optional[bool] = None

    @model_validator(mode="after")
    def _compute_abnormal(self) -> "MetricRecordCreate":
        if self.reference_lower is not None and self.reference_upper is not None:
            self.is_abnormal = not (self.reference_lower <= self.value <= self.reference_upper)
            self.is_critical = bool(
                self.is_abnormal
                and (
                    self.value < self.reference_lower * 0.5
                    or self.value > self.reference_upper * 1.5
                )
            )
        else:
            self.is_abnormal = False
            self.is_critical = False
        return self


class MetricRecordUpdate(BaseModel):
    """Partial update for a metric record. Re-computes abnormal/critical."""
    value: Optional[float] = None
    unit: Optional[str] = Field(None, max_length=32)
    reference_lower: Optional[float] = None
    reference_upper: Optional[float] = None
    measured_at: Optional[datetime] = None
    context: Optional[str] = Field(None, max_length=64)

    @model_validator(mode="after")
    def _recompute_abnormal(self) -> "MetricRecordUpdate":
        if self.value is not None and self.reference_lower is not None and self.reference_upper is not None:
            self.is_abnormal = not (self.reference_lower <= self.value <= self.reference_upper)
            self.is_critical = bool(
                self.is_abnormal
                and (
                    self.value < self.reference_lower * 0.5
                    or self.value > self.reference_upper * 1.5
                )
            )
        return self



class MetricRecordResponse(MetricRecordBase):
    id: int
    member_id: int
    is_abnormal: bool
    is_critical: bool
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
