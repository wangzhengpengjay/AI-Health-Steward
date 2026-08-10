"""Add health summaries table

Revision ID: 70b29195e3a6
Revises: dd051f241487
Create Date: 2026-08-10 10:08:58.505876

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '70b29195e3a6'
down_revision: Union[str, None] = 'dd051f241487'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('health_summaries',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('member_id', sa.BigInteger(), nullable=False),
    sa.Column('summary_type', sa.String(length=16), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('stats_json', sa.Text(), nullable=True),
    sa.Column('abnormal_events', sa.Text(), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['member_id'], ['family_members.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_health_summaries_member_id', 'health_summaries', ['member_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_health_summaries_member_id', table_name='health_summaries')
    op.drop_table('health_summaries')
