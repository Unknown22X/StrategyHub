"""Persist the Paper direction setting per watched contract."""

from alembic import op
import sqlalchemy as sa

revision = "0004_paper_watchlist_direction"
down_revision = "0003_paper_watchlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_watchlist",
        sa.Column("direction", sa.String(16), nullable=False, server_default="both"),
    )


def downgrade() -> None:
    op.drop_column("paper_watchlist", "direction")
