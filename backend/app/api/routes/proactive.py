"""Proactive agent API routes (V1.4).

Endpoints:
- GET  /{member_id}/proactive/messages  — list proactive messages (unread first)
- POST /{member_id}/proactive/patrol     — manually trigger a patrol for this member
- POST /{member_id}/proactive/reply      — user replies to a proactive message
- POST /{member_id}/proactive/dismiss     — dismiss a proactive message
- POST /{member_id}/proactive/postpone    — postpone a proactive reminder
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.core.security import rate_limited
from app.models.family import FamilyMember
from app.models.health import ChatMessage
from app.providers.router import ModelRouter, get_model_router
from app.services.patrol_engine import patrol_member
from app.services.result_collector import collect_result, find_last_proactive_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/members", tags=["proactive"])


class ProactiveMessage(BaseModel):
    id: int
    content: str
    priority: str = "normal"
    created_at: str
    metadata: dict | None = None
    collected: bool = False


class ProactiveListResponse(BaseModel):
    messages: list[ProactiveMessage]


class PatrolRequest(BaseModel):
    trigger: str = Field(default="manual", description="manual / event:new_report / event:abnormal_metric")


class PatrolResponse(BaseModel):
    should_push: bool
    message: str | None = None
    priority: str | None = None
    task_updates: list[dict] | None = None


class ProactiveReplyRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ProactiveReplyResponse(BaseModel):
    sufficient: bool
    followup: str | None = None
    task_action: dict | None = None
    metrics_saved: int = 0


class ProactiveDismissRequest(BaseModel):
    message_id: int


class ProactivePostponeRequest(BaseModel):
    message_id: int
    days: int = Field(default=1, ge=1, le=30)


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    result = await db.execute(
        select(FamilyMember.id).where(
            FamilyMember.id == member_id,
            FamilyMember.is_deleted.is_(False),
        )
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=404,
            detail=f"FamilyMember {member_id} not found",
        )


@router.get("/{member_id}/proactive/messages", response_model=ProactiveListResponse)
async def list_proactive_messages(
    member_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limited()),
) -> ProactiveListResponse:
    """List proactive messages for this member (most recent first)."""
    await _ensure_member(db, member_id)
    limit = min(limit, 50)
    result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.member_id == member_id,
            ChatMessage.source == "proactive",
        )
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    messages = []
    for r in rows:
        meta = None
        collected = False
        if r.metadata_json:
            try:
                meta = json.loads(r.metadata_json)
                collected = meta.get("collected", False)
            except json.JSONDecodeError:
                pass
        messages.append(
            ProactiveMessage(
                id=r.id,
                content=r.content,
                priority=meta.get("priority", "normal") if meta else "normal",
                created_at=r.created_at.isoformat() if r.created_at else "",
                metadata=meta,
                collected=collected,
            )
        )
    return ProactiveListResponse(messages=messages)


@router.post("/{member_id}/proactive/patrol", response_model=PatrolResponse)
async def trigger_patrol(
    member_id: int,
    body: PatrolRequest = PatrolRequest(),
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    _: None = Depends(rate_limited()),
) -> PatrolResponse:
    """Manually trigger a patrol for a specific member."""
    await _ensure_member(db, member_id)
    result = await patrol_member(db, model_router, member_id, trigger=body.trigger)
    if result is None:
        return PatrolResponse(should_push=False)
    return PatrolResponse(
        should_push=result.get("should_push", False),
        message=result.get("message"),
        priority=result.get("priority"),
        task_updates=result.get("task_updates"),
    )


@router.post("/{member_id}/proactive/reply", response_model=ProactiveReplyResponse)
async def reply_to_proactive(
    member_id: int,
    body: ProactiveReplyRequest,
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    _: None = Depends(rate_limited()),
) -> ProactiveReplyResponse:
    """Process a user's reply to a proactive message.

    The reply is saved as a normal user message, then the result collector
    extracts structured data and generates a follow-up if needed.
    """
    await _ensure_member(db, member_id)

    # Save user reply as a chat message
    user_msg = ChatMessage(
        member_id=member_id,
        role="user",
        content=body.message,
        source="webui",
        message_type="normal",
    )
    db.add(user_msg)
    await db.flush()

    # Collect and process the reply
    result = await collect_result(db, model_router, member_id, body.message)

    # If follow-up is needed, save it as an assistant message
    followup = result.get("followup")
    if followup:
        followup_msg = ChatMessage(
            member_id=member_id,
            role="assistant",
            content=followup,
            source="proactive",
            message_type="followup",
        )
        db.add(followup_msg)
        await db.commit()

    return ProactiveReplyResponse(
        sufficient=result.get("sufficient", True),
        followup=followup,
        task_action=result.get("task_action"),
        metrics_saved=result.get("metrics_saved", 0),
    )


@router.post("/{member_id}/proactive/dismiss")
async def dismiss_proactive(
    member_id: int,
    body: ProactiveDismissRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limited()),
) -> dict:
    """Dismiss a proactive message."""
    await _ensure_member(db, member_id)
    msg = await db.get(ChatMessage, body.message_id)
    if msg is None or msg.member_id != member_id or msg.source != "proactive":
        raise HTTPException(status_code=404, detail="Proactive message not found")

    # Update metadata to mark as dismissed
    meta = {}
    if msg.metadata_json:
        try:
            meta = json.loads(msg.metadata_json)
        except json.JSONDecodeError:
            pass
    meta["collected"] = True
    meta["dismissed"] = True
    msg.metadata_json = json.dumps(meta, ensure_ascii=False)
    await db.commit()
    return {"status": "dismissed"}


@router.post("/{member_id}/proactive/postpone")
async def postpone_proactive(
    member_id: int,
    body: ProactivePostponeRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(rate_limited()),
) -> dict:
    """Postpone a proactive reminder by N days."""
    await _ensure_member(db, member_id)
    msg = await db.get(ChatMessage, body.message_id)
    if msg is None or msg.member_id != member_id or msg.source != "proactive":
        raise HTTPException(status_code=404, detail="Proactive message not found")

    # Update metadata with postponement info
    meta = {}
    if msg.metadata_json:
        try:
            meta = json.loads(msg.metadata_json)
        except json.JSONDecodeError:
            pass
    meta["postponed_days"] = body.days
    meta["postponed_at"] = datetime.now(timezone.utc).isoformat()
    msg.metadata_json = json.dumps(meta, ensure_ascii=False)

    # Also postpone related tasks
    from app.models.tasks import HealthTask
    from datetime import timedelta
    patrol_id = meta.get("patrol_id", "")
    if patrol_id:
        tasks = (
            await db.execute(
                select(HealthTask).where(
                    HealthTask.member_id == member_id,
                    HealthTask.source_ref == f"patrol:{patrol_id}",
                    HealthTask.status == "open",
                )
            )
        ).scalars().all()
        for task in tasks:
            if task.due_date:
                task.due_date = task.due_date + timedelta(days=body.days)
            else:
                from datetime import date
                task.due_date = date.today() + timedelta(days=body.days)

    await db.commit()
    return {"status": "postponed", "days": body.days}
