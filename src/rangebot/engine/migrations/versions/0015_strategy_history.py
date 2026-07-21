"""Add strategy configuration, run, decision, and trade-origin history."""

from alembic import op
import sqlalchemy as sa


revision = "0015_strategy_history"
down_revision = "0014_strategy_instances"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_configuration_version",
        sa.Column("version_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("version_id"),
        sa.UniqueConstraint(
            "instance_id", "revision", name="uq_strategy_configuration_revision"
        ),
    )
    op.create_index(
        "ix_strategy_configuration_instance",
        "strategy_configuration_version",
        ["instance_id"],
        unique=False,
    )
    op.create_table(
        "strategy_run",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(
        "ix_strategy_run_instance",
        "strategy_run",
        ["instance_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_run_status",
        "strategy_run",
        ["status"],
        unique=False,
    )
    op.create_table(
        "strategy_decision",
        sa.Column("decision_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal", sa.String(length=100), nullable=False),
        sa.Column("eligible", sa.Boolean(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False),
        sa.Column("analysis_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index(
        "ix_strategy_decision_instance",
        "strategy_decision",
        ["instance_id", "occurred_at"],
        unique=False,
    )
    op.create_table(
        "trade_ownership",
        sa.Column("ownership_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("identity_kind", sa.String(length=16), nullable=False),
        sa.Column("external_identity", sa.String(length=200), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("instance_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ownership_id"),
        sa.UniqueConstraint(
            "identity_kind", "external_identity", name="uq_trade_ownership_identity"
        ),
    )
    op.create_index(
        "ix_trade_ownership_instance",
        "trade_ownership",
        ["instance_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trade_ownership_instance", table_name="trade_ownership")
    op.drop_table("trade_ownership")
    op.drop_index("ix_strategy_decision_instance", table_name="strategy_decision")
    op.drop_table("strategy_decision")
    op.drop_index("ix_strategy_run_status", table_name="strategy_run")
    op.drop_index("ix_strategy_run_instance", table_name="strategy_run")
    op.drop_table("strategy_run")
    op.drop_index(
        "ix_strategy_configuration_instance",
        table_name="strategy_configuration_version",
    )
    op.drop_table("strategy_configuration_version")
