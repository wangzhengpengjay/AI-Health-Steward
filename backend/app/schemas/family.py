"""Pydantic schemas for FamilyMember."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FamilyMemberBase(BaseModel):
    model_config = {"populate_by_name": True}

    name: str = Field(..., min_length=1, max_length=64)
    gender: str = Field(..., pattern=r"^(male|female|other)$")
    birth_date: Optional[date] = None
    height: Optional[float] = Field(None, gt=0, le=300)  # cm
    weight: Optional[float] = Field(None, gt=0, le=500)  # kg
    blood_type: Optional[str] = Field(None, max_length=8)
    relationship: Optional[str] = Field(None, max_length=32)
    region: Optional[str] = Field(None, max_length=64)
    occupation: Optional[str] = Field(None, max_length=64)


class FamilyMemberCreate(FamilyMemberBase):
    bmi: Optional[float] = None  # auto-computed if height & weight given

    @field_validator("bmi", mode="after")
    @classmethod
    def _round_bmi(cls, v: Optional[float]) -> Optional[float]:
        # NOTE: an `after` field validator does not run when the field falls back
        # to its default, so the height/weight -> BMI computation must live in a
        # model validator below (see _compute_bmi_from_body).
        return round(v, 1) if v is not None else None

    @model_validator(mode="after")
    def _compute_bmi_from_body(self) -> "FamilyMemberCreate":
        if self.bmi is None and self.height and self.weight and self.height > 0:
            self.bmi = round(self.weight / (self.height / 100) ** 2, 1)
        return self


class FamilyMemberUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    gender: Optional[str] = Field(None, pattern=r"^(male|female|other)$")
    birth_date: Optional[date] = None
    height: Optional[float] = Field(None, gt=0, le=300)
    weight: Optional[float] = Field(None, gt=0, le=500)
    blood_type: Optional[str] = Field(None, max_length=8)
    relationship: Optional[str] = Field(None, max_length=32)
    bmi: Optional[float] = None
    region: Optional[str] = Field(None, max_length=64)
    occupation: Optional[str] = Field(None, max_length=64)
    is_pregnant: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    is_preparing_pregnancy: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    has_sexual_history: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    contrast_allergy: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    has_pacemaker: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    has_metal_implant: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    on_anticoagulant: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    claustrophobia: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    is_breastfeeding: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    has_coagulopathy: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")
    has_heart_failure: Optional[str] = Field(None, pattern=r"^(yes|no|unknown)$")


class FamilyMemberResponse(FamilyMemberBase):
    id: int
    bmi: Optional[float] = None
    region: Optional[str] = None
    occupation: Optional[str] = None
    is_pregnant: str = "unknown"
    is_preparing_pregnancy: str = "unknown"
    has_sexual_history: str = "unknown"
    contrast_allergy: str = "unknown"
    has_pacemaker: str = "unknown"
    has_metal_implant: str = "unknown"
    on_anticoagulant: str = "unknown"
    claustrophobia: str = "unknown"
    is_breastfeeding: str = "unknown"
    has_coagulopathy: str = "unknown"
    has_heart_failure: str = "unknown"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm(cls, obj):
        data = {
            "id": obj.id,
            "name": obj.name,
            "gender": obj.gender,
            "birth_date": obj.birth_date,
            "height": obj.height,
            "weight": obj.weight,
            "bmi": obj.bmi,
            "blood_type": obj.blood_type,
            "relationship": obj.member_relation,
            "region": obj.region,
            "occupation": obj.occupation,
            "is_pregnant": obj.is_pregnant,
            "is_preparing_pregnancy": obj.is_preparing_pregnancy,
            "has_sexual_history": obj.has_sexual_history,
            "contrast_allergy": obj.contrast_allergy,
            "has_pacemaker": obj.has_pacemaker,
            "has_metal_implant": obj.has_metal_implant,
            "on_anticoagulant": obj.on_anticoagulant,
            "claustrophobia": obj.claustrophobia,
            "is_breastfeeding": obj.is_breastfeeding,
            "has_coagulopathy": obj.has_coagulopathy,
            "has_heart_failure": obj.has_heart_failure,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)
