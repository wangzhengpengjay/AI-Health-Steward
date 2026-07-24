"""add checkup recommendation fields to family_members

Revision ID: a1b2c3d4e5f6
Revises: e041be0735ed
Create Date: 2026-07-24 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e041be0735ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('family_members', sa.Column('region', sa.String(length=64), nullable=True))
    op.add_column('family_members', sa.Column('occupation', sa.String(length=64), nullable=True))
    op.add_column('family_members', sa.Column('is_pregnant', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('is_preparing_pregnancy', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('has_sexual_history', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('contrast_allergy', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('has_pacemaker', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('has_metal_implant', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('egfr', sa.Float(), nullable=True))
    op.add_column('family_members', sa.Column('on_anticoagulant', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('claustrophobia', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('is_breastfeeding', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('has_coagulopathy', sa.String(length=8), server_default='unknown', nullable=False))
    op.add_column('family_members', sa.Column('has_heart_failure', sa.String(length=8), server_default='unknown', nullable=False))


def downgrade() -> None:
    op.drop_column('family_members', 'has_heart_failure')
    op.drop_column('family_members', 'has_coagulopathy')
    op.drop_column('family_members', 'is_breastfeeding')
    op.drop_column('family_members', 'claustrophobia')
    op.drop_column('family_members', 'on_anticoagulant')
    op.drop_column('family_members', 'egfr')
    op.drop_column('family_members', 'has_metal_implant')
    op.drop_column('family_members', 'has_pacemaker')
    op.drop_column('family_members', 'contrast_allergy')
    op.drop_column('family_members', 'has_sexual_history')
    op.drop_column('family_members', 'is_preparing_pregnancy')
    op.drop_column('family_members', 'is_pregnant')
    op.drop_column('family_members', 'occupation')
    op.drop_column('family_members', 'region')
