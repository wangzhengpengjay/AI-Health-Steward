"""Normalize chat-extracted glucose aliases to postmeal_glucose.

Revision ID: l3f4a5b6c7d8
Revises: k1f2a3b4c5d6
Create Date: 2026-08-13
"""
from alembic import op

revision = "l3f4a5b6c7d8"
down_revision = "k1f2a3b4c5d6"
branch_labels = None
depends_on = None

_ALIASES = (
    "postprandial_glucose",
    "postprandial_glucose_2h",
    "postprandial_2h_glucose",
)


def upgrade() -> None:
    for alias in _ALIASES:
        op.execute(
            "UPDATE metric_records SET metric_name = 'postmeal_glucose' "
            f"WHERE metric_name = '{alias}'"
        )


def downgrade() -> None:
    # 原别名无法从目标值还原，留空保证可降级。
    pass
