"""Feishu multi-channel bot manager via WebSocket long-connection.

Each FeishuChannel (DB row) = one bot instance with its own app_id/app_secret
and bound family member. All active channels start their own ws connection.

Threading model: lark ws.Client.start() is blocking and uses asyncio internally.
We run each connection in its own thread with its own event loop.
Message callbacks from lark SDK arrive in that thread — we schedule async work
on a dedicated loop per connection.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from typing import Any

import lark_oapi as lark
import lark_oapi.ws.client as _ws_module
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetImageRequest,
    GetMessageRequest,
    P2ImMessageReceiveV1,
)
import httpx as _httpx
from sqlalchemy import select

from app.core.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import async_session_factory as _main_session_factory
# ponytail: lazy engine — asyncpg connections are loop-bound, so engine must be
# created on the same loop that will use it (the feishu thread's loop).
_feishu_engine = None
_feishu_session_factory = None

def _get_feishu_session_factory():
    global _feishu_engine, _feishu_session_factory
    if _feishu_session_factory is None:
        _feishu_engine = create_async_engine(get_settings().DATABASE_URL, pool_pre_ping=True)
        _feishu_session_factory = async_sessionmaker(_feishu_engine, class_=AsyncSession, expire_on_commit=False)
    return _feishu_session_factory
from app.models.family import FamilyMember
from app.models.feishu import FeishuChannel
from app.providers.router import get_model_router
from app.services.consultation import ConsultationService
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

_processed_msg_ids: set[str] = set()


class ChannelConnection:
    """One WebSocket connection per Feishu channel, running in its own thread+loop."""

    def __init__(self, channel: FeishuChannel) -> None:
        self.channel = channel
        self._client: lark.Client | None = None
        self._ws_client: lark.ws.Client | None = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        """Start connection in a dedicated thread with its own event loop."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Run in dedicated thread: create own loop, build client, start ws."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Patch lark SDK module-level loop — it grabbed uvicorn's loop at import time.
        # We replace it with our thread's loop so ws.Client.start() works.
        _ws_module.loop = self._loop

        self._client = lark.Client.builder() \
            .app_id(self.channel.app_id) \
            .app_secret(self.channel.app_secret) \
            .build()

        dispatcher = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(self._on_message) \
            .build()

        self._ws_client = lark.ws.Client(
            self.channel.app_id,
            self.channel.app_secret,
            event_handler=dispatcher,
            log_level=lark.LogLevel.INFO,
            auto_reconnect=True,
        )
        self._connected = True
        logger.info("Feishu channel '%s' (id=%s) connecting...", self.channel.name, self.channel.id)
        try:
            self._ws_client.start()
        except Exception as e:
            logger.error("Feishu ws start error (channel=%s): %s", self.channel.id, e)
        finally:
            self._connected = False

    def stop(self) -> None:
        self._connected = False

    def _on_message(self, event: P2ImMessageReceiveV1) -> None:
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._handle_message(event), self._loop)
            else:
                logger.warning("Feishu loop not running")
        except Exception:
            logger.exception("Feishu _on_message error (channel=%s)", self.channel.id)

    # ------------------------------------------------------------------
    # Message handling (async, runs on connection's own loop)
    # ------------------------------------------------------------------

    async def _handle_message(self, event: P2ImMessageReceiveV1) -> None:
        try:
            msg = event.event.message
            msg_id = msg.message_id

            if msg_id in _processed_msg_ids:
                return
            _processed_msg_ids.add(msg_id)
            if len(_processed_msg_ids) > 500:
                _processed_msg_ids.difference_update(list(_processed_msg_ids)[:250])

            msg_type = msg.message_type
            chat_id = msg.chat_id

            async with _get_feishu_session_factory()() as db:
                member_id = self.channel.member_id
                if not member_id:
                    member = await self._get_default_member(db)
                    if not member:
                        await self._send_text(chat_id, "尚未添加家庭成员，请先在 WebUI 中添加成员。")
                        return
                    member_id = member.id

                if msg_type == "text":
                    await self._handle_text(db, member_id, chat_id, msg.content)
                elif msg_type == "image":
                    await self._handle_image(db, member_id, chat_id, msg.content, msg.message_id)
                else:
                    await self._send_text(chat_id, f"暂不支持 {msg_type} 类型消息，目前支持文字和图片。")

        except Exception:
            logger.exception("Feishu message handling failed (channel=%s)", self.channel.id)

    async def _get_default_member(self, db) -> FamilyMember | None:
        result = await db.execute(
            select(FamilyMember)
            .where(FamilyMember.is_deleted.is_(False))
            .order_by(FamilyMember.id)
            .limit(1)
        )
        return result.scalars().first()

    async def _handle_text(self, db, member_id: int, chat_id: str, content_json: str) -> None:
        content = json.loads(content_json) if isinstance(content_json, str) else content_json
        user_text = content.get("text", "").strip()
        if not user_text:
            return

        from app.providers.router import ModelRouter
        router = ModelRouter()
        service = ConsultationService(router=router, tool_registry=ToolRegistry(), db=db)
        # 指标提取完全交由工具调用 extract_and_save 完成，避免重复调用模型（P0-1）
        try:
            reply, _, _ = await service.chat(member_id=member_id, user_message=user_text, source="feishu")
            await db.commit()
        except Exception as e:
            logger.error("Feishu chat error (channel=%s): %s", self.channel.id, e)
            await db.rollback()
            reply = "咨询处理失败，请稍后重试。"
        await self._send_text(chat_id, reply)

    async def _handle_image(self, db, member_id: int, chat_id: str, content_json: str, message_id: str = "") -> None:
        content = json.loads(content_json) if isinstance(content_json, str) else content_json
        logger.info("Feishu image message content: %s", json.dumps(content, ensure_ascii=False))
        image_key = content.get("image_key", "")
        if not image_key:
            await self._send_text(chat_id, "未能获取图片标识，请重新发送。")
            return

        await self._send_text(chat_id, "正在解析报告，请稍候...")

        image_bytes = await self._download_image(image_key, message_id)
        if not image_bytes:
            await self._send_text(chat_id, "图片下载失败，请重试。")
            return

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{b64}"

        from app.providers.router import ModelRouter
        router = ModelRouter()
        service = ConsultationService(router=router, tool_registry=ToolRegistry(), db=db)
        try:
            reply, _, _ = await service.chat(
                member_id=member_id,
                user_message="请解析这份健康报告",
                image_data_url=data_url,
                source="feishu",
            )
        except Exception as e:
            logger.error("Feishu image chat error (channel=%s): %s", self.channel.id, e)
            reply = "报告解析失败，请稍后重试。"

        confirmation = (
            "报告已解析完成！\n\n"
            f"{reply}\n\n"
            "请前往 WebUI 查看完整画像和确认入档。"
        )
        await self._send_text(chat_id, confirmation)

    # ------------------------------------------------------------------
    # Feishu API helpers (sync SDK calls, run on connection's loop via run_in_executor)
    # ------------------------------------------------------------------

    async def _send_text(self, chat_id: str, text: str) -> None:
        """Send message as Feishu interactive card with Markdown rendering."""
        if not self._client:
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._send_card_sync, chat_id, text)

    def _send_card_sync(self, chat_id: str, text: str) -> None:
        """Send text as a Feishu interactive card with markdown element.

        Feishu card markdown supports: bold, italic, strikethrough, links,
        hr, lists, code blocks, images, etc.
        We split long text into multiple markdown elements (max ~3000 chars each).
        """
        elements = []
        # Split by lines to avoid exceeding content limits, chunk at ~2800 chars
        lines = text.split("\n")
        chunk_lines: list[str] = []
        chunk_len = 0
        for line in lines:
            if chunk_len + len(line) > 2800 and chunk_lines:
                elements.append({
                    "tag": "markdown",
                    "content": "\n".join(chunk_lines),
                })
                chunk_lines = []
                chunk_len = 0
            chunk_lines.append(line)
            chunk_len += len(line) + 1
        if chunk_lines:
            elements.append({
                "tag": "markdown",
                "content": "\n".join(chunk_lines),
            })

        card = {
            "elements": elements,
        }
        req = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card))
                .build()) \
            .build()
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            logger.error("Feishu send failed: code=%s msg=%s", resp.code, resp.msg)
            # Fallback to plain text if card fails
            self._send_plain_text_sync(chat_id, text)

    def _send_plain_text_sync(self, chat_id: str, text: str) -> None:
        """Fallback: send as plain text message."""
        req = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()) \
            .build()
        resp = self._client.im.v1.message.create(req)
        if not resp.success():
            logger.error("Feishu plain text send failed: code=%s msg=%s", resp.code, resp.msg)

    async def _download_image(self, image_key: str, message_id: str = "") -> bytes | None:
        if not self._client or not message_id:
            logger.error("Feishu image download: missing client or message_id")
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._download_image_sync, image_key, message_id)

    def _download_image_sync(self, image_key: str, message_id: str = "") -> bytes | None:
        """Download image via GET /im/v1/messages/:message_id/resources/:file_key?type=image"""
        import requests as _req
        # Get tenant_access_token
        try:
            token_r = _req.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.channel.app_id, "app_secret": self.channel.app_secret},
                timeout=10,
            )
            token = token_r.json().get("tenant_access_token")
            if not token:
                logger.error("Feishu token fetch failed: %s", token_r.text)
                return None
        except Exception as e:
            logger.error("Feishu token fetch error: %s", e)
            return None

        # Download via message resource endpoint
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{image_key}"
        try:
            resp = _req.get(url, headers={"Authorization": f"Bearer {token}"}, params={"type": "image"}, timeout=30)
            if resp.status_code == 200:
                logger.info("Feishu image downloaded: %d bytes", len(resp.content))
                return resp.content
            logger.error("Feishu image download failed: status=%s body=%s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.error("Feishu image download error: %s", e)
        return None


class FeishuBot:
    """Manages all active Feishu channel connections."""

    def __init__(self) -> None:
        self._connections: dict[int, ChannelConnection] = {}

    @property
    def connections(self) -> dict[int, ChannelConnection]:
        return self._connections

    async def start_all(self) -> None:
        """Load all active channels from DB and start connections."""
        async with _main_session_factory() as db:
            result = await db.execute(
                select(FeishuChannel).where(FeishuChannel.is_active.is_(True))
            )
            channels = result.scalars().all()

        if not channels:
            logger.info("No active Feishu channels configured")
            return

        for ch in channels:
            self._start_channel(ch)

    def _start_channel(self, channel: FeishuChannel) -> None:
        if channel.id in self._connections:
            old = self._connections.pop(channel.id)
            old.stop()
        conn = ChannelConnection(channel)
        self._connections[channel.id] = conn
        conn.start()

    async def stop_all(self) -> None:
        for conn in self._connections.values():
            conn.stop()
        self._connections.clear()
        logger.info("All Feishu connections stopped")

    async def reload(self) -> None:
        """Reload channels from DB — stop removed, start new."""
        async with _main_session_factory() as db:
            result = await db.execute(
                select(FeishuChannel).where(FeishuChannel.is_active.is_(True))
            )
            active_channels = result.scalars().all()
            active_ids = {ch.id for ch in active_channels}

        for cid in list(self._connections.keys()):
            if cid not in active_ids:
                self._connections[cid].stop()
                del self._connections[cid]
                logger.info("Feishu channel %s stopped", cid)

        for ch in active_channels:
            # Always rebuild — channel config (member_id, app_id, etc) may have changed
            self._start_channel(ch)

    def get_status(self) -> list[dict]:
        return [
            {
                "channel_id": cid,
                "connected": conn.connected,
                "name": conn.channel.name,
            }
            for cid, conn in self._connections.items()
        ]


# Singleton
feishu_bot = FeishuBot()
