"""Multimodal API provider (required).

Uses OpenAI-compatible API for vision-capable model calls.
Supports image input (base64) and tool calling.
"""
from __future__ import annotations

import base64
from typing import AsyncIterator

import httpx

import logging
logger = logging.getLogger(__name__)

from app.providers.base import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderCapability,
    ToolCall,
    ToolDefinition,
)


class MultimodalAPIProvider(ModelProvider):
    """OpenAI-compatible multimodal API provider (e.g., GPT-4o)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__(
            name="multimodal_api",
            base_url=base_url,
            api_key=api_key,
            model=model,
            capabilities=ProviderCapability.TEXT | ProviderCapability.VISION | ProviderCapability.TOOL_CALLING,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        """Convert unified messages to OpenAI format."""
        result = []
        for msg in messages:
            entry: dict = {"role": msg.role}
            if isinstance(msg.content, str):
                entry["content"] = msg.content
            else:
                # Multimodal content: list of {type: text/image_url} parts
                entry["content"] = msg.content
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = msg.tool_calls
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

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if stream:
            return self._stream_chat(payload, headers)

        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            if resp.status_code != 200:
                logger.error("Multimodal API error %d: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        tool_calls = None
        if message.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    name=tc["function"]["name"],
                    arguments=tc["function"]["arguments"],
                )
                for tc in message["tool_calls"]
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
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
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
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False


def encode_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Encode image bytes to base64 data URL for OpenAI API."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def build_image_message(text: str, image_data_url: str) -> list[dict]:
    """Build a multimodal message with text + image."""
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]
