"""Chat endpoints for AI health consultations."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.providers.router import ModelRouter, get_model_router
from app.services.consultation import ConsultationService
from app.services.tools.registry import ToolRegistry

router = APIRouter(prefix="/members", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None


class ToolCallRecord(BaseModel):
    name: str
    arguments: str
    result: dict


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallRecord]
    risk_level: str


@router.post("/{member_id}/chat", response_model=ChatResponse)
async def chat(
    member_id: int,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> ChatResponse:
    """Non-streaming chat endpoint."""
    await _ensure_member(db, member_id)

    service = ConsultationService(
        router=model_router,
        tool_registry=ToolRegistry(),
        db=db,
    )
    try:
        reply, tool_calls, risk_level = await service.chat(
            member_id=member_id,
            user_message=payload.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI 服务暂时不可用: {str(e)}",
        )
    return ChatResponse(
        reply=reply,
        tool_calls=[ToolCallRecord(**tc) for tc in tool_calls],
        risk_level=risk_level,
    )


@router.post("/{member_id}/chat/stream")
async def chat_stream(
    member_id: int,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> StreamingResponse:
    """SSE streaming chat endpoint."""
    await _ensure_member(db, member_id)

    service = ConsultationService(
        router=model_router,
        tool_registry=ToolRegistry(),
        db=db,
    )

    async def event_generator():
        async for delta in service.chat_stream(
            member_id=member_id,
            user_message=payload.message,
        ):
            data = json.dumps({"delta": delta}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


async def _ensure_member(db: AsyncSession, member_id: int) -> None:
    result = await db.execute(
        select(FamilyMember.id).where(
            FamilyMember.id == member_id,
            FamilyMember.is_deleted.is_(False),
        )
    )
    if result.scalars().first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FamilyMember {member_id} not found",
        )
