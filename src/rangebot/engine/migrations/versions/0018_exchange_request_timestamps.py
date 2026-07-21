"""Add durable timestamps to exchange operation identities.

Revision ID: 0018_exchange_request_timestamps
Revises: 0017_discovery_backtesting
"""

from alembic import op
import sqlalchemy as sa


revision = "0018_exchange_request_timestamps"
down_revision = "0017_discovery_backtesting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "exchange_request",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.add_column(
        "exchange_request",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "ix_exchange_request_updated",
        "exchange_request",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_exchange_request_updated", table_name="exchange_request")
    op.drop_column("exchange_request", "updated_at")
    op.drop_column("exchange_request", "created_at")
