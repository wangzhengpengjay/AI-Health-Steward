"""Widen lifestyles.category so chat-extracted medication mentions persist.

The chat tool writes ``category="medication_mention"`` (18 chars) into
``lifestyles.category`` which was ``String(16)``. On PostgreSQL every such write
failed with "value too long for type character varying(16)" and the surrounding
rollback discarded the user's medication information.

Revision ID: m4a5b6c7d8e9
Revises: l3f4a5b6c7d8
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa

revision = "m4a5b6c7d8e9"
down_revision = "l3f4a5b6c7d8"
branch_labels = None
depends_on = None

# Must comfortably fit every category literal used by the application
# (smoking/drinking/exercise/diet/symptom/medication_mention...).
_NEW_LENGTH = 32
_OLD_LENGTH = 16


def upgrade() -> None:
    op.alter_column(
        "lifestyles",
        "category",
        existing_type=sa.String(length=_OLD_LENGTH),
        type_=sa.String(length=_NEW_LENGTH),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Rows longer than the old width would not fit; shorten them first so the
    # downgrade cannot fail on data written after this migration.
    op.execute(
        "UPDATE lifestyles SET category = left(category, 16) WHERE length(category) > 16"
    )
    op.alter_column(
        "lifestyles",
        "category",
        existing_type=sa.String(length=_NEW_LENGTH),
        type_=sa.String(length=_OLD_LENGTH),
        existing_nullable=False,
    )
