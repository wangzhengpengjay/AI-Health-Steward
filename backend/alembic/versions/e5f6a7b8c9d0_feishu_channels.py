"""Add feishu_channels table.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-27
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feishu_channels",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("app_id", sa.String(128), nullable=False),
        sa.Column("app_secret", sa.String(256), nullable=False),
        sa.Column("member_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # PostgreSQL needs explicit sequence for BigInteger autoincrement
    op.execute("CREATE SEQUENCE IF NOT EXISTS feishu_channels_id_seq")
    op.execute("ALTER TABLE feishu_channels ALTER COLUMN id SET DEFAULT nextval('feishu_channels_id_seq')")

    op.create_foreign_key(
        "fk_feishu_channels_member_id",
        "feishu_channels",
        "family_members",
        ["member_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("feishu_channels")
    op.execute("DROP SEQUENCE IF EXISTS feishu_channels_id_seq")
