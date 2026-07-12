"""Persist Paper TP and SL protection for the single simulated position."""

from alembic import op
import sqlalchemy as sa


revision = "0006_paper_protection"
down_revision = "0005_paper_market_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_position",
        sa.Column("leverage", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "paper_position",
        sa.Column(
            "maker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False,
            server_default="0.001",
        ),
    )
    op.add_column(
        "paper_position",
        sa.Column(
            "taker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False,
            server_default="0.001",
        ),
    )
    op.create_table(
        "paper_protection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("take_profit_price", sa.Numeric(precision=24, scale=8)),
        sa.Column("stop_loss_price", sa.Numeric(precision=24, scale=8)),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("warning", sa.String(length=500)),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_fee_schedule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("maker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("taker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("paper_fee_schedule")
    op.drop_table("paper_protection")
    op.drop_column("paper_position", "taker_fee_rate")
    op.drop_column("paper_position", "leverage")
    op.drop_column("paper_position", "maker_fee_rate")
