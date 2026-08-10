"""Family member model (D8 field family A: basic info)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    gender: Mapped[str] = mapped_column(String(16), nullable=False)  # male/female/other
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    height: Mapped[Optional[float]] = mapped_column(nullable=True)  # cm
    weight: Mapped[Optional[float]] = mapped_column(nullable=True)  # kg
    bmi: Mapped[Optional[float]] = mapped_column(nullable=True)  # computed
    blood_type: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # A/B/AB/O[+/-]
    member_relation: Mapped[Optional[str]] = mapped_column("relationship", String(32), nullable=True)

    # Checkup recommendation: region & occupation
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Checkup safety: contraindication fields (default "unknown")
    is_pregnant: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    is_preparing_pregnancy: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    has_sexual_history: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    contrast_allergy: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    has_pacemaker: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    has_metal_implant: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    egfr: Mapped[Optional[float]] = mapped_column(nullable=True)
    on_anticoagulant: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    claustrophobia: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    is_breastfeeding: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    has_coagulopathy: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)
    has_heart_failure: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    is_deleted: Mapped[bool] = mapped_column(default=False, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Long-term conversation memory (P1-4): rolling summary of prior consultations
    memory_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    memory_summary_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # relationships
    metrics: Mapped[list["MetricRecord"]] = relationship(  # noqa: F821
        back_populates="member", cascade="all, delete-orphan"
    )
