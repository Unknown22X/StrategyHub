"""Add immutable Paper and Gate executed-trade history."""

from alembic import op
import sqlalchemy as sa


revision = "0025_trade_fill_ledger"
down_revision = "0024_strategy_execution_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trade_fill",
        sa.Column("fill_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("external_trade_id", sa.String(length=200), nullable=False),
        sa.Column("order_id", sa.String(length=200), nullable=True),
        sa.Column("contract", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("position_effect", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("price", sa.Numeric(30, 12), nullable=False),
        sa.Column("fee", sa.Numeric(30, 12), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("close_quantity", sa.Numeric(30, 12), nullable=False),
        sa.Column("trade_value", sa.Numeric(30, 12), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(30, 12), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=True),
        sa.Column("instance_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("strategy_name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("fill_id"),
        sa.UniqueConstraint(
            "environment",
            "external_trade_id",
            name="uq_trade_fill_environment_external_id",
        ),
    )
    op.create_index("ix_trade_fill_occurred_at", "trade_fill", ["occurred_at"])
    op.create_index(
        "ix_trade_fill_contract", "trade_fill", ["contract", "occurred_at"]
    )
    op.create_index(
        "ix_trade_fill_instance", "trade_fill", ["instance_id", "occurred_at"]
    )
    op.create_index("ix_trade_fill_run", "trade_fill", ["run_id", "occurred_at"])
    op.create_index(
        "ix_trade_fill_order", "trade_fill", ["environment", "order_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_trade_fill_order", table_name="trade_fill")
    op.drop_index("ix_trade_fill_run", table_name="trade_fill")
    op.drop_index("ix_trade_fill_instance", table_name="trade_fill")
    op.drop_index("ix_trade_fill_contract", table_name="trade_fill")
    op.drop_index("ix_trade_fill_occurred_at", table_name="trade_fill")
    op.drop_table("trade_fill")
