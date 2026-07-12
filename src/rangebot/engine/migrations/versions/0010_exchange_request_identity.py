"""Persist exchange intents before adapter submission."""

from alembic import op
import sqlalchemy as sa


revision = "0010_exchange_request_identity"
down_revision = "0009_exchange_mode_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_request",
        sa.Column("client_request_id", sa.String(length=64), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("exchange_request")
