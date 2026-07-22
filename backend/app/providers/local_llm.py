"""Local LLM provider (optional).

Uses Ollama-compatible API for local model calls.
Only supports text input — no vision capability.
Supports tool calling if the local model supports it.
"""
from __future__ import annotations

from typing import AsyncIterator

import httpx

from app.providers.base import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderCapability,
    ToolCall,
    ToolDefinition,
)


class LocalLLMProvider(ModelProvider):
    """Ollama-compatible local LLM provider (e.g., llama3 via Ollama)."""

    def __init__(self, base_url: str, model: str):
        super().__init__(
            name="local_llm",
            base_url=base_url,
            api_key="ollama",  # Ollama doesn't require a real key
            model=model,
            capabilities=ProviderCapability.TEXT | ProviderCapability.TOOL_CALLING,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        result = []
        for msg in messages:
            entry: dict = {"role": msg.role}
            if isinstance(msg.content, str):
                entry["content"] = msg.content
            else:
                # Local LLM: text only, strip images
                text_parts = [
                    p.get("text", "") for p in msg.content if p.get("type") == "text"
                ]
                entry["content"] = "\n".join(text_parts) or "(empty)"
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict] | None:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> ModelResponse | AsyncIterator[str]:
        payload: dict = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        tool_defs = self._build_tools(tools)
        if tool_defs:
            payload["tools"] = tool_defs

        headers = {"Content-Type": "application/json"}

        if stream:
            return self._stream_chat(payload, headers)

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc.get("id", f"call_{i}"),
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for i, tc in enumerate(message["tool_calls"])
            ]

        return ModelResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage"),
        )

    async def _stream_chat(
        self, payload: dict, headers: dict
    ) -> AsyncIterator[str]:
        payload["stream"] = True
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk == "[DONE]":
                        break
                    import json
                    data = json.loads(chunk)
                    delta = data["choices"][0].get("delta", {})
                    if content := delta.get("content"):
                        yield content

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/models")
                return resp.status_code == 200
        except Exception:
            return False
