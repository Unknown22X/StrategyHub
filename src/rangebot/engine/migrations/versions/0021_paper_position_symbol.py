"""Persist the contract symbol for Paper positions.

Revision ID: 0021_paper_position_symbol
Revises: 0020_trade_ownership_context
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_paper_position_symbol"
down_revision = "0020_trade_ownership_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_position",
        sa.Column("symbol", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_position", "symbol")
