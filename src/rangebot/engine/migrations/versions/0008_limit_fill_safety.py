"""Persist the reserve needed to validate a Paper Limit fill."""

from alembic import op
import sqlalchemy as sa


revision = "0008_limit_fill_safety"
down_revision = "0007_paper_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_pending_entry",
        sa.Column(
            "safety_reserve",
            sa.Numeric(precision=24, scale=8),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("paper_pending_entry", "safety_reserve")
