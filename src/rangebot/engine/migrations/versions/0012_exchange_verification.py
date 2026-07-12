"""Persist advisory exchange verification evidence separately by mode."""

from alembic import op
import sqlalchemy as sa


revision = "0012_exchange_verification"
down_revision = "0011_mock_exchange_restart_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_mode_state",
        sa.Column("verification_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exchange_mode_state", "verification_json")
