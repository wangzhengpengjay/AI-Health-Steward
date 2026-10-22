"""Paired device model: tracks mobile devices paired via pairing code."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PairedDevice(Base):
    __tablename__ = "paired_devices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Human-friendly device name (e.g. "iPhone 15 Pro", "妈妈的手机")
    device_name: Mapped[str] = mapped_column(String(128), nullable=False, default="Unknown Device")
    # The bearer token issued to this device (stored as hash for security)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Optional: scope this device to a specific family member
    member_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    # Platform: ios / android / web
    platform: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # Role: admin (full access) | viewer (read-only) | limited (specific member only)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="admin")
    # Pairing metadata
    paired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_revoked: Mapped[bool] = mapped_column(default=False, nullable=False)
    # For token auto-renewal: track issued and expiry
    token_issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Token lifetime in seconds (default 30 days)
    token_ttl: Mapped[int] = mapped_column(default=2592000, nullable=False)
