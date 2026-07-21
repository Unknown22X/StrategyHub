"""Add contract context to durable order and position ownership.

Revision ID: 0020_trade_ownership_context
Revises: 0019_account_performance
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_trade_ownership_context"
down_revision = "0019_account_performance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_ownership",
        sa.Column("environment", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "trade_ownership",
        sa.Column("symbol", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "trade_ownership",
        sa.Column("direction", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_trade_ownership_context",
        "trade_ownership",
        ["identity_kind", "environment", "symbol", "direction", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_ownership_context", table_name="trade_ownership")
    op.drop_column("trade_ownership", "direction")
    op.drop_column("trade_ownership", "symbol")
    op.drop_column("trade_ownership", "environment")
