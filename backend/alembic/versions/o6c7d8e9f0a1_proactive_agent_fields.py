"""add proactive agent fields to chat_messages

Revision ID: o6c7d8e9f0a1
Revises: n5b6c7d8e9f0
Create Date: 2026-10-13 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "o6c7d8e9f0a1"
down_revision = "n5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column(
            "message_type",
            sa.String(16),
            server_default="normal",
            nullable=False,
        ),
    )
    op.add_column(
        "chat_messages",
        sa.Column("metadata_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "metadata_json")
    op.drop_column("chat_messages", "message_type")
