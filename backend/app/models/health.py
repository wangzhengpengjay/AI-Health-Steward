"""Health profile models (D8 field families B-H).

B MetricRecord  - physiological metrics (time-series)
C Diagnosis     - diagnosis records
D Medication    - medication records
E Allergy       - allergies & contraindications
F Lifestyle     - lifestyle factors
G FamilyHistory - family medical history
H DataProvenance- data provenance for any record
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from pgvector.sqlalchemy import Vector


class MetricRecord(Base):
    """B physiological metrics (time-series, one row per measurement)."""

    __tablename__ = "metric_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reference_lower: Mapped[Optional[float]] = mapped_column(nullable=True)
    reference_upper: Mapped[Optional[float]] = mapped_column(nullable=True)
    is_abnormal: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_critical: Mapped[bool] = mapped_column(default=False, nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    context: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # fasting/postmeal/...
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    member: Mapped["FamilyMember"] = relationship(  # noqa: F821
        back_populates="metrics"
    )


class Diagnosis(Base):
    """C diagnosis records."""

    __tablename__ = "diagnoses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    disease_name: Mapped[str] = mapped_column(String(128), nullable=False)
    icd_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    diagnosed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active/past/cured

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    medications: Mapped[list["Medication"]] = relationship(back_populates="diagnosis")


class Medication(Base):
    """D medication records."""

    __tablename__ = "medications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    drug_name: Mapped[str] = mapped_column(String(128), nullable=False)
    generic_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dosage: Mapped[str] = mapped_column(String(64), nullable=False)
    frequency: Mapped[str] = mapped_column(String(64), nullable=False)
    route: Mapped[str] = mapped_column(String(32), default="oral", nullable=False)  # oral/injection/topical/other
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    diagnosis_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("diagnoses.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    diagnosis: Mapped[Optional["Diagnosis"]] = relationship(back_populates="medications")


class Allergy(Base):
    """E allergies & contraindications."""

    __tablename__ = "allergies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # drug/food/other
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="mild", nullable=False)  # mild/moderate/severe
    recorded_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Lifestyle(Base):
    """F lifestyle factors."""

    __tablename__ = "lifestyles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(16), nullable=False)  # smoking/drinking/exercise/sleep/diet
    status: Mapped[str] = mapped_column(String(128), nullable=False)
    frequency: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FamilyHistory(Base):
    """G family medical history."""

    __tablename__ = "family_histories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)  # father/mother/brother/sister/grandparent/other
    disease_name: Mapped[str] = mapped_column(String(128), nullable=False)
    recorded_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
class Surgery(Base):
    """Surgical history records."""

    __tablename__ = "surgeries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    surgery_name: Mapped[str] = mapped_column(String(128), nullable=False)
    surgery_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hospital: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Vaccination(Base):
    """Vaccination history records."""

    __tablename__ = "vaccinations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    vaccine_name: Mapped[str] = mapped_column(String(128), nullable=False)
    dose_no: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # 1st/2nd/booster
    vaccinated_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    facility: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataProvenance(Base):
    """H data provenance - one row per sourced record."""

    __tablename__ = "data_provenances"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_type: Mapped[str] = mapped_column(String(32), nullable=False)  # metric/diagnosis/medication/...
    record_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # manual/report/chat_extract
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_file_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CheckupReport(Base):
    """Persisted AI checkup recommendation reports."""

    __tablename__ = "checkup_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    budget_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    completeness_score: Mapped[int] = mapped_column(nullable=False)
    completeness_level: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_fields: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReportRecord(Base):
    """Report file entity with state machine: uploaded→extracting→pending→archived/rejected/cancelled."""

    __tablename__ = "report_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(256), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # image/jpeg, image/png, image/webp, application/pdf
    file_size: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="report_page", nullable=False)  # report_page / metric_input / chat
    status: Mapped[str] = mapped_column(String(16), default="uploaded", nullable=False)
    # uploaded → extracting → pending(待确认) → archived(已入档) / rejected / cancelled

    # AI extraction result (JSON)
    extraction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # human-confirmed extraction (JSON, after user edit)
    confirmed_extraction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # report metadata from AI
    report_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    report_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    patient_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # confirmation stats
    saved_metrics: Mapped[int] = mapped_column(default=0, nullable=False)
    saved_diagnoses: Mapped[int] = mapped_column(default=0, nullable=False)
    saved_medications: Mapped[int] = mapped_column(default=0, nullable=False)
    saved_lab_tests: Mapped[int] = mapped_column(default=0, nullable=False)
    saved_exam_findings: Mapped[int] = mapped_column(default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReportChunk(Base):
    """Vectorized report text chunk for RAG retrieval.

    One row per archived report. Stores the text representation used for
    semantic search plus its embedding vector (pgvector).
    """

    __tablename__ = "report_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    member_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("family_members.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_records.id", ondelete="CASCADE"), nullable=False
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    # pgvector column — dimension set at migration time (1024 is common for many embedding models)
    embedding = mapped_column(Vector(1024), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
