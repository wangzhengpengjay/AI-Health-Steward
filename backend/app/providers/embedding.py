"""Embedding provider — calls OpenAI-compatible /embeddings endpoint.

Reuses TEXT_API_BASE / TEXT_API_KEY by default, or dedicated EMBEDDING_API_BASE / EMBEDDING_API_KEY.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingProvider:
    """OpenAI-compatible embeddings API client."""

    def __init__(self) -> None:
        _s = get_settings()
        self.base_url = (_s.EMBEDDING_API_BASE or _s.TEXT_API_BASE).rstrip("/")
        self.api_key = _s.EMBEDDING_API_KEY or _s.TEXT_API_KEY
        self.model = _s.EMBEDDING_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text. Returns float vector."""
        if not self.is_configured:
            raise RuntimeError("Embedding model 未配置，请在设置中配置 EMBEDDING_MODEL")
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": text},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["data"][0]["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        if not self.is_configured:
            raise RuntimeError("Embedding model 未配置")
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                json={"model": self.model, "input": texts},
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        # Sort by index to ensure order
        items = sorted(data["data"], key=lambda d: d["index"])
        return [item["embedding"] for item in items]

    async def health_check(self) -> dict:
        import time
        t0 = time.monotonic()
        if not self.is_configured:
            return {"status": "not_configured", "latency_ms": 0}
        try:
            vec = await self.embed("test")
            ms = int((time.monotonic() - t0) * 1000)
            return {"status": "ok", "latency_ms": ms, "dimensions": len(vec)}
        except Exception as e:
            ms = int((time.monotonic() - t0) * 1000)
            return {"status": "error", "latency_ms": ms, "error": str(e)}
