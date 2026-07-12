"""Create local Paper watchlist state.

Revision ID: 0003_paper_watchlist
Revises: 0002_paper_account
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_paper_watchlist"
down_revision = "0002_paper_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_watchlist",
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("symbol"),
    )
    op.create_table(
        "paper_automation_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("automatic_trading_enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("paper_automation_state")
    op.drop_table("paper_watchlist")
