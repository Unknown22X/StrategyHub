"""Persist Paper operational controls, risk state, profiles, and evidence."""

from alembic import op
import sqlalchemy as sa


revision = "0007_paper_operations"
down_revision = "0006_paper_protection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_pending_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column(
            "allocated_margin", sa.Numeric(precision=24, scale=8), nullable=False
        ),
        sa.Column("limit_price", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("leverage", sa.Integer(), nullable=False),
        sa.Column("taker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("maker_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("entry_fee_rate", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_zone", sa.String(length=200)),
        sa.Column("signal_symbol", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_risk_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column(
            "baseline_balance", sa.Numeric(precision=24, scale=8), nullable=False
        ),
        sa.Column(
            "realized_net_loss", sa.Numeric(precision=24, scale=8), nullable=False
        ),
        sa.Column("losing_trades", sa.Integer(), nullable=False),
        sa.Column("automatic_fills", sa.Integer(), nullable=False),
        sa.Column(
            "daily_loss_limit", sa.Numeric(precision=24, scale=8), nullable=False
        ),
        sa.Column("losing_trade_limit", sa.Integer(), nullable=False),
        sa.Column("automatic_fill_limit", sa.Integer(), nullable=False),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_emergency_stop",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("automatic_trading_requires_restart", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_used_signal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("trigger_zone", sa.String(length=200), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reset_seen", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("safety_fingerprint", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_verification_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_build", sa.String(length=200), nullable=False),
        sa.Column("safety_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "paper_active_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("paper_active_profile")
    op.drop_table("paper_verification_record")
    op.drop_table("paper_profile")
    op.drop_table("paper_used_signal")
    op.drop_table("paper_emergency_stop")
    op.drop_table("paper_risk_state")
    op.drop_table("paper_pending_entry")
