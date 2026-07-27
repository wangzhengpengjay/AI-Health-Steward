"""Model exports — ensure all models are imported for Alembic auto-detection."""
from app.models.family import FamilyMember
from app.models.health import (
    Allergy,
    CheckupReport,
    DataProvenance,
    Diagnosis,
    FamilyHistory,
    Lifestyle,
    Medication,
    MetricRecord,
    ReportRecord,
)
from app.models.feishu import FeishuChannel

__all__ = [
    "FamilyMember",
    "MetricRecord",
    "Diagnosis",
    "Medication",
    "Allergy",
    "Lifestyle",
    "FamilyHistory",
    "DataProvenance",
    "CheckupReport",
    "ReportRecord",
    "FeishuChannel",
]
