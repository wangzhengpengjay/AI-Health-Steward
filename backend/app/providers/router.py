"""Model router — selects the right provider based on input type and config.

Routing logic (per design.md TD4 and model-provider spec):
- Vision input (image/PDF) → MultimodalAPIProvider (required, no fallback)
- Text input → TextAPIProvider or LocalLLMProvider, by TEXT_PROVIDER_PRIORITY config
- If the priority provider is not configured, falls back to the other
- If neither text provider is configured, raises an error

The router also exposes health-check and capability info for the settings UI.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.core.config import settings
from app.providers.base import (
    Message,
    ModelProvider,
    ModelResponse,
    ProviderCapability,
    ToolDefinition,
)
from app.providers.local_llm import LocalLLMProvider
from app.providers.multimodal import MultimodalAPIProvider
from app.providers.text import TextAPIProvider


class ProviderNotConfiguredError(Exception):
    """Raised when a required provider is not configured."""


class ModelRouter:
    """Routes requests to the appropriate model provider."""

    def __init__(self):
        self._multimodal = MultimodalAPIProvider(
            base_url=settings.MULTIMODAL_API_BASE,
            api_key=settings.MULTIMODAL_API_KEY,
            model=settings.MULTIMODAL_API_MODEL,
        )
        self._text_api = TextAPIProvider(
            base_url=settings.TEXT_API_BASE,
            api_key=settings.TEXT_API_KEY,
            model=settings.TEXT_API_MODEL,
        )
        self._local_llm = LocalLLMProvider(
            base_url=settings.LOCAL_LLM_BASE,
            model=settings.LOCAL_LLM_MODEL,
        )

    @property
    def multimodal_provider(self) -> MultimodalAPIProvider:
        return self._multimodal

    @property
    def text_api_provider(self) -> TextAPIProvider:
        return self._text_api

    @property
    def local_llm_provider(self) -> LocalLLMProvider:
        return self._local_llm

    def get_multimodal_provider(self) -> MultimodalAPIProvider:
        """Get the multimodal provider. Raises if not configured."""
        if not self._multimodal.is_configured:
            raise ProviderNotConfiguredError(
                "报告导入需要配置多模态 API，请前往系统设置配置"
            )
        return self._multimodal

    def get_text_provider(self) -> ModelProvider:
        """Get the text provider based on config priority.

        Falls back to the other text provider if the priority one is not configured.
        """
        priority = settings.TEXT_PROVIDER_PRIORITY

        if priority == "local_llm":
            if self._local_llm.is_configured:
                return self._local_llm
            if self._text_api.is_configured:
                return self._text_api
        else:  # default: text_api
            if self._text_api.is_configured:
                return self._text_api
            if self._local_llm.is_configured:
                return self._local_llm

        raise ProviderNotConfiguredError(
            "没有可用的文字模型 provider，请配置文字 API 或本地 LLM"
        )

    def has_multimodal(self) -> bool:
        return self._multimodal.is_configured

    def has_text(self) -> bool:
        return self._text_api.is_configured or self._local_llm.is_configured

    def get_provider_status(self) -> dict:
        """Return status of all providers for settings UI."""
        return {
            "multimodal_api": {
                "configured": self._multimodal.is_configured,
                "base_url": self._multimodal.base_url,
                "model": self._multimodal.model,
                "capabilities": ["text", "vision", "tool_calling"],
            },
            "text_api": {
                "configured": self._text_api.is_configured,
                "base_url": self._text_api.base_url,
                "model": self._text_api.model,
                "capabilities": ["text", "tool_calling"],
            },
            "local_llm": {
                "configured": self._local_llm.is_configured,
                "base_url": self._local_llm.base_url,
                "model": self._local_llm.model,
                "capabilities": ["text", "tool_calling"],
            },
            "text_priority": settings.TEXT_PROVIDER_PRIORITY,
            "multimodal_available": self.has_multimodal(),
            "text_available": self.has_text(),
        }

    def route(
        self,
        messages: list[Message],
        *,
        has_vision: bool = False,
    ) -> ModelProvider:
        """Determine which provider to use based on input type.

        Args:
            messages: The message list (not used for routing, but available).
            has_vision: Whether the input contains image/PDF content.

        Returns:
            The appropriate ModelProvider instance.

        Raises:
            ProviderNotConfiguredError: If the required provider is not configured.
        """
        if has_vision:
            return self.get_multimodal_provider()
        return self.get_text_provider()


@lru_cache
def get_model_router() -> ModelRouter:
    """Singleton router instance."""
    return ModelRouter()
