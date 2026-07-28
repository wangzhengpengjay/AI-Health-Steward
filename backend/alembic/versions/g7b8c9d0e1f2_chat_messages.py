"""Add chat_messages table for conversation history.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-28
"""
from alembic import op
import sqlalchemy as sa

revision = "g7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("member_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), server_default="webui", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS chat_messages_id_seq")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN id SET DEFAULT nextval('chat_messages_id_seq')")
    op.create_index("ix_chat_messages_member_id", "chat_messages", ["member_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_member_id", table_name="chat_messages")
    op.drop_table("chat_messages")
