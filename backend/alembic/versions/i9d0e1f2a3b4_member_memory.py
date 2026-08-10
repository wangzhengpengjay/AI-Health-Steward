"""Add member memory summary columns for long-term conversation memory.

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "i9d0e1f2a3b4"
down_revision = "h8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("family_members", sa.Column("memory_summary", sa.Text(), nullable=True))
    op.add_column(
        "family_members",
        sa.Column("memory_summary_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("family_members", "memory_summary_updated_at")
    op.drop_column("family_members", "memory_summary")