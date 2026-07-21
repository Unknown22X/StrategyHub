"""Add a persisted account-wide risk policy for Gate Testnet and Live."""

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa


revision = "0028_account_risk_policy"
down_revision = "0027_trailing_protection_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = op.create_table(
        "account_risk_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("daily_loss_limit", sa.Numeric(30, 12), nullable=False),
        sa.Column("losing_trade_limit", sa.Integer(), nullable=False),
        sa.Column("automatic_trade_limit", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": 1,
                "daily_loss_limit": 100,
                "losing_trade_limit": 3,
                "automatic_trade_limit": 5,
                "revision": 1,
                "updated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("account_risk_policy")
