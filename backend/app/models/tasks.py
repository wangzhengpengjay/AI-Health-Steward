"""Health task (to-do / reminder) model.

Represents actionable items for a family member — medication reminders,
recheck alerts, checkup appointments, vaccination due, chronic follow-ups,
and custom user tasks. Auto-generated from health events and also user-managed.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class HealthTask(Base):
    __tablename__ = "health_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(24), nullable=False)  # medication/recheck/checkup/vaccination/followup/custom
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal", nullable=False)  # critical/high/normal/low
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="open", nullable=False)  # open/done/dismissed
    # source link, e.g. "metric:123" / "med:7" / "checkup:2" / "diagnosis:4"
    source_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    auto_generated: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    member: Mapped["FamilyMember"] = relationship(  # noqa: F821
        back_populates="tasks"
    )