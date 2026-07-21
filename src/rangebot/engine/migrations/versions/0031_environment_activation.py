"""authoritative environment activation

Revision ID: 0031_environment_activation
Revises: 0030_production_backtesting
"""

from alembic import op
import sqlalchemy as sa


revision = "0031_environment_activation"
down_revision = "0030_production_backtesting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environment_activation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "environment IN ('paper', 'testnet', 'live')",
            name="ck_environment_activation_environment",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("environment_activation")
