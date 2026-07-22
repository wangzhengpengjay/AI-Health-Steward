"""AI consultation service — orchestrates model provider + tool calling.

The service builds a system prompt with role/knowledge-boundary constraints,
sends the conversation to the text model with tool definitions, executes any
tool calls the model returns, feeds the results back, and produces the final
reply. Both non-streaming (chat) and streaming (chat_stream) entry points are
provided.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import Message, ModelProvider, ModelResponse, ToolCall
from app.providers.router import ModelRouter
from app.services.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
你是"AI健康管家"，一个帮助家庭管理健康数据的智能助手。

你的能力范围：
1. 查询和分析用户已录入的健康指标（血压、血糖、血脂、心率、体重等）
2. 查询用户的诊断记录、用药记录、过敏信息
3. 解读指标是否正常（基于参考范围）
4. 提供常规健康科普建议（饮食、运动等）
5. 从对话中提取用户提到的健康数据并记录到画像

你的边界（不能做的事）：
- 不能进行医疗诊断
- 不能开具处方或建议停药
- 不能替代医生的专业判断
- 遇到急性症状（胸痛、呼吸困难等）或危急值，必须建议立即就医

风险分级：
- S级（禁止输出）：建议停药、开具处方、进行诊断 → 回复"该问题超出能力范围，请就医"
- A级（高风险警示）：用药相互作用、症状可能关联严重疾病 → 附带"此建议涉及用药安全，请务必遵医嘱"
- B级（常规）：饮食建议、运动指导、指标解读 → 正常回答

回答时始终基于用户画像中的实际数据，不要编造数据。如果数据不足，引导用户上传报告或手动录入。
"""

# Keywords that hint at higher-risk conversations for risk-level tagging.
_S_LEVEL_KEYWORDS = ["停药", "处方", "诊断", "开药"]
_A_LEVEL_KEYWORDS = ["用药", "药物", "相互作用", "副作用", "胸痛", "呼吸困难", "急症"]


class ConsultationService:
    """Orchestrates the model provider and health tools for a consultation."""

    def __init__(
        self,
        router: ModelRouter,
        tool_registry: ToolRegistry,
        db: AsyncSession,
    ) -> None:
        self.router = router
        self.tools = tool_registry
        self.db = db

    async def chat(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
    ) -> tuple[str, list[dict[str, Any]], str]:
        """Run a full (non-streaming) consultation turn.

        Returns:
            A tuple of (reply_text, tool_call_records, risk_level).
        """
        provider = self.router.get_text_provider()
        messages = self._build_messages(user_message, conversation_history)
        tool_defs = self.tools.get_all_tool_definitions()

        tool_call_records: list[dict[str, Any]] = []
        max_rounds = 5  # safety limit on tool-calling loops

        for _ in range(max_rounds):
            response: ModelResponse = await provider.chat(
                messages, tools=tool_defs if tool_defs else None
            )

            if not response.tool_calls:
                reply = response.content or ""
                risk_level = self._assess_risk(user_message, reply)
                return reply, tool_call_records, risk_level

            # The model wants to call tools — append the assistant message and
            # execute each requested call.
            # Build tool_calls in OpenAI format for the assistant message
            tool_calls_oi = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ]
            messages.append(
                Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=tool_calls_oi,
                )
            )

            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                tool_call_records.append(
                    {"name": tc.name, "arguments": tc.arguments, "result": result}
                )
                messages.append(
                    Message(
                        role="tool",
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        name=tc.name,
                        tool_call_id=tc.id,
                    )
                )

        # Exhausted the loop — ask the model for a final summary without tools.
        response = await provider.chat(messages, tools=None)
        reply = response.content or ""
        risk_level = self._assess_risk(user_message, reply)
        return reply, tool_call_records, risk_level

    async def chat_stream(
        self,
        member_id: int,
        user_message: str,
        conversation_history: list[Message] | None = None,
    ) -> AsyncIterator[str]:
        """Stream the final reply as content deltas (for SSE).

        Tool-calling rounds are performed non-streaming; only the final
        response is streamed to the client.
        """
        provider = self.router.get_text_provider()
        messages = self._build_messages(user_message, conversation_history)
        tool_defs = self.tools.get_all_tool_definitions()

        max_rounds = 5

        for _ in range(max_rounds):
            response: ModelResponse = await provider.chat(
                messages, tools=tool_defs if tool_defs else None
            )

            if not response.tool_calls:
                # Final answer — re-request in stream mode so we can yield deltas.
                async for delta in await provider.chat(  # type: ignore[assignment]
                    messages, tools=None, stream=True
                ):
                    yield delta
                return

            # Build tool_calls in OpenAI format for the assistant message
            tool_calls_oi = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ]
            messages.append(
                Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=tool_calls_oi,
                )
            )

            for tc in response.tool_calls:
                result = await self._execute_tool_call(tc, member_id)
                messages.append(
                    Message(
                        role="tool",
                        content=json.dumps(result, ensure_ascii=False, default=str),
                        name=tc.name,
                        tool_call_id=tc.id,
                    )
                )

        # Fallback: stream whatever the model produces without tools.
        async for delta in await provider.chat(messages, tools=None, stream=True):  # type: ignore[assignment]
            yield delta

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_messages(
        self, user_message: str, history: list[Message] | None
    ) -> list[Message]:
        messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
        if history:
            messages.extend(history)
        messages.append(Message(role="user", content=user_message))
        return messages

    async def _execute_tool_call(
        self, tc: ToolCall, member_id: int
    ) -> dict[str, Any]:
        """Execute a single ToolCall and return its result dict."""
        tool = self.tools.get_tool(tc.name)
        if tool is None:
            return {"error": f"未知工具: {tc.name}"}

        try:
            arguments = json.loads(tc.arguments) if tc.arguments else {}
        except json.JSONDecodeError:
            return {"error": f"工具参数解析失败: {tc.arguments}"}

        try:
            result = await tool.execute(self.db, member_id, **arguments)
            await self.db.flush()
            return result
        except Exception as exc:
            logger.exception("Tool %s execution failed", tc.name)
            return {"error": f"工具执行失败: {exc}"}

    @staticmethod
    def _assess_risk(user_message: str, reply: str) -> str:
        """Heuristic risk-level assessment for response tagging."""
        combined = (user_message + reply).lower()
        if any(kw in combined for kw in _S_LEVEL_KEYWORDS):
            return "S"
        if any(kw in combined for kw in _A_LEVEL_KEYWORDS):
            return "A"
        return "B"
