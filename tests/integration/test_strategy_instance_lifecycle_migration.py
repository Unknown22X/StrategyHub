from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def _alembic_config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_existing_strategy_instances_are_preserved_and_not_archived(tmp_path) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0034_strategy_run_configuration_snapshot")
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
                "existing-instance",
                "range",
                "builtin:range",
                "legacy",
                "Existing",
                "paper",
                "BTC_USDT",
                15,
                "both",
                20,
                3,
                "{}",
                "stopped",
                now,
                now,
                7,
            ),
        )
        connection.commit()

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT instance_id, is_pinned, archived_at, archive_reason, revision
            FROM strategy_instance
            WHERE instance_id = 'existing-instance'
            """
        ).fetchone()
        columns = {
            item[1]
            for item in connection.execute(
                "PRAGMA table_info(strategy_instance)"
            ).fetchall()
        }

    assert row == ("existing-instance", 0, None, None, 7)
    assert {"is_pinned", "archived_at", "archive_reason"}.issubset(columns)
