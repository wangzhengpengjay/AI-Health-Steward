"""Chat endpoints for AI health consultations."""
from __future__ import annotations

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_db
from app.core.security import rate_limited
from app.models.family import FamilyMember
from app.models.health import ChatMessage
from app.providers.router import ModelRouter, ProviderNotConfiguredError, get_model_router
from app.services.consultation import ConsultationService
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/members", tags=["chat"])


async def _compress_memory_in_background(member_id: int, router: ModelRouter) -> None:
    """后台压缩长期记忆: 使用独立 DB session, 不占用 SSE 连接/请求 session.

    流式咨询把 delta 全部推给前端后会立即发 [DONE] 并关闭连接;
    长期记忆压缩(maybe_compact_memory 内部会调用 LLM, 可能耗时数秒~十几秒)
    绝不可阻塞流式收尾, 因此在后台独立运行.
    """
    try:
        async with async_session_factory() as db:
            from app.services.member_memory import maybe_compact_memory

            await maybe_compact_memory(db, router, member_id, "webui")
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("Background memory compaction failed for member %s", member_id)

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


class HistoryMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ChatHistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    has_more: bool = False


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


@router.get("/{member_id}/chat/history", response_model=ChatHistoryResponse)
async def chat_history(
    member_id: int,
    limit: int = 50,
    before_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> ChatHistoryResponse:
    """Return the member's persisted webui chat history (ascending).

    Paginated: loads up to `limit` messages. If `before_id` is provided,
    loads messages with id < before_id (for infinite scroll / load-more).
    The frontend should request the first page without before_id, then
    pass the oldest message id as before_id to load older messages.
    """
    await _ensure_member(db, member_id)
    limit = min(limit, 200)  # hard cap
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.member_id == member_id, ChatMessage.source == "webui")
        .order_by(ChatMessage.id.desc())
        .limit(limit + 1)  # fetch one extra to check has_more
    )
    if before_id is not None:
        stmt = stmt.where(ChatMessage.id < before_id)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    rows.reverse()  # back to ascending order
    messages = [
        HistoryMessage(
            id=r.id,
            role=r.role,
            content=r.content,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]
    return ChatHistoryResponse(messages=messages, has_more=has_more)


@router.post("/{member_id}/chat", response_model=ChatResponse)
async def chat(
    member_id: int,
    message: str = Form(...),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    model_router: ModelRouter = Depends(get_model_router),
    _: None = Depends(rate_limited()),
) -> ChatResponse:
    """Non-streaming chat endpoint. Supports optional image/PDF upload."""
    await _ensure_member(db, member_id)

    image_data_url = None
    if file:
        image_data_url = _file_to_data_url(file)

    # 指标提取完全交由工具调用 extract_and_save 完成，避免重复调用模型（P0-1）
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
    _: None = Depends(rate_limited()),
) -> StreamingResponse:
    """SSE streaming chat endpoint. Supports optional image/PDF upload.

    Emits two event types:
    - {"report": {...}} — report extraction result (when image/PDF attached)
    - {"delta": "..."}  — streamed text chunks
    """
    await _ensure_member(db, member_id)

    image_data_url = None
    if file:
        image_data_url = _file_to_data_url(file)

    # 指标提取完全交由工具调用 extract_and_save 完成，避免重复调用模型（P0-1）
    service = ConsultationService(
        router=model_router,
        tool_registry=ToolRegistry(),
        db=db,
    )

    async def event_generator():
        try:
            async for event_type, data in service.chat_stream(
                member_id=member_id,
                user_message=message,
                image_data_url=image_data_url,
            ):
                payload = json.dumps({event_type: data}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except ProviderNotConfiguredError as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        except Exception as e:
            logger.exception("Stream chat failed")
            err = json.dumps({"error": f"AI 服务暂时不可用: {e}"}, ensure_ascii=False)
            yield f"data: {err}\n\n"
        # 先发送 [DONE] 解除前端"持续输出"状态; 长期记忆压缩走后台任务,
        # 不阻塞流式收尾, 连接在 DONE 后立即关闭.
        yield "data: [DONE]\n\n"
        try:
            asyncio.create_task(_compress_memory_in_background(member_id, model_router))
        except Exception:  # noqa: BLE001
            logger.exception("Could not schedule background memory compaction for member %s", member_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
