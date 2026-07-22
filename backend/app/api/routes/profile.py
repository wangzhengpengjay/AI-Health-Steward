"""Health profile aggregation: diagnoses, medications, allergies."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import Allergy, Diagnosis, Medication

router = APIRouter(prefix="/members", tags=["profile"])

# ---- Schemas ----

class DiagnosisOut(BaseModel):
    id: int
    disease_name: str
    icd_code: Optional[str] = None
    diagnosed_date: Optional[date] = None
    severity: Optional[str] = None
    status: str
    model_config = {"from_attributes": True}

class DiagnosisCreate(BaseModel):
    disease_name: str
    icd_code: Optional[str] = None
    diagnosed_date: Optional[date] = None
    severity: Optional[str] = None
    status: str = "active"

class MedicationOut(BaseModel):
    id: int
    drug_name: str
    generic_name: Optional[str] = None
    dosage: str
    frequency: str
    route: str = "oral"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    model_config = {"from_attributes": True}

class MedicationCreate(BaseModel):
    drug_name: str
    generic_name: Optional[str] = None
    dosage: str
    frequency: str
    route: str = "oral"
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class AllergyOut(BaseModel):
    id: int
    type: str
    name: str
    severity: str = "mild"
    recorded_at: Optional[date] = None
    model_config = {"from_attributes": True}

class AllergyCreate(BaseModel):
    type: str
    name: str
    severity: str = "mild"
    recorded_at: Optional[date] = None

class ProfileSummary(BaseModel):
    diagnoses: List[DiagnosisOut]
    medications: List[MedicationOut]
    allergies: List[AllergyOut]


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    r = await db.execute(
        select(FamilyMember.id).where(FamilyMember.id == member_id, FamilyMember.is_deleted.is_(False))
    )
    if r.scalars().first() is None:
        raise HTTPException(status_code=404, detail=f"FamilyMember {member_id} not found")


@router.get("/{member_id}/profile", response_model=ProfileSummary)
async def get_profile(member_id: int, db: AsyncSession = Depends(get_db)) -> ProfileSummary:
    await _ensure_member(db, member_id)
    d = await db.execute(select(Diagnosis).where(Diagnosis.member_id == member_id).order_by(Diagnosis.created_at.desc()))
    m = await db.execute(select(Medication).where(Medication.member_id == member_id).order_by(Medication.created_at.desc()))
    a = await db.execute(select(Allergy).where(Allergy.member_id == member_id).order_by(Allergy.created_at.desc()))
    return ProfileSummary(
        diagnoses=list(d.scalars().all()),
        medications=list(m.scalars().all()),
        allergies=list(a.scalars().all()),
    )


@router.post("/{member_id}/profile/diagnoses", response_model=DiagnosisOut, status_code=201)
async def add_diagnosis(member_id: int, payload: DiagnosisCreate, db: AsyncSession = Depends(get_db)) -> Diagnosis:
    await _ensure_member(db, member_id)
    obj = Diagnosis(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.post("/{member_id}/profile/medications", response_model=MedicationOut, status_code=201)
async def add_medication(member_id: int, payload: MedicationCreate, db: AsyncSession = Depends(get_db)) -> Medication:
    await _ensure_member(db, member_id)
    obj = Medication(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.post("/{member_id}/profile/allergies", response_model=AllergyOut, status_code=201)
async def add_allergy(member_id: int, payload: AllergyCreate, db: AsyncSession = Depends(get_db)) -> Allergy:
    await _ensure_member(db, member_id)
    obj = Allergy(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/profile/records/{record_type}/{record_id}", status_code=204)
async def delete_profile_record(record_type: str, record_id: int, db: AsyncSession = Depends(get_db)):
    model_map = {"diagnoses": Diagnosis, "medications": Medication, "allergies": Allergy}
    model = model_map.get(record_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unknown record type: {record_type}")
    r = await db.execute(select(model).where(model.id == record_id))
    obj = r.scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{record_type} {record_id} not found")
    await db.delete(obj)
