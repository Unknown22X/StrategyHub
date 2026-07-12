"""Create local Paper Account state and audit records.

Revision ID: 0002_paper_account
Revises: 0001_runtime_state
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_paper_account"
down_revision = "0001_runtime_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("starting_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("available_futures_balance", sa.Numeric(24, 8), nullable=False),
        sa.Column("position_quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("pending_entry", sa.Boolean(), nullable=False),
        sa.Column("protection_state", sa.String(length=32), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_state", sa.String(length=64), nullable=False),
        sa.Column("last_change_reason", sa.String(length=500), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_account_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("paper_account_audit")
    op.drop_table("paper_account")
