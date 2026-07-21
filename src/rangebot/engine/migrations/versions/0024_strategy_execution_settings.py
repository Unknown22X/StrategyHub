"""Add engine-owned automatic execution sizing and version/run references.

Revision ID: 0024_strategy_execution_settings
Revises: 0023_paper_performance_totals
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_strategy_execution_settings"
down_revision = "0023_paper_performance_totals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategy_instance",
        sa.Column(
            "requested_margin",
            sa.Numeric(30, 12),
            nullable=False,
            server_default="20",
        ),
    )
    op.add_column(
        "strategy_instance",
        sa.Column(
            "requested_leverage",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "strategy_configuration_version",
        sa.Column(
            "requested_margin",
            sa.Numeric(30, 12),
            nullable=False,
            server_default="20",
        ),
    )
    op.add_column(
        "strategy_configuration_version",
        sa.Column(
            "requested_leverage",
            sa.Integer(),
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "strategy_run",
        sa.Column(
            "configuration_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("strategy_run", "configuration_revision")
    op.drop_column("strategy_configuration_version", "requested_leverage")
    op.drop_column("strategy_configuration_version", "requested_margin")
    op.drop_column("strategy_instance", "requested_leverage")
    op.drop_column("strategy_instance", "requested_margin")
