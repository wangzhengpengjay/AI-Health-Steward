"""Add a unique index on health_summaries (member, period, range).

The scheduler's idempotency guard is a SELECT-then-INSERT with no database
constraint, and ``scheduler_loop`` runs inside every process's lifespan. With
more than one worker/replica, two processes could both see "not generated yet"
and each create a summary for the same period (duplicate rows, and duplicate
LLM spend when enrichment is enabled).

Revision ID: n5b6c7d8e9f0
Revises: m4a5b6c7d8e9
Create Date: 2026-09-13
"""
from alembic import op

revision = "n5b6c7d8e9f0"
down_revision = "m4a5b6c7d8e9"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_health_summary_member_period"


def upgrade() -> None:
    # Drop duplicates left behind by the previous non-atomic check-then-insert,
    # keeping the earliest row of each group.
    op.execute(
        """
        DELETE FROM health_summaries a
        USING health_summaries b
        WHERE a.member_id = b.member_id
          AND a.period = b.period
          AND a.period_start = b.period_start
          AND a.period_end = b.period_end
          AND a.id > b.id
        """
    )
    op.create_index(
        _INDEX_NAME,
        "health_summaries",
        ["member_id", "period", "period_start", "period_end"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="health_summaries")
