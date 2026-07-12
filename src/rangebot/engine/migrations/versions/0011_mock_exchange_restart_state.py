"""Persist restart-critical local adapter state for mock lifecycle verification."""

from alembic import op
import sqlalchemy as sa


revision = "0011_mock_exchange_restart_state"
down_revision = "0010_exchange_request_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_mode_state",
        sa.Column("adapter_state_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("exchange_mode_state", "adapter_state_json")
