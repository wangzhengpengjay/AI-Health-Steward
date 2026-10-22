"""Pairing endpoints: generate pairing code, redeem for token, list/revoke devices.

# Invalidate pairing cache on revoke/renew to prevent stale token access
from app.core.security import _invalidate_pairing_cache

Flow (modeled on openGym):
1. Desktop (logged in / localhost) calls POST /pair/code → gets one-time 6-digit code
2. Mobile app enters server URL + pairing code
3. Mobile calls POST /pair/redeem with code → gets Bearer Token
4. All subsequent mobile API requests use Authorization: Bearer <token>
5. Token auto-renews: if past half-life, GET /pair/me returns a fresh token
6. Desktop can list paired devices and revoke any device
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.paired_device import PairedDevice

router = APIRouter(prefix="/pair", tags=["pairing"])

logger = logging.getLogger(__name__)

# In-memory pairing codes (short-lived, 5 min TTL)
# Code → {device_name_hint, created_at, member_id, role}
_pairing_codes: dict[str, dict] = {}
CODE_TTL_SECONDS = 300  # 5 minutes
TOKEN_TTL_SECONDS = 30 * 24 * 3600  # 30 days

# Brute-force protection: track failed redeem attempts per IP
# IP → {attempts, first_attempt_time}
_redeem_attempts: dict[str, list[float]] = {}
MAX_REDEEM_ATTEMPTS = 5  # max failed attempts per IP before lockout
REDEEM_LOCKOUT_SECONDS = 300  # 5-min lockout after max attempts


def _hash_token(token: str) -> str:
    """Hash a bearer token for secure storage (SHA-256)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_pairing_code() -> str:
    """Generate a 6-digit pairing code."""
    return f"{secrets.randbelow(1000000):06d}"


def _generate_bearer_token() -> str:
    """Generate a secure bearer token."""
    return secrets.token_urlsafe(32)


def _cleanup_expired_codes() -> None:
    """Remove expired pairing codes."""
    now = time.time()
    expired = [k for k, v in _pairing_codes.items() if now - v["created_at"] > CODE_TTL_SECONDS]
    for k in expired:
        del _pairing_codes[k]


def _is_ip_locked(ip: str) -> bool:
    """Check if an IP is locked out from redeem attempts."""
    now = time.time()
    attempts = _redeem_attempts.get(ip, [])
    # Keep only recent attempts
    attempts = [t for t in attempts if now - t < REDEEM_LOCKOUT_SECONDS]
    _redeem_attempts[ip] = attempts
    return len(attempts) >= MAX_REDEEM_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    """Record a failed redeem attempt for an IP."""
    now = time.time()
    if ip not in _redeem_attempts:
        _redeem_attempts[ip] = []
    _redeem_attempts[ip].append(now)


def _clear_failed_attempts(ip: str) -> None:
    """Clear failed attempts after a successful redeem."""
    _redeem_attempts.pop(ip, None)


# ---- Request/Response models ----

class PairingCodeRequest(BaseModel):
    device_name: Optional[str] = None
    member_id: Optional[int] = None
    role: str = "admin"  # admin | viewer | limited


class PairingCodeResponse(BaseModel):
    code: str
    expires_in: int  # seconds


class RedeemRequest(BaseModel):
    code: str
    device_name: Optional[str] = None
    platform: Optional[str] = None  # ios | android | web


class RedeemResponse(BaseModel):
    token: str
    expires_in: int
    device_id: int
    role: str
    member_id: Optional[int] = None


class DeviceInfo(BaseModel):
    id: int
    device_name: str
    platform: Optional[str]
    role: str
    member_id: Optional[int]
    paired_at: str
    last_active_at: Optional[str]
    is_revoked: bool


class RenewResponse(BaseModel):
    token: str
    expires_in: int


# ---- Endpoints ----

@router.post("/code", response_model=PairingCodeResponse)
async def generate_pairing_code(
    req: PairingCodeRequest,
    request: Request,
) -> PairingCodeResponse:
    """Generate a one-time pairing code (desktop only — localhost or existing auth)."""
    # Security: only allow from localhost / same machine / Docker internal network
    client_host = request.client.host if request.client else ""
    is_local = (
        client_host.startswith("127.")
        or client_host.startswith("::1")
        or client_host == "localhost"
        or client_host.startswith("172.")  # Docker bridge network
        or client_host.startswith("10.")   # Tailscale / VPN
        or client_host.startswith("192.168.")  # LAN
    )
    if not is_local:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="配对码只能从本机生成",
        )

    _cleanup_expired_codes()

    code = _generate_pairing_code()
    _pairing_codes[code] = {
        "device_name": req.device_name,
        "member_id": req.member_id,
        "role": req.role,
        "created_at": time.time(),
    }

    logger.info("Generated pairing code for device_name=%s", req.device_name)
    return PairingCodeResponse(code=code, expires_in=CODE_TTL_SECONDS)


