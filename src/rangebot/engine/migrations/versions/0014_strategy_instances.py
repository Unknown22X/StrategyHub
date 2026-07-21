"""Add persisted strategy instances and lifecycle state."""

from alembic import op
import sqlalchemy as sa


revision = "0014_strategy_instances"
down_revision = "0013_application_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_instance",
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("type_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timeframe_minutes", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("instance_id"),
    )
    op.create_index(
        "ix_strategy_instance_status",
        "strategy_instance",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_strategy_instance_type_id",
        "strategy_instance",
        ["type_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_instance_type_id", table_name="strategy_instance")
    op.drop_index("ix_strategy_instance_status", table_name="strategy_instance")
    op.drop_table("strategy_instance")
