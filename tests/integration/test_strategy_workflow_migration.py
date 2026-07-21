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


def test_existing_strategy_instances_are_backfilled_without_losing_runtime_state(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0028_account_risk_policy")

    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database_path) as connection:
        for instance_id, status in (
            ("legacy-running", "running"),
            ("legacy-stopped", "stopped"),
        ):
            connection.execute(
                """
                INSERT INTO strategy_instance (
                    instance_id, type_id, name, environment, symbol,
                    timeframe_minutes, direction, requested_margin,
                    requested_leverage, configuration_json, status,
                    created_at, updated_at, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instance_id,
                    "range",
                    f"Legacy {status}",
                    "paper",
                    "BTC_USDT" if status == "running" else "ETH_USDT",
                    15,
                    "both",
                    25,
                    4,
                    json.dumps({"proximity_percentage": "3"}),
                    status,
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
                (instance_id, 1, 25, 4, "{}", now),
            )
        connection.commit()

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        templates = connection.execute(
            "SELECT type_id, status, current_revision FROM strategy_template"
        ).fetchall()
        setups = connection.execute(
            """
            SELECT runtime_instance_id, symbol, status, revision,
                   template_revision
            FROM strategy_coin_setup
            ORDER BY runtime_instance_id
            """
        ).fetchall()
        approvals = connection.execute(
            """
            SELECT setup_revision, mode, status
            FROM strategy_setup_approval
            """
        ).fetchall()
        deployments = connection.execute(
            """
            SELECT runtime_instance_id, environment, status,
                   setup_revision, template_revision
            FROM bot_deployment
            """
        ).fetchall()
        backtest_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(backtest_run)").fetchall()
        }

    assert templates == [("range", "active", 1), ("range", "active", 1)]
    assert setups == [
        ("legacy-running", "BTC_USDT", "approved_paper", 1, 1),
        ("legacy-stopped", "ETH_USDT", "backtest_required", 1, 1),
    ]
    assert approvals == [(1, "paper", "approved")]
    assert deployments == [("legacy-running", "paper", "running", 1, 1)]
    assert {"setup_id", "setup_revision"}.issubset(backtest_columns)
