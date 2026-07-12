"""Persist exchange-backed safety locks and sanitized reconciliation state."""

from alembic import op
import sqlalchemy as sa


revision = "0009_exchange_mode_safety"
down_revision = "0008_limit_fill_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_mode_state",
        sa.Column("mode", sa.String(length=16), primary_key=True),
        sa.Column(
            "live_locked", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "emergency_stop", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("snapshot_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("exchange_mode_state")
