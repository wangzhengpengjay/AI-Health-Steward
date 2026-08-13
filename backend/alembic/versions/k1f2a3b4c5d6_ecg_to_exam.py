"""Move ECG quantitative metrics into exam:心电图 category.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-08-12
"""
from alembic import op

revision = "k1f2a3b4c5d6"
down_revision = "j0e1f2a3b4c5"
branch_labels = None
depends_on = None

_ECG_MAPPING = {
    "pr_interval": "P-R间期",
    "qrs_duration": "QRS时限",
    "qt_qtc": "QT/QTc",
    "sv1": "SV1",
    "rv5": "RV5",
    "rv5_plus_sv1": "RV5+SV1",
    "cardiac_axis": "心电轴",
}


def upgrade() -> None:
    for old_name, desc in _ECG_MAPPING.items():
        new_name = f"exam:心电图:{desc}"
        op.execute(
            f"UPDATE metric_records SET metric_name = '{new_name}' "
            f"WHERE metric_name = '{old_name}'"
        )


def downgrade() -> None:
    for old_name, desc in _ECG_MAPPING.items():
        new_name = f"exam:心电图:{desc}"
        op.execute(
            f"UPDATE metric_records SET metric_name = '{old_name}' "
            f"WHERE metric_name = '{new_name}'"
        )
