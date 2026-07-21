from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_existing_strategy_runs_receive_snapshot_without_losing_history(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0033_strategy_template_preset_lineage")
    now = datetime.now(UTC).isoformat()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO strategy_instance (
                instance_id, type_id, template_id, template_version,
                preset_id, preset_revision, name, environment, symbol,
                timeframe_minutes, direction, requested_margin,
                requested_leverage, configuration_json, status,
                created_at, updated_at, revision
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-instance",
                "range",
                "builtin:range",
                "legacy",
                "Legacy instance",
                "paper",
                "BTC_USDT",
                15,
                "both",
                25,
                5,
                json.dumps({"mode": "rolling_window"}),
                "running",
                now,
                now,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO strategy_configuration_version (
                instance_id, revision, requested_margin,
                requested_leverage, configuration_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-instance",
                1,
                25,
                5,
                json.dumps({"mode": "rolling_window"}),
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO strategy_run (
                run_id, instance_id, mode, status, configuration_revision,
                started_at, ended_at, end_reason
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                "legacy-run",
                "legacy-instance",
                "automatic",
                "active",
                1,
                now,
            ),
        )
        connection.commit()

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT run_id, instance_id, status, configuration_snapshot_json
            FROM strategy_run
            WHERE run_id = 'legacy-run'
            """
        ).fetchone()
        columns = {
            item[1]
            for item in connection.execute("PRAGMA table_info(strategy_run)").fetchall()
        }

    snapshot = json.loads(row[3])
    assert row[:3] == ("legacy-run", "legacy-instance", "active")
    assert "configuration_snapshot_json" in columns
    assert snapshot["migration_source"] == "0034_strategy_run_configuration_snapshot"
    assert snapshot["configuration_revision"] == 1
    assert snapshot["instance"]["instance_id"] == "legacy-instance"
    assert snapshot["instance"]["configuration"] == {"mode": "rolling_window"}
    assert snapshot["instance"]["requested_margin"].startswith("25")
    assert snapshot["instance"]["requested_leverage"] == 5
