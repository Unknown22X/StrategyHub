"""Add structured failure diagnostics to portfolio backtests.

Revision ID: 0036_backtest_diagnostics
Revises: 0035_strategy_instance_lifecycle
"""

from alembic import op
import sqlalchemy as sa


revision = "0036_backtest_diagnostics"
down_revision = "0035_strategy_instance_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("backtest_portfolio_run") as batch:
        batch.add_column(sa.Column("failure_code", sa.String(length=80)))
        batch.add_column(sa.Column("failure_stage", sa.String(length=80)))


def downgrade() -> None:
    with op.batch_alter_table("backtest_portfolio_run") as batch:
        batch.drop_column("failure_stage")
        batch.drop_column("failure_code")
