"""Security utilities: optional bearer-token auth + per-member chat rate limiting.

Design (P0-3 + pairing):
- Auth: 若配置了 AUTH_TOKEN（非空），所有业务 API 需携带
  `Authorization: Bearer <AUTH_TOKEN>`。AUTH_TOKEN 留空 = 本地单家庭开放模式。
- Pairing: 配对码模式下，移动设备通过 POST /pair/redeem 获取独立 Bearer Token，
  该 Token 的 hash 存在 paired_devices 表中。require_auth 同时检查全局 AUTH_TOKEN
  和配对 Token。
- Rate limit: 对 /chat、/chat/stream 按 (成员ID, 窗口) 做内存级滑动窗口限流。
"""
from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)

# Cache of valid pairing token hashes (populated lazily from DB)
# token_hash → {device_id, role, member_id}
_pairing_cache: dict[str, dict] = {}
_pairing_cache_time: float = 0
_PAIRING_CACHE_TTL = 30  # refresh every 30 seconds


async def _refresh_pairing_cache() -> None:
    """Refresh the in-memory pairing token cache from the database."""
    global _pairing_cache, _pairing_cache_time
    now = time.time()
    if now - _pairing_cache_time < _PAIRING_CACHE_TTL:
        return
    try:
        from app.core.database import async_session_factory
        from app.models.paired_device import PairedDevice
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(PairedDevice.token_hash, PairedDevice.id, PairedDevice.role, PairedDevice.member_id)
                .where(PairedDevice.is_revoked.is_(False))
            )
            _pairing_cache = {
                row[0]: {"device_id": row[1], "role": row[2], "member_id": row[3]}
                for row in result
            }
            _pairing_cache_time = now
    except Exception:
        # DB not available — fail open (local mode)
        pass


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict | None:
    """FastAPI dependency enforcing bearer-token auth.

    Checks in order:
    1. If AUTH_TOKEN is empty → local open mode, no auth required
    2. If credentials match AUTH_TOKEN → global admin access (localhost)
    3. If credentials match a paired device token → device-scoped access
    4. If request is from localhost → allow (desktop mode)
    5. Otherwise → 401

    Returns a dict with optional device info for permission scoping.
    """
    token = settings.AUTH_TOKEN

    # Local open mode: no auth required
    if not token:
        # Check if request comes through Cloudflare Tunnel (public access)
        is_tunnel = bool(request.headers.get("CF-Connecting-IP"))
        client_host = request.client.host if request and request.client else ""
        is_local = (
            client_host.startswith("127.") or client_host.startswith("::1")
            or client_host == "localhost"
            or client_host.startswith("172.")  # Docker bridge
            or client_host.startswith("10.")   # Tailscale / VPN
            or client_host.startswith("192.168.")  # LAN / Docker gateway
        )
        # Local direct access (not through tunnel) → no auth required
        if is_local and not is_tunnel:
            return None
        # Public tunnel or non-local → require pairing token
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先配对设备",
                headers={"WWW-Authenticate": "Bearer"},
            )
        token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        await _refresh_pairing_cache()
        device_info = _pairing_cache.get(token_hash)
        if device_info is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 无效或已吊销，请重新配对",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return device_info

    # AUTH_TOKEN is set: check global token first
    if credentials and secrets.compare_digest(credentials.credentials, token):
        return None  # global admin

    # Check pairing token
    if credentials:
        token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        await _refresh_pairing_cache()
        device_info = _pairing_cache.get(token_hash)
        if device_info is not None:
            return device_info

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未授权：缺少或无效的访问令牌",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> None:
    """FastAPI dependency for sensitive endpoints (settings, data wipe, provider config).

    Only allows:
    - localhost (desktop browser, no tunnel headers)
    - global AUTH_TOKEN holder

    Paired devices and public tunnel requests are blocked — prevents a
    compromised or lost phone from reading API keys or wiping the database.
    """
    # If AUTH_TOKEN is set, allow it from anywhere
    token = settings.AUTH_TOKEN
    if token and credentials and secrets.compare_digest(credentials.credentials, token):
        return

    # Block all requests coming through Cloudflare Tunnel (has CF-Connecting-IP header)
    if request.headers.get("CF-Connecting-IP"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此操作仅限本机访问，不可通过公网隧道",
        )

    # Only allow direct localhost access (Docker bridge/gateway or loopback)
    # Note: X-Forwarded-For is NOT checked because Vite dev proxy and Nginx
    # reverse proxy legitimately add it for internal routing.
    client_host = request.client.host if request and request.client else ""
    is_local = (
        client_host.startswith("127.") or client_host.startswith("::1")
        or client_host == "localhost"
        or client_host.startswith("172.")  # Docker bridge
        or client_host.startswith("192.168.")  # Docker gateway / LAN
    )
    if is_local:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="此操作仅限本机访问",
    )


def _invalidate_pairing_cache() -> None:
    """Clear the pairing token cache immediately (call after revoke/renew)."""
    global _pairing_cache, _pairing_cache_time
    _pairing_cache = {}
    _pairing_cache_time = 0


def check_write_permission(device_info: dict | None) -> None:
    # TODO: Wire this into write routes (POST/PUT/DELETE) via require_write_auth dependency.
    # Currently require_auth runs at router level but its return value (device_info)
    # is not passed to individual routes. A future PR should add require_write_auth
    # as a per-route dependency for write endpoints.
    """Check if the authenticated device has write permission.

    Call this in write routes to enforce role-based access:
    - None (localhost / global token) → full access
    - admin → full access
    - viewer → read-only, raise 403
    - limited → only their member_id, raise 403 for others
    """
    if device_info is None:
        return  # localhost or global admin

    role = device_info.get("role", "admin")
    if role == "admin":
        return

    if role == "viewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只读设备无写入权限",
        )

    if role == "limited":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="受限设备仅可访问指定成员数据",
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

# Named limiters, created once. ``rate_limited()`` used to build a fresh
# _SlidingWindowLimiter on every call, so /chat and /chat/stream each got an
# independent counter — a client could use 2x the intended budget by alternating
# endpoints. Sharing a named limiter makes the documented "per-member limit"
# actually hold across the chat surface.
_LIMITERS: dict[str, _SlidingWindowLimiter] = {"chat": _chat_limiter}


def _get_limiter(name: str, max_requests: int, window_seconds: int) -> _SlidingWindowLimiter:
    limiter = _LIMITERS.get(name)
    if limiter is None:
        limiter = _SlidingWindowLimiter(
            max_requests=max_requests, window_seconds=window_seconds
        )
        _LIMITERS[name] = limiter
    return limiter


def rate_limited(
    name: str = "chat",
    max_requests: int | None = None,
    window_seconds: int = 60,
) -> Callable:
    """Return a FastAPI dependency that rate-limits a route.

    Key is derived from the request path's member_id (if present) else the
    client host. Routes that should share a budget must pass the same ``name``.
    When max_requests is None, uses the global chat limit.
    """
    if max_requests is None:
        max_requests = settings.CHAT_RATE_LIMIT_PER_MIN
    limiter = _get_limiter(name, max_requests, window_seconds)

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

async def require_write_auth(
    device_info: dict | None = Depends(require_auth),
) -> dict | None:
    """Dependency for write endpoints: require_auth + check_write_permission."""
    check_write_permission(device_info)
    return device_info
