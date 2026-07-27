"""Base model provider interface.

All providers (multimodal API, text API, local LLM) implement this interface.
The ModelRouter selects the appropriate provider based on input type and config.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Flag, auto
from typing import Any, AsyncIterator, Optional


class ProviderCapability(Flag):
    """Capabilities a provider supports."""
    TEXT = auto()
    VISION = auto()
    TOOL_CALLING = auto()


@dataclass
class Message:
    """Unified message format for all providers."""
    role: str  # system | user | assistant | tool
    content: str | list[dict[str, Any]]  # str for text, list for multimodal
    name: Optional[str] = None  # tool name for tool messages
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None  # assistant tool calls


@dataclass
class ToolDefinition:
    """Function/tool definition for function calling."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    """A tool call requested by the model."""
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class ModelResponse:
    """Unified response from any provider."""
    content: str
    tool_calls: list[ToolCall] = None
    finish_reason: str = "stop"
    usage: dict[str, int] = None  # {"prompt_tokens": N, "completion_tokens": N}


class ModelProvider(ABC):
    """Abstract base class for all model providers."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        capabilities: ProviderCapability,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.capabilities = capabilities

    @property
    def is_configured(self) -> bool:
        """Whether this provider has valid configuration."""
        return bool(self.base_url and self.model)

    @property
    def supports_vision(self) -> bool:
        return bool(self.capabilities & ProviderCapability.VISION)

    @property
    def supports_tool_calling(self) -> bool:
        return bool(self.capabilities & ProviderCapability.TOOL_CALLING)

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolDefinition] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> ModelResponse | AsyncIterator[str]:
        """Send a chat completion request.

        If stream=True, returns an async iterator of content deltas (str).
        If stream=False, returns a ModelResponse.
        """
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Check if the provider is reachable. Returns {status, latency_ms, error}."""
        ...
