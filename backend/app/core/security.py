"""Security utilities: optional bearer-token auth + per-member chat rate limiting.

Design (P0-3):
- Auth: 若配置了 AUTH_TOKEN（非空），所有业务 API 需携带
  `Authorization: Bearer <AUTH_TOKEN>`。默认留空 = 本地单家庭开放模式，
  不改变默认体验。为开源发布/局域网多设备访问提供可选防护。
- Rate limit: 对 /chat、/chat/stream 按 (成员ID, 窗口) 做内存级滑动窗口限流，
  防止误触发或刷接口烧真实 LLM 花费。单进程内存实现即可满足单家庭规模。
"""
from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency enforcing bearer-token auth when AUTH_TOKEN is set."""
    token = settings.AUTH_TOKEN
    if not token:
        # Local open mode: no auth required
        return

    if credentials is None or not secrets.compare_digest(credentials.credentials, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未授权：缺少或无效的访问令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# Rate limiting (in-memory sliding window, keyed by member id)
# ---------------------------------------------------------------------------

class _SlidingWindowLimiter:
    """Minimal per-key sliding-window rate limiter using deque timestamps."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = __import__("asyncio").Lock()

    async def acquire(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            q = self._hits[key]
            # Drop timestamps outside the window
            while q and now - q[0] > self.window_seconds:
                q.popleft()
            if len(q) >= self.max_requests:
                return False
            q.append(now)
            return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


_chat_limiter = _SlidingWindowLimiter(
    max_requests=settings.CHAT_RATE_LIMIT_PER_MIN,
    window_seconds=60,
)


def rate_limited(
    max_requests: int | None = None, window_seconds: int = 60
) -> Callable:
    """Return a FastAPI dependency that rate-limits a route.

    Key is derived from the request path's member_id (if present) else the
    client host. When max_requests is None, uses the global chat limit.
    """
    if max_requests is None:
        max_requests = settings.CHAT_RATE_LIMIT_PER_MIN
    limiter = _SlidingWindowLimiter(max_requests=max_requests, window_seconds=window_seconds)

    async def dependency(request: Request) -> None:
        # Extract member_id from path like /members/{id}/chat
        member_id = _extract_member_id(request.url.path)
        key = f"member:{member_id}" if member_id is not None else f"host:{request.client.host}"
        ok = await limiter.acquire(key)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请稍后再试（{max_requests} 次/分钟）",
            )

    return dependency


def _extract_member_id(path: str) -> int | None:
    """Parse member id from `/members/{id}/...` path segments."""
    parts = [p for p in path.split("/") if p.isdigit()]
    return int(parts[0]) if parts else None