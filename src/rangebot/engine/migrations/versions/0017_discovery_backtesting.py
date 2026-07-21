"""Add strategy discovery and deterministic backtest audit records.

Revision ID: 0017_discovery_backtesting
Revises: 0016_remove_live_lock
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_discovery_backtesting"
down_revision = "0016_remove_live_lock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_scan",
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_type_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scan_id"),
    )
    op.create_index(
        "ix_discovery_scan_created",
        "discovery_scan",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_scan_strategy",
        "discovery_scan",
        ["strategy_type_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "discovery_scan_candidate",
        sa.Column("candidate_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("candidate_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("candidate_id"),
        sa.UniqueConstraint("scan_id", "rank", name="uq_discovery_candidate_rank"),
        sa.UniqueConstraint("scan_id", "symbol", name="uq_discovery_candidate_symbol"),
    )
    op.create_index(
        "ix_discovery_candidate_scan",
        "discovery_scan_candidate",
        ["scan_id", "rank"],
        unique=False,
    )

    op.create_table(
        "backtest_run",
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("scan_id", sa.String(length=36), nullable=True),
        sa.Column("strategy_type_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("backtest_id"),
    )
    op.create_index(
        "ix_backtest_run_scan",
        "backtest_run",
        ["scan_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_run_strategy_symbol",
        "backtest_run",
        ["strategy_type_id", "symbol", "created_at"],
        unique=False,
    )

    op.create_table(
        "backtest_trade",
        sa.Column("trade_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("trade_number", sa.Integer(), nullable=False),
        sa.Column("trade_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("trade_id"),
        sa.UniqueConstraint(
            "backtest_id", "trade_number", name="uq_backtest_trade_number"
        ),
    )
    op.create_index(
        "ix_backtest_trade_run",
        "backtest_trade",
        ["backtest_id", "trade_number"],
        unique=False,
    )

    op.create_table(
        "backtest_equity_point",
        sa.Column("point_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("point_index", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.String(length=100), nullable=False),
        sa.Column("drawdown_percentage", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("point_id"),
        sa.UniqueConstraint(
            "backtest_id", "point_index", name="uq_backtest_equity_index"
        ),
    )
    op.create_index(
        "ix_backtest_equity_run",
        "backtest_equity_point",
        ["backtest_id", "point_index"],
        unique=False,
    )

    op.create_table(
        "backtest_strategy_application",
        sa.Column("application_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("application_id"),
        sa.UniqueConstraint("backtest_id", name="uq_backtest_strategy_application"),
        sa.UniqueConstraint("instance_id", name="uq_strategy_backtest_application"),
    )
    op.create_index(
        "ix_backtest_application_instance",
        "backtest_strategy_application",
        ["instance_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backtest_application_instance",
        table_name="backtest_strategy_application",
    )
    op.drop_table("backtest_strategy_application")
    op.drop_index("ix_backtest_equity_run", table_name="backtest_equity_point")
    op.drop_table("backtest_equity_point")
    op.drop_index("ix_backtest_trade_run", table_name="backtest_trade")
    op.drop_table("backtest_trade")
    op.drop_index("ix_backtest_run_strategy_symbol", table_name="backtest_run")
    op.drop_index("ix_backtest_run_scan", table_name="backtest_run")
    op.drop_table("backtest_run")
    op.drop_index("ix_discovery_candidate_scan", table_name="discovery_scan_candidate")
    op.drop_table("discovery_scan_candidate")
    op.drop_index("ix_discovery_scan_strategy", table_name="discovery_scan")
    op.drop_index("ix_discovery_scan_created", table_name="discovery_scan")
    op.drop_table("discovery_scan")
