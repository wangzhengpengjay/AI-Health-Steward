"""Health summary model — periodic (weekly/monthly/annual) review reports.

Summaries aggregate a member's metrics, abnormal events, new diagnoses and
medications over a period, producing a human-readable review (stats + optional
LLM interpretation) that helps track management effectiveness.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HealthSummary(Base):
    __tablename__ = "health_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    summary_type: Mapped[str] = mapped_column(String(16), default="auto", nullable=False)  # auto/manual
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # weekly/monthly/annual
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    # Structured stats for frontend rendering (JSON): metric trends, abnormal events, etc.
    stats_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Abnormal / critical events list (JSON)
    abnormal_events: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Markdown review body
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    member: Mapped["FamilyMember"] = relationship(  # noqa: F821
        back_populates="summaries"
    )