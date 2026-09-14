"""Health task routes — list, manage, and manually create member to-dos."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

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
    """Partial update. Use ``model_dump(exclude_unset=True)`` so an explicit
    ``null`` (clear the field) is distinguishable from "not provided"."""
    status: Optional[Literal["done", "dismissed", "reopen"]] = None
    title: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = None
    priority: Optional[Literal["critical", "high", "normal", "low"]] = None
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

    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)

    if new_status == "done":
        if task.status != "open":
            # Report the real state instead of returning a fake 200 success for
            # an already-completed/dismissed task.
            raise HTTPException(status_code=409, detail=f"待办当前状态为 {task.status}，无法标记完成")
        await task_service.complete_task(db, task_id)
    elif new_status == "dismissed":
        if task.status != "open":
            raise HTTPException(status_code=409, detail=f"待办当前状态为 {task.status}，无法忽略")
        await task_service.dismiss_task(db, task_id)
    elif new_status == "reopen":
        task.status = "open"
        task.completed_at = None
        task.dismissed_at = None

    # exclude_unset lets a client clear description / due_date with an explicit
    # null; previously `is not None` silently ignored those requests.
    for field in ("title", "description", "priority", "due_date"):
        if field in data:
            setattr(task, field, data[field])
    await db.commit()
    await db.refresh(task)
    return _to_out(task)