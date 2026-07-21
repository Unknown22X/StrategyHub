"""Persist cumulative Paper performance totals.

Revision ID: 0023_paper_performance_totals
Revises: 0022_paper_pending_order_identity
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_paper_performance_totals"
down_revision = "0022_paper_pending_order_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_account",
        sa.Column("realized_pnl_total", sa.Numeric(30, 12), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_account",
        sa.Column("fees_total", sa.Numeric(30, 12), nullable=False, server_default="0"),
    )
    op.add_column(
        "paper_account",
        sa.Column("funding_total", sa.Numeric(30, 12), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("paper_account", "funding_total")
    op.drop_column("paper_account", "fees_total")
    op.drop_column("paper_account", "realized_pnl_total")
