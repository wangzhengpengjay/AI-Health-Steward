"""Chat endpoints for AI health consultations."""
from __future__ import annotations

import base64
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.family import FamilyMember
from app.providers.router import ModelRouter, ProviderNotConfiguredError, get_model_router
from app.services.consultation import ConsultationService
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/members", tags=["chat"])

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_PDF_TYPE = "application/pdf"


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


def _file_to_data_url(file: UploadFile) -> str:
    """Convert uploaded file to base64 data URL."""
    content = file.file.read()
    if len(content) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件过大，请上传 20MB 以内的文件",
        )

    mime = file.content_type or "application/octet-stream"

    if mime in ALLOWED_IMAGE_TYPES:
        b64 = base64.b64encode(content).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    if mime == ALLOWED_PDF_TYPE:
        # PDF — encode as base64, model provider handles PDF input
        b64 = base64.b64encode(content).decode("utf-8")
        return f"data:application/pdf;base64,{b64}"

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"不支持的文件类型: {mime}，仅支持 JPG/PNG/WebP/PDF",
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


@router.post("/{member_id}/chat", response_model=ChatResponse)
async def chat(
    member_id: int,
    message: str = Form(...),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> ChatResponse:
    """Non-streaming chat endpoint. Supports optional image/PDF upload."""
    await _ensure_member(db, member_id)

    image_data_url = None
    if file:
        image_data_url = _file_to_data_url(file)

    service = ConsultationService(
        router=model_router,
        tool_registry=ToolRegistry(),
        db=db,
    )
    try:
        reply, tool_calls, risk_level = await service.chat(
            member_id=member_id,
            user_message=message,
            image_data_url=image_data_url,
        )
    except ProviderNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI 服务暂时不可用: {e}",
        )
    return ChatResponse(
        reply=reply,
        tool_calls=[ToolCallRecord(**tc) for tc in tool_calls],
        risk_level=risk_level,
    )


@router.post("/{member_id}/chat/stream")
async def chat_stream(
    member_id: int,
    message: str = Form(...),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
) -> StreamingResponse:
    """SSE streaming chat endpoint. Supports optional image/PDF upload."""
    await _ensure_member(db, member_id)

    image_data_url = None
    if file:
        image_data_url = _file_to_data_url(file)

    service = ConsultationService(
        router=model_router,
        tool_registry=ToolRegistry(),
        db=db,
    )

    async def event_generator():
        try:
            async for delta in service.chat_stream(
                member_id=member_id,
                user_message=message,
                image_data_url=image_data_url,
            ):
                data = json.dumps({"delta": delta}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except ProviderNotConfiguredError as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        except Exception as e:
            logger.exception("Stream chat failed")
            err = json.dumps({"error": f"AI 服务暂时不可用: {e}"}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
