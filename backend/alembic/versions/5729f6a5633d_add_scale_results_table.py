"""Add scale results table

Revision ID: 5729f6a5633d
Revises: 70b29195e3a6
Create Date: 2026-08-10 10:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5729f6a5633d'
down_revision: Union[str, None] = '70b29195e3a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('scale_results',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('member_id', sa.BigInteger(), nullable=False),
    sa.Column('scale_code', sa.String(length=32), nullable=False),
    sa.Column('answers', sa.Text(), nullable=False),
    sa.Column('total_score', sa.Float(), nullable=False),
    sa.Column('risk_level', sa.String(length=24), nullable=False),
    sa.Column('risk_label', sa.String(length=64), nullable=True),
    sa.Column('interpretation', sa.Text(), nullable=True),
    sa.Column('advice', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['family_members.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scale_results_member_id', 'scale_results', ['member_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_scale_results_member_id', table_name='scale_results')
    op.drop_table('scale_results')