@router.post("/redeem", response_model=RedeemResponse)
async def redeem_pairing_code(
    req: RedeemRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RedeemResponse:
    """Redeem a pairing code for a Bearer Token (mobile app calls this)."""
    # Brute-force protection: check IP lockout
    client_ip = request.client.host if request.client else "unknown"
    if _is_ip_locked(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"尝试次数过多，请 {REDEEM_LOCKOUT_SECONDS // 60} 分钟后再试",
        )

    _cleanup_expired_codes()

    code_data = _pairing_codes.get(req.code, None)
    if code_data is None:
        _record_failed_attempt(client_ip)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配对码无效或已过期",
        )

    # Success — remove code and clear IP attempts
    _pairing_codes.pop(req.code, None)

    _clear_failed_attempts(client_ip)

    # Generate token
    token = _generate_bearer_token()
    token_hash = _hash_token(token)
    device_name = req.device_name or code_data.get("device_name") or "Unknown Device"

    # Create paired device record
    device = PairedDevice(
        device_name=device_name,
        token_hash=token_hash,
        member_id=code_data.get("member_id"),
        platform=req.platform,
        role=code_data.get("role", "admin"),
        token_issued_at=datetime.now(timezone.utc),
        token_ttl=TOKEN_TTL_SECONDS,
    )
    db.add(device)
    await db.flush()

    logger.info("Device paired: id=%s name=%s role=%s", device.id, device_name, device.role)
    return RedeemResponse(
        token=token,
        expires_in=TOKEN_TTL_SECONDS,
        device_id=device.id,
        role=device.role,
        member_id=device.member_id,
    )


@router.get("/me", response_model=RenewResponse)
async def get_device_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RenewResponse:
    """Check token validity and auto-renew if past half-life.

    Mobile app calls this on app launch / periodically.
    If the token is past half its lifetime, issue a new one.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Bearer Token",
        )
    token = auth[7:]
    token_hash = _hash_token(token)

    result = await db.execute(
        select(PairedDevice).where(
            PairedDevice.token_hash == token_hash,
            PairedDevice.is_revoked.is_(False),
        )
    )
    device = result.scalars().first()
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已吊销",
        )

    # Update last active
    await db.execute(
        update(PairedDevice)
        .where(PairedDevice.id == device.id)
        .values(last_active_at=datetime.now(timezone.utc))
    )

    # Check if token needs renewal (past half-life)
    now = datetime.now(timezone.utc)
    age = (now - device.token_issued_at.replace(tzinfo=timezone.utc)).total_seconds()
    if age > device.token_ttl / 2:
        # Issue new token
        new_token = _generate_bearer_token()
        new_hash = _hash_token(new_token)
        await db.execute(
            update(PairedDevice)
            .where(PairedDevice.id == device.id)
            .values(
                token_hash=new_hash,
                token_issued_at=now,
            )
        )
        logger.info("Token renewed for device id=%s", device.id)
        _invalidate_pairing_cache()  # Invalidate old token immediately
        return RenewResponse(token=new_token, expires_in=device.token_ttl)

    return RenewResponse(token=token, expires_in=device.token_ttl - int(age))


@router.get("/devices", response_model=list[DeviceInfo])
async def list_devices(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[DeviceInfo]:
    """List all paired devices (desktop only — localhost)."""
    client_host = request.client.host if request.client else ""
    is_local = (
        client_host.startswith("127.") or client_host.startswith("::1")
        or client_host == "localhost"
        or client_host.startswith("172.") or client_host.startswith("10.")
        or client_host.startswith("192.168.")
    )
    if not is_local:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能从本机查看已配对设备",
        )

    result = await db.execute(
        select(PairedDevice).order_by(PairedDevice.paired_at.desc())
    )
    devices = result.scalars().all()
    return [
        DeviceInfo(
            id=d.id,
            device_name=d.device_name,
            platform=d.platform,
            role=d.role,
            member_id=d.member_id,
            paired_at=d.paired_at.isoformat() if d.paired_at else "",
            last_active_at=d.last_active_at.isoformat() if d.last_active_at else None,
            is_revoked=d.is_revoked,
        )
        for d in devices
    ]


@router.delete("/devices/{device_id}")
async def revoke_device(
    device_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a paired device (desktop only — localhost)."""
    client_host = request.client.host if request.client else ""
    is_local = (
        client_host.startswith("127.") or client_host.startswith("::1")
        or client_host == "localhost"
        or client_host.startswith("172.") or client_host.startswith("10.")
        or client_host.startswith("192.168.")
    )
    if not is_local:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能从本机吊销设备",
        )

    result = await db.execute(
        select(PairedDevice).where(PairedDevice.id == device_id)
    )
    device = result.scalars().first()
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    device.is_revoked = True
    _invalidate_pairing_cache()  # Immediately invalidate cached tokens
    logger.info("Device revoked: id=%s name=%s", device.id, device.device_name)
    return {"status": "revoked", "device_id": device_id}


@router.get("/verify")
async def verify_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify if a Bearer Token is valid (mobile app calls on launch).

    Returns device info and role/permission scope.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer Token")
    token = auth[7:]
    token_hash = _hash_token(token)

    result = await db.execute(
        select(PairedDevice).where(
            PairedDevice.token_hash == token_hash,
            PairedDevice.is_revoked.is_(False),
        )
    )
    device = result.scalars().first()
    if device is None:
        raise HTTPException(status_code=401, detail="Token 无效或已吊销")

    # Update last active
    await db.execute(
        update(PairedDevice)
        .where(PairedDevice.id == device.id)
        .values(last_active_at=datetime.now(timezone.utc))
    )

    return {
        "device_id": device.id,
        "device_name": device.device_name,
        "role": device.role,
        "member_id": device.member_id,
    }
