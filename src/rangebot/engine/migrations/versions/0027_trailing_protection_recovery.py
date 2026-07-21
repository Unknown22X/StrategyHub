"""Persist desired and reconciled trailing protection with trade ownership."""

from alembic import op
import sqlalchemy as sa


revision = "0027_trailing_protection_recovery"
down_revision = "0026_paper_trailing_protection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trade_ownership") as batch:
        batch.add_column(sa.Column("trailing_stop_price", sa.Numeric(30, 12)))
        batch.add_column(sa.Column("trailing_stop_distance", sa.Numeric(30, 12)))
        batch.add_column(sa.Column("trailing_state", sa.String(length=16)))
        batch.add_column(sa.Column("trailing_order_id", sa.String(length=200)))
        batch.add_column(sa.Column("trailing_last_error", sa.String(length=500)))
        batch.add_column(sa.Column("trailing_updated_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    with op.batch_alter_table("trade_ownership") as batch:
        batch.drop_column("trailing_updated_at")
        batch.drop_column("trailing_last_error")
        batch.drop_column("trailing_order_id")
        batch.drop_column("trailing_state")
        batch.drop_column("trailing_stop_distance")
        batch.drop_column("trailing_stop_price")
