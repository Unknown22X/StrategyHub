"""production historical portfolio backtesting

Revision ID: 0030_production_backtesting
Revises: 0029_strategy_workflow
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_production_backtesting"
down_revision = "0029_strategy_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_portfolio_run",
        sa.Column("backtest_id", sa.String(length=36), nullable=False),
        sa.Column("setup_id", sa.String(length=36), nullable=True),
        sa.Column("setup_revision", sa.Integer(), nullable=True),
        sa.Column("strategy_type_id", sa.String(length=64), nullable=False),
        sa.Column("strategy_version", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_percentage", sa.Integer(), nullable=False),
        sa.Column("stage_message_ar", sa.Text(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("input_data_hash", sa.String(length=64), nullable=True),
        sa.Column("request_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("post_test_observations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("backtest_id"),
    )
    op.create_index(
        "ix_backtest_portfolio_created", "backtest_portfolio_run", ["created_at"]
    )
    op.create_index(
        "ix_backtest_portfolio_setup", "backtest_portfolio_run",
        ["setup_id", "setup_revision"]
    )
    op.create_index(
        "ix_backtest_portfolio_status", "backtest_portfolio_run", ["status"]
    )
    for table, payload_column in (
        ("backtest_candidate", "candidate_json"),
        ("backtest_decision", "decision_json"),
        ("backtest_order", "order_json"),
        ("backtest_fill", "fill_json"),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("backtest_id", sa.String(length=36), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(length=64), nullable=False),
            sa.Column(payload_column, sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["backtest_id"], ["backtest_portfolio_run.backtest_id"],
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint("backtest_id", "sequence", name=f"uq_{table}_sequence"),
        )
        op.create_index(f"ix_{table}_run", table, ["backtest_id", "sequence"])


def downgrade() -> None:
    for table in ("backtest_fill", "backtest_order", "backtest_decision", "backtest_candidate"):
        op.drop_index(f"ix_{table}_run", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_backtest_portfolio_status", table_name="backtest_portfolio_run")
    op.drop_index("ix_backtest_portfolio_setup", table_name="backtest_portfolio_run")
    op.drop_index("ix_backtest_portfolio_created", table_name="backtest_portfolio_run")
    op.drop_table("backtest_portfolio_run")
