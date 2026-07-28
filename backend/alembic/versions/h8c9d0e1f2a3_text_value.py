"""Add text_value column to metric_records for non-numeric lab results.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "h8c9d0e1f2a3"
down_revision = "g7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("metric_records", sa.Column("text_value", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("metric_records", "text_value")
