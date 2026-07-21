"""explicit risk-limit enablement and immutable daily baselines

Revision ID: 0032_account_risk_controls
Revises: 0031_environment_activation
"""

from alembic import op
import sqlalchemy as sa


revision = "0032_account_risk_controls"
down_revision = "0031_environment_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("account_risk_policy") as batch:
        batch.add_column(
            sa.Column(
                "daily_loss_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "losing_trade_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "automatic_trade_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )

    op.create_table(
        "account_daily_risk_baseline",
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("baseline_equity", sa.Numeric(30, 12), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "environment IN ('testnet', 'live')",
            name="ck_account_daily_risk_baseline_environment",
        ),
        sa.PrimaryKeyConstraint("environment", "day"),
    )


def downgrade() -> None:
    op.drop_table("account_daily_risk_baseline")
    with op.batch_alter_table("account_risk_policy") as batch:
        batch.drop_column("automatic_trade_enabled")
        batch.drop_column("losing_trade_enabled")
        batch.drop_column("daily_loss_enabled")
