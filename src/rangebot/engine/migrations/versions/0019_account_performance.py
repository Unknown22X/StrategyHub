"""Add persisted Gate account equity history.

Revision ID: 0019_account_performance
Revises: 0018_exchange_request_timestamps
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_account_performance"
down_revision = "0018_exchange_request_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_equity_point",
        sa.Column("point_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_equity", sa.Numeric(30, 12), nullable=False),
        sa.Column("available_balance", sa.Numeric(30, 12), nullable=False),
        sa.Column("used_margin", sa.Numeric(30, 12), nullable=False),
        sa.Column("margin_usage_percentage", sa.Numeric(30, 12), nullable=False),
        sa.Column("realized_pnl_total", sa.Numeric(30, 12), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(30, 12), nullable=False),
        sa.Column("fees_total", sa.Numeric(30, 12), nullable=False),
        sa.Column("funding_total", sa.Numeric(30, 12), nullable=False),
        sa.Column("net_pnl_total", sa.Numeric(30, 12), nullable=False),
        sa.Column("open_exposure", sa.Numeric(30, 12), nullable=False),
        sa.PrimaryKeyConstraint("point_id"),
        sa.UniqueConstraint("mode", "occurred_at", name="uq_account_equity_mode_time"),
    )
    op.create_index(
        "ix_account_equity_mode_time",
        "account_equity_point",
        ["mode", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_account_equity_mode_time", table_name="account_equity_point")
    op.drop_table("account_equity_point")
