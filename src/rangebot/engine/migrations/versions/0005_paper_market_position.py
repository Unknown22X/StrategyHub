"""Persist the single simulated Paper Market position."""

from alembic import op
import sqlalchemy as sa


revision = "0005_paper_market_position"
down_revision = "0004_paper_watchlist_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_position",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("entry_fee", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column(
            "allocated_margin", sa.Numeric(precision=24, scale=8), nullable=False
        ),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("paper_position")
