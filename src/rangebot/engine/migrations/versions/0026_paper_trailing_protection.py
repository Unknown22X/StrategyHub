"""Add durable Paper trailing-stop protection state."""

from alembic import op
import sqlalchemy as sa


revision = "0026_paper_trailing_protection"
down_revision = "0025_trade_fill_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("paper_protection") as batch:
        batch.add_column(sa.Column("trailing_stop_price", sa.Numeric(24, 8)))
        batch.add_column(sa.Column("trailing_distance", sa.Numeric(24, 8)))
        batch.add_column(sa.Column("trailing_extremum_price", sa.Numeric(24, 8)))


def downgrade() -> None:
    with op.batch_alter_table("paper_protection") as batch:
        batch.drop_column("trailing_extremum_price")
        batch.drop_column("trailing_distance")
        batch.drop_column("trailing_stop_price")
