"""Health task routes — list, manage, and manually create member to-dos."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tasks import HealthTask
from app.services import task_service

router = APIRouter()


class TaskCreate(BaseModel):
    task_type: str = Field(default="custom")
    title: str
    description: Optional[str] = None
    priority: str = Field(default="normal")
    due_date: Optional[date] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None  # done / dismissed / reopen
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None


class TaskOut(BaseModel):
    id: int
    member_id: int
    task_type: str
    title: str
    description: Optional[str]
    priority: str
    due_date: Optional[date]
    status: str
    source_ref: Optional[str]
    auto_generated: bool
    created_at: datetime
    completed_at: Optional[datetime]
    dismissed_at: Optional[datetime]

    model_config = {"from_attributes": True}


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    from app.models.family import FamilyMember
    member = await db.get(FamilyMember, member_id)
    if member is None or member.is_deleted:
        raise HTTPException(status_code=404, detail="成员不存在")


def _to_out(t: HealthTask) -> TaskOut:
    return TaskOut.model_validate(t)


@router.get("/members/{member_id}/tasks", response_model=list[TaskOut])
async def get_tasks(
    member_id: int,
    db: AsyncSession = Depends(get_db),
    status: str = Query(default="open", description="open / all / done / dismissed"),
    task_type: Optional[str] = Query(default=None),
):
    await _ensure_member(db, member_id)
    tasks = await task_service.list_tasks(db, member_id, status=status, task_type=task_type)
    return [_to_out(t) for t in tasks]


@router.get("/tasks/overview", response_model=list[dict])
async def get_overview(db: AsyncSession = Depends(get_db)):
    """Family-level task overview for the home page."""
    from sqlalchemy import select
    from app.models.family import FamilyMember
    result = await db.execute(
        select(FamilyMember).where(FamilyMember.is_deleted.is_(False))
    )
    members = list(result.scalars().all())
    return await task_service.overview(db, [m.id for m in members])


@router.post("/members/{member_id}/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    member_id: int,
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_member(db, member_id)
    task = await task_service._add_task(
        db,
        member_id,
        payload.task_type,
        payload.title,
        description=payload.description,
        due_date=payload.due_date,
        priority=payload.priority,
        auto_generated=False,
    )
    await db.commit()
    await db.refresh(task)
    return _to_out(task)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
):
    task = await db.get(HealthTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="待办不存在")

    if payload.status == "done":
        await task_service.complete_task(db, task_id)
    elif payload.status == "dismissed":
        await task_service.dismiss_task(db, task_id)
    elif payload.status == "reopen":
        task.status = "open"
        task.completed_at = None
        task.dismissed_at = None
    if payload.title is not None:
        task.title = payload.title
    if payload.description is not None:
        task.description = payload.description
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.due_date is not None:
        task.due_date = payload.due_date
    await db.commit()
    await db.refresh(task)
    return _to_out(task)