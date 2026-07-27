"""add surgeries and vaccinations tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'surgeries',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('member_id', sa.BigInteger(), sa.ForeignKey('family_members.id', ondelete='CASCADE'), nullable=False),
        sa.Column('surgery_name', sa.String(128), nullable=False),
        sa.Column('surgery_date', sa.Date(), nullable=True),
        sa.Column('hospital', sa.String(128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        'vaccinations',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('member_id', sa.BigInteger(), sa.ForeignKey('family_members.id', ondelete='CASCADE'), nullable=False),
        sa.Column('vaccine_name', sa.String(128), nullable=False),
        sa.Column('dose_no', sa.String(16), nullable=True),
        sa.Column('vaccinated_date', sa.Date(), nullable=True),
        sa.Column('facility', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('vaccinations')
    op.drop_table('surgeries')
