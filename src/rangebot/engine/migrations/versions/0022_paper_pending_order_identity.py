"""Persist RangeBot order identity for Paper pending entries.

Revision ID: 0022_paper_pending_order_identity
Revises: 0021_paper_position_symbol
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_paper_pending_order_identity"
down_revision = "0021_paper_position_symbol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_pending_entry",
        sa.Column("order_id", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("paper_pending_entry", "order_id")
