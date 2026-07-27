"""Feishu channel model — one row per configured Feishu bot."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeishuChannel(Base):
    __tablename__ = "feishu_channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 渠道名称，如"爸爸的飞书"
    app_id: Mapped[str] = mapped_column(String(128), nullable=False)
    app_secret: Mapped[str] = mapped_column(String(256), nullable=False)
    # 绑定的家庭成员 ID，null=默认本人
    member_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
