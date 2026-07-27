"""add checkup_reports table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-24 21:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'checkup_reports',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('member_id', sa.BigInteger(), sa.ForeignKey('family_members.id', ondelete='CASCADE'), nullable=False),
        sa.Column('budget_tier', sa.String(16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('completeness_score', sa.Integer(), nullable=False),
        sa.Column('completeness_level', sa.String(32), nullable=False),
        sa.Column('missing_fields', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_checkup_reports_member_id', 'checkup_reports', ['member_id'])


def downgrade() -> None:
    op.drop_index('ix_checkup_reports_member_id', table_name='checkup_reports')
    op.drop_table('checkup_reports')
