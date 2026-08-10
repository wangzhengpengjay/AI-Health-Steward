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
from app.models.tasks import HealthTask
from app.models.summaries import HealthSummary

__all__ = [
    "FamilyMember",
    "HealthTask",
    "HealthSummary",
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
