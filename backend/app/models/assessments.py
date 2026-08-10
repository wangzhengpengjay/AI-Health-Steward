"""Scale result model — stores completed risk self-assessment answers & scores."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScaleResult(Base):
    __tablename__ = "scale_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    scale_code: Mapped[str] = mapped_column(String(32), nullable=False)  # phq9/gad7/diabetes/ascvd
    # answers JSON: {question_id: value}
    answers: Mapped[str] = mapped_column(Text, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False)  # low/moderate/high/none/mild/...
    risk_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # optional LLM interpretation
    interpretation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    advice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    member: Mapped["FamilyMember"] = relationship(  # noqa: F821
        back_populates="scale_results"
    )
