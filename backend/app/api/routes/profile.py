"""Health profile aggregation: diagnoses, medications, allergies, lifestyle, surgery, vaccination."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.models.health import Allergy, Diagnosis, Lifestyle, Medication, Surgery, Vaccination

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

class LifestyleOut(BaseModel):
    id: int
    category: str
    status: str
    frequency: Optional[str] = None
    recorded_at: Optional[date] = None
    model_config = {"from_attributes": True}

class LifestyleCreate(BaseModel):
    category: str  # smoking/drinking/exercise/sleep/diet
    status: str
    frequency: Optional[str] = None
    recorded_at: Optional[date] = None

class SurgeryOut(BaseModel):
    id: int
    surgery_name: str
    surgery_date: Optional[date] = None
    hospital: Optional[str] = None
    notes: Optional[str] = None
    model_config = {"from_attributes": True}

class SurgeryCreate(BaseModel):
    surgery_name: str
    surgery_date: Optional[date] = None
    hospital: Optional[str] = None
    notes: Optional[str] = None

class VaccinationOut(BaseModel):
    id: int
    vaccine_name: str
    dose_no: Optional[str] = None
    vaccinated_date: Optional[date] = None
    facility: Optional[str] = None
    model_config = {"from_attributes": True}

class VaccinationCreate(BaseModel):
    vaccine_name: str
    dose_no: Optional[str] = None
    vaccinated_date: Optional[date] = None
    facility: Optional[str] = None

class ProfileSummary(BaseModel):
    diagnoses: List[DiagnosisOut]
    medications: List[MedicationOut]
    allergies: List[AllergyOut]
    lifestyles: List[LifestyleOut]
    surgeries: List[SurgeryOut]
    vaccinations: List[VaccinationOut]


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
    l = await db.execute(select(Lifestyle).where(Lifestyle.member_id == member_id).order_by(Lifestyle.created_at.desc()))
    s = await db.execute(select(Surgery).where(Surgery.member_id == member_id).order_by(Surgery.created_at.desc()))
    v = await db.execute(select(Vaccination).where(Vaccination.member_id == member_id).order_by(Vaccination.created_at.desc()))
    return ProfileSummary(
        diagnoses=list(d.scalars().all()),
        medications=list(m.scalars().all()),
        allergies=list(a.scalars().all()),
        lifestyles=list(l.scalars().all()),
        surgeries=list(s.scalars().all()),
        vaccinations=list(v.scalars().all()),
    )


@router.post("/{member_id}/profile/diagnoses", response_model=DiagnosisOut, status_code=201)
async def add_diagnosis(member_id: int, payload: DiagnosisCreate, db: AsyncSession = Depends(get_db)) -> Diagnosis:
    await _ensure_member(db, member_id)
    obj = Diagnosis(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    # 功能①: 慢病 active 状态生成定期随访待办
    try:
        from app.services import task_service
        await task_service.handle_diagnosis_added(
            db, member_id, obj.disease_name, obj.id, obj.status,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("task gen failed for diagnosis %s", obj.id)
    return obj


@router.post("/{member_id}/profile/medications", response_model=MedicationOut, status_code=201)
async def add_medication(member_id: int, payload: MedicationCreate, db: AsyncSession = Depends(get_db)) -> Medication:
    await _ensure_member(db, member_id)
    obj = Medication(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    # 功能①: 在用药（无 end_date）生成用药提醒待办
    try:
        from app.services import task_service
        await task_service.handle_medication_added(
            db, member_id, obj.drug_name, obj.id, obj.end_date,
        )
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("task gen failed for medication %s", obj.id)
    return obj


@router.post("/{member_id}/profile/allergies", response_model=AllergyOut, status_code=201)
async def add_allergy(member_id: int, payload: AllergyCreate, db: AsyncSession = Depends(get_db)) -> Allergy:
    await _ensure_member(db, member_id)
    obj = Allergy(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.post("/{member_id}/profile/lifestyles", response_model=LifestyleOut, status_code=201)
async def add_lifestyle(member_id: int, payload: LifestyleCreate, db: AsyncSession = Depends(get_db)) -> Lifestyle:
    await _ensure_member(db, member_id)
    obj = Lifestyle(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.post("/{member_id}/profile/surgeries", response_model=SurgeryOut, status_code=201)
async def add_surgery(member_id: int, payload: SurgeryCreate, db: AsyncSession = Depends(get_db)) -> Surgery:
    await _ensure_member(db, member_id)
    obj = Surgery(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.post("/{member_id}/profile/vaccinations", response_model=VaccinationOut, status_code=201)
async def add_vaccination(member_id: int, payload: VaccinationCreate, db: AsyncSession = Depends(get_db)) -> Vaccination:
    await _ensure_member(db, member_id)
    obj = Vaccination(member_id=member_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/profile/records/{record_type}/{record_id}", status_code=204)
async def delete_profile_record(record_type: str, record_id: int, db: AsyncSession = Depends(get_db)):
    model_map = {
        "diagnoses": Diagnosis,
        "medications": Medication,
        "allergies": Allergy,
        "lifestyles": Lifestyle,
        "surgeries": Surgery,
        "vaccinations": Vaccination,
    }
    model = model_map.get(record_type)
    if model is None:
        raise HTTPException(status_code=400, detail=f"Unknown record type: {record_type}")
    r = await db.execute(select(model).where(model.id == record_id))
    obj = r.scalars().first()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{record_type} {record_id} not found")
    await db.delete(obj)
