"""Add report_records table with state machine.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("member_id", sa.BigInteger(), nullable=False),
        sa.Column("file_name", sa.String(256), nullable=False),
        sa.Column("file_type", sa.String(32), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(32), server_default="report_page", nullable=False),
        sa.Column("status", sa.String(16), server_default="uploaded", nullable=False),
        sa.Column("extraction", sa.Text(), nullable=True),
        sa.Column("confirmed_extraction", sa.Text(), nullable=True),
        sa.Column("report_type", sa.String(128), nullable=True),
        sa.Column("report_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("patient_name", sa.String(64), nullable=True),
        sa.Column("saved_metrics", sa.Integer(), server_default="0", nullable=False),
        sa.Column("saved_diagnoses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("saved_medications", sa.Integer(), server_default="0", nullable=False),
        sa.Column("saved_lab_tests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("saved_exam_findings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_records_member_id", "report_records", ["member_id"])
    op.create_index("ix_report_records_status", "report_records", ["status"])


def downgrade() -> None:
    op.drop_index("ix_report_records_status", table_name="report_records")
    op.drop_index("ix_report_records_member_id", table_name="report_records")
    op.drop_table("report_records")
