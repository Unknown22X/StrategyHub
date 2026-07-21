"""Separate immutable built-in Templates from editable user Presets.

Revision ID: 0033_strategy_template_preset_lineage
Revises: 0032_account_risk_controls
"""

from alembic import op
import sqlalchemy as sa


revision = "0033_strategy_template_preset_lineage"
down_revision = "0032_account_risk_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("strategy_instance") as batch:
        batch.add_column(sa.Column("template_id", sa.String(length=72), nullable=True))
        batch.add_column(
            sa.Column("template_version", sa.String(length=50), nullable=True)
        )
        batch.add_column(sa.Column("preset_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("preset_revision", sa.Integer(), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE strategy_instance
            SET template_id = 'builtin:' || type_id,
                template_version = 'legacy'
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE strategy_instance
            SET preset_id = (
                    SELECT setup.template_id
                    FROM strategy_coin_setup AS setup
                    WHERE setup.runtime_instance_id = strategy_instance.instance_id
                    ORDER BY setup.created_at ASC
                    LIMIT 1
                ),
                preset_revision = (
                    SELECT setup.template_revision
                    FROM strategy_coin_setup AS setup
                    WHERE setup.runtime_instance_id = strategy_instance.instance_id
                    ORDER BY setup.created_at ASC
                    LIMIT 1
                )
            WHERE EXISTS (
                SELECT 1
                FROM strategy_coin_setup AS setup
                WHERE setup.runtime_instance_id = strategy_instance.instance_id
            )
            """
        )
    )

    with op.batch_alter_table("strategy_instance") as batch:
        batch.alter_column(
            "template_id", existing_type=sa.String(length=72), nullable=False
        )
        batch.alter_column(
            "template_version",
            existing_type=sa.String(length=50),
            nullable=False,
        )
        batch.create_index(
            "ix_strategy_instance_template",
            ["template_id", "preset_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_instance") as batch:
        batch.drop_index("ix_strategy_instance_template")
        batch.drop_column("preset_revision")
        batch.drop_column("preset_id")
        batch.drop_column("template_version")
        batch.drop_column("template_id")
