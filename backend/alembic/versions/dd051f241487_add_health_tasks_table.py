"""Add health tasks table

Revision ID: dd051f241487
Revises: i9d0e1f2a3b4
Create Date: 2026-08-10 09:51:14.442368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dd051f241487'
down_revision: Union[str, None] = 'i9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('health_tasks',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('member_id', sa.BigInteger(), nullable=False),
    sa.Column('task_type', sa.String(length=24), nullable=False),
    sa.Column('title', sa.String(length=128), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('priority', sa.String(length=8), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('source_ref', sa.String(length=64), nullable=True),
    sa.Column('auto_generated', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['member_id'], ['family_members.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_health_tasks_member_id', 'health_tasks', ['member_id'], unique=False)
    op.create_index('ix_health_tasks_status', 'health_tasks', ['status'], unique=False)
    op.create_index('ix_health_tasks_due_date', 'health_tasks', ['due_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_health_tasks_due_date', table_name='health_tasks')
    op.drop_index('ix_health_tasks_status', table_name='health_tasks')
    op.drop_index('ix_health_tasks_member_id', table_name='health_tasks')
    op.drop_table('health_tasks')