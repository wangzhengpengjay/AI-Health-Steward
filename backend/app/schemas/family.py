"""Pydantic schemas for FamilyMember."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class FamilyMemberBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    gender: str = Field(..., pattern=r"^(male|female|other)$")
    birth_date: Optional[date] = None
    height: Optional[float] = Field(None, gt=0, le=300)  # cm
    weight: Optional[float] = Field(None, gt=0, le=500)  # kg
    blood_type: Optional[str] = Field(None, max_length=8)
    relationship: Optional[str] = Field(None, max_length=32)


class FamilyMemberCreate(FamilyMemberBase):
    bmi: Optional[float] = None  # auto-computed if height & weight given

    @field_validator("bmi", mode="after")
    @classmethod
    def _compute_bmi(cls, v: Optional[float], info) -> Optional[float]:
        if v is not None:
            return round(v, 1)
        height = info.data.get("height")
        weight = info.data.get("weight")
        if height and weight and height > 0:
            return round(weight / (height / 100) ** 2, 1)
        return None


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    gender: Optional[str] = Field(None, pattern=r"^(male|female|other)$")
    birth_date: Optional[date] = None
    height: Optional[float] = Field(None, gt=0, le=300)
    weight: Optional[float] = Field(None, gt=0, le=500)
    blood_type: Optional[str] = Field(None, max_length=8)
    relationship: Optional[str] = Field(None, max_length=32)
    bmi: Optional[float] = None


class FamilyMemberResponse(FamilyMemberBase):
    id: int
    bmi: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
