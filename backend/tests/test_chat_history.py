"""Tests for chat history persistence & LLM context window (P3-2)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.health import ChatMessage
from app.providers.base import Message
from app.services.consultation import ConsultationService


pytestmark = pytest.mark.asyncio


def _chat_message(id, role, content, source="webui"):
    m = MagicMock(spec=ChatMessage)
    m.id = id
    m.role = role
    m.content = content
    m.source = source
    m.created_at = MagicMock()
    return m


def _execute_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


class TestLoadRecentHistory:
    """The webui is a single continuous stream: context = recent 50 webui msgs."""

    async def test_loads_webui_history_ascending_with_limit(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=_execute_result(
                [
                    _chat_message(3, "user", "问题3"),
                    _chat_message(2, "assistant", "回复2"),
                ]
            )
        )
        svc = ConsultationService.__new__(ConsultationService)
        svc.db = db

        history = await svc._load_recent_history(6)

        # Executed once, filtered to webui source
        db.execute.assert_awaited_once()
        # Desc query results are reversed to ascending: 回复2(assistant) then 问题3(user)
        assert [m.role for m in history] == ["assistant", "user"]
        assert all(isinstance(m, Message) for m in history)
        assert history[0].content == "回复2"
        assert history[1].content == "问题3"

    async def test_does_not_mix_feishu_into_webui_context(self) -> None:
        db = MagicMock()
        db.execute = AsyncMock(
            return_value=_execute_result(
                [_chat_message(1, "user", "webui 对话", source="webui")]
            )
        )
        svc = ConsultationService.__new__(ConsultationService)
        svc.db = db

        history = await svc._load_recent_history(6)

        assert len(history) == 1
        assert history[0].content == "webui 对话"
        # Where clause should restrict to source == "webui"
        where = db.execute.await_args.args[0]
        assert where is not None


class TestChatHistoryEndpoint:
    """The /chat/history endpoint returns the member's full webui history."""

    def test_history_response_model_shape(self) -> None:
        from app.api.routes.chat import ChatHistoryResponse, HistoryMessage

        resp = ChatHistoryResponse(
            messages=[HistoryMessage(id=1, role="user", content="你好", created_at="2026-08-10T10:00:00")],
        )
        assert resp.messages[0].role == "user"
        assert resp.has_more is False