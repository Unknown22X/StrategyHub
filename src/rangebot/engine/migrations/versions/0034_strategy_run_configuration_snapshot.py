"""Persist immutable Strategy Run configuration snapshots.

Revision ID: 0034_strategy_run_configuration_snapshot
Revises: 0033_strategy_template_preset_lineage
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0034_strategy_run_configuration_snapshot"
down_revision = "0033_strategy_template_preset_lineage"
branch_labels = None
depends_on = None


def _timestamp_text(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def upgrade() -> None:
    with op.batch_alter_table("strategy_run") as batch:
        batch.add_column(
            sa.Column("configuration_snapshot_json", sa.Text(), nullable=True)
        )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT run.run_id,
                   run.configuration_revision,
                   instance.instance_id,
                   instance.type_id,
                   instance.template_id,
                   instance.template_version,
                   instance.preset_id,
                   instance.preset_revision,
                   instance.name,
                   instance.environment,
                   instance.symbol,
                   instance.timeframe_minutes,
                   instance.direction,
                   instance.requested_margin AS instance_requested_margin,
                   instance.requested_leverage AS instance_requested_leverage,
                   instance.configuration_json AS instance_configuration_json,
                   instance.status,
                   instance.created_at,
                   instance.updated_at,
                   instance.revision,
                   version.requested_margin,
                   version.requested_leverage,
                   version.configuration_json
            FROM strategy_run AS run
            JOIN strategy_instance AS instance
              ON instance.instance_id = run.instance_id
            LEFT JOIN strategy_configuration_version AS version
              ON version.instance_id = run.instance_id
             AND version.revision = run.configuration_revision
            """
        )
    ).mappings()
    for row in rows:
        configuration_json = (
            row["configuration_json"] or row["instance_configuration_json"] or "{}"
        )
        requested_margin = (
            row["requested_margin"]
            if row["requested_margin"] is not None
            else row["instance_requested_margin"]
        )
        requested_leverage = (
            row["requested_leverage"]
            if row["requested_leverage"] is not None
            else row["instance_requested_leverage"]
        )
        snapshot = {
            "schema_version": 1,
            "migration_source": revision,
            "instance": {
                "instance_id": row["instance_id"],
                "type_id": row["type_id"],
                "template_id": row["template_id"],
                "template_version": row["template_version"],
                "preset_id": row["preset_id"],
                "preset_revision": row["preset_revision"],
                "name": row["name"],
                "environment": row["environment"],
                "symbol": row["symbol"],
                "timeframe_minutes": row["timeframe_minutes"],
                "direction": row["direction"],
                "requested_margin": str(requested_margin),
                "requested_leverage": requested_leverage,
                "configuration": json.loads(configuration_json),
                "status": row["status"],
                "created_at": _timestamp_text(row["created_at"]),
                "updated_at": _timestamp_text(row["updated_at"]),
                "revision": row["revision"],
            },
            "configuration_revision": row["configuration_revision"],
        }
        connection.execute(
            sa.text(
                """
                UPDATE strategy_run
                SET configuration_snapshot_json = :snapshot
                WHERE run_id = :run_id
                """
            ),
            {
                "run_id": row["run_id"],
                "snapshot": json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        )

    with op.batch_alter_table("strategy_run") as batch:
        batch.alter_column(
            "configuration_snapshot_json",
            existing_type=sa.Text(),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("strategy_run") as batch:
        batch.drop_column("configuration_snapshot_json")
