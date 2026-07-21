"""Remove the obsolete Live activation lock.

Revision ID: 0016_remove_live_lock
Revises: 0015_strategy_history
"""

from alembic import op
import sqlalchemy as sa


revision = "0016_remove_live_lock"
down_revision = "0015_strategy_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exchange_mode_state") as batch_op:
        batch_op.drop_column("live_locked")


def downgrade() -> None:
    with op.batch_alter_table("exchange_mode_state") as batch_op:
        batch_op.add_column(
            sa.Column(
                "live_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
