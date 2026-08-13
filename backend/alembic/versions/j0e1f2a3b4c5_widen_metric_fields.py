"""Widen metric_records string columns to TEXT.

Report extraction may produce long lab/exam names, text values, or context
(e.g. exam conclusion), which exceeded the previous varchar(64/128) limits.

Revision ID: j0e1f2a3b4c5
Revises: 5729f6a5633d
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = "j0e1f2a3b4c5"
down_revision = "5729f6a5633d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "metric_records",
        "metric_name",
        type_=sa.Text(),
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "metric_records",
        "text_value",
        type_=sa.Text(),
        existing_type=sa.String(length=128),
        existing_nullable=True,
    )
    op.alter_column(
        "metric_records",
        "context",
        type_=sa.Text(),
        existing_type=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "metric_records",
        "context",
        type_=sa.String(length=64),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "metric_records",
        "text_value",
        type_=sa.String(length=128),
        existing_type=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "metric_records",
        "metric_name",
        type_=sa.String(length=64),
        existing_type=sa.Text(),
        existing_nullable=False,
    )
