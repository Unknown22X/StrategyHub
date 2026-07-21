"""Add pin and archive lifecycle fields to Strategy Instances.

Revision ID: 0035_strategy_instance_lifecycle
Revises: 0034_strategy_run_configuration_snapshot
"""

from alembic import op
import sqlalchemy as sa


revision = "0035_strategy_instance_lifecycle"
down_revision = "0034_strategy_run_configuration_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("strategy_instance") as batch:
        batch.add_column(
            sa.Column(
                "is_pinned",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("archived_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("archive_reason", sa.String(length=500)))
        batch.create_index(
            "ix_strategy_instance_archived",
            ["archived_at", "is_pinned"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_instance") as batch:
        batch.drop_index("ix_strategy_instance_archived")
        batch.drop_column("archive_reason")
        batch.drop_column("archived_at")
        batch.drop_column("is_pinned")
