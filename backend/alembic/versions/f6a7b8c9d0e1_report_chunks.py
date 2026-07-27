"""Add report_chunks table with pgvector for RAG.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension exists
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "report_chunks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("member_id", sa.BigInteger(), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("CREATE SEQUENCE IF NOT EXISTS report_chunks_id_seq")
    op.execute("ALTER TABLE report_chunks ALTER COLUMN id SET DEFAULT nextval('report_chunks_id_seq')")

    op.create_foreign_key(
        "fk_report_chunks_member_id", "report_chunks", "family_members",
        ["member_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_report_chunks_report_id", "report_chunks", "report_records",
        ["report_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_report_chunks_member_id", "report_chunks", ["member_id"])


def downgrade() -> None:
    op.drop_index("ix_report_chunks_member_id", table_name="report_chunks")
    op.drop_table("report_chunks")
