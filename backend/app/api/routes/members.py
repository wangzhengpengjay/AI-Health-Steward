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
    member = FamilyMember(**payload.model_dump(exclude_unset=True))
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


@router.get("", response_model=List[FamilyMemberResponse])
async def list_members(db: AsyncSession = Depends(get_db)) -> List[FamilyMember]:
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False)).order_by(FamilyMember.id)
    )
    return list(result.scalars().all())


@router.get("/{member_id}", response_model=FamilyMemberResponse)
async def get_member(member_id: int, db: AsyncSession = Depends(get_db)) -> FamilyMember:
    member = await _get_member_or_404(db, member_id)
    return member


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
    return member


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(member_id: int, db: AsyncSession = Depends(get_db)) -> None:
    member = await _get_member_or_404(db, member_id)
    member.is_deleted = True
    member.deleted_at = datetime.now(timezone.utc)
    await db.flush()


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
