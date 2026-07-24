"""Family member CRUD endpoints (soft-delete)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.schemas.family import (
    FamilyMemberCreate,
    FamilyMemberResponse,
    FamilyMemberUpdate,
)

router = APIRouter(prefix="/members", tags=["members"])


@router.post(
    "",
    response_model=FamilyMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_member(
    payload: FamilyMemberCreate,
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    data = payload.model_dump(exclude_unset=True)
    if 'relationship' in data:
        data['member_relation'] = data.pop('relationship')
    # Ensure computed BMI is included
    if payload.bmi is not None:
        data['bmi'] = payload.bmi
    member = FamilyMember(**data)
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return _to_response(member)


@router.get("", response_model=List[FamilyMemberResponse])
async def list_members(db: AsyncSession = Depends(get_db)) -> List[FamilyMember]:
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False)).order_by(FamilyMember.id)
    )
    members = list(result.scalars().all())
    return [FamilyMemberResponse(
        id=m.id, name=m.name, gender=m.gender,
        birth_date=m.birth_date, height=m.height,
        weight=m.weight, bmi=m.bmi, blood_type=m.blood_type,
        relationship=m.member_relation,
        created_at=m.created_at, updated_at=m.updated_at,
    ) for m in members]


@router.get("/{member_id}", response_model=FamilyMemberResponse)
async def get_member(member_id: int, db: AsyncSession = Depends(get_db)) -> FamilyMember:
    member = await _get_member_or_404(db, member_id)
    return FamilyMemberResponse(
            id=member.id, name=member.name, gender=member.gender,
            birth_date=member.birth_date, height=member.height,
            weight=member.weight, bmi=member.bmi, blood_type=member.blood_type,
            relationship=member.member_relation,
            created_at=member.created_at, updated_at=member.updated_at,
        )


@router.put("/{member_id}", response_model=FamilyMemberResponse)
async def update_member(
    member_id: int,
    payload: FamilyMemberUpdate,
    db: AsyncSession = Depends(get_db),
) -> FamilyMember:
    member = await _get_member_or_404(db, member_id)
    data = payload.model_dump(exclude_unset=True)
    # Recompute BMI if height/weight changed and bmi not explicitly provided
    if ("height" in data or "weight" in data) and "bmi" not in data:
        height = data.get("height", member.height)
        weight = data.get("weight", member.weight)
        if height and weight and height > 0:
            data["bmi"] = round(weight / (height / 100) ** 2, 1)
    for key, value in data.items():
        setattr(member, key, value)
    await db.flush()
    await db.refresh(member)
    return FamilyMemberResponse(
            id=member.id, name=member.name, gender=member.gender,
            birth_date=member.birth_date, height=member.height,
            weight=member.weight, bmi=member.bmi, blood_type=member.blood_type,
            relationship=member.member_relation,
            created_at=member.created_at, updated_at=member.updated_at,
        )


@router.delete("/{member_id}")
async def delete_member(member_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    member = await _get_member_or_404(db, member_id)
    member.is_deleted = True
    member.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return {'message': 'Member soft-deleted', 'id': member_id}


async def _get_member_or_404(db: AsyncSession, member_id: int) -> FamilyMember:
    result = await db.execute(
        select(FamilyMember).where(
            FamilyMember.id == member_id,
            FamilyMember.is_deleted.is_(False),
        )
    )
    member = result.scalars().first()
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FamilyMember {member_id} not found",
        )
    return member

def _to_response(m: FamilyMember) -> FamilyMemberResponse:
    return FamilyMemberResponse(
        id=m.id, name=m.name, gender=m.gender,
        birth_date=m.birth_date, height=m.height,
        weight=m.weight, bmi=m.bmi, blood_type=m.blood_type,
        relationship=m.member_relation,
        region=m.region, occupation=m.occupation,
        is_pregnant=m.is_pregnant, is_preparing_pregnancy=m.is_preparing_pregnancy,
        has_sexual_history=m.has_sexual_history, contrast_allergy=m.contrast_allergy,
        has_pacemaker=m.has_pacemaker, has_metal_implant=m.has_metal_implant,
        on_anticoagulant=m.on_anticoagulant, claustrophobia=m.claustrophobia,
        is_breastfeeding=m.is_breastfeeding, has_coagulopathy=m.has_coagulopathy,
        has_heart_failure=m.has_heart_failure,
        created_at=m.created_at, updated_at=m.updated_at,
    )
