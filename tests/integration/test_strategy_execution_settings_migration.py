from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def _alembic_config(database_url: str) -> Config:
    repository_root = Path(__file__).resolve().parents[2]
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_strategy_execution_settings_are_present_on_a_fresh_database(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.post(
            "/v1/strategies",
            json={
                "type_id": "range",
                "name": "Fresh Range",
                "environment": "paper",
                "symbol": "BTC_USDT",
                "timeframe_minutes": 15,
                "direction": "both",
                "requested_margin": "33.5",
                "requested_leverage": 7,
                "configuration": {"proximity_percentage": "3"},
            },
        )
        strategy = response.json()
        versions = client.get(
            f"/v1/strategies/{strategy['instance_id']}/configuration-versions"
        ).json()

    assert response.status_code == 201
    assert strategy["requested_margin"] == "33.500000000000"
    assert strategy["requested_leverage"] == 7
    assert versions[0]["requested_margin"] == "33.500000000000"
    assert versions[0]["requested_leverage"] == 7


def test_strategy_execution_settings_upgrade_existing_database_with_safe_defaults(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0023_paper_performance_totals")

    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO strategy_instance (
                instance_id, type_id, name, environment, symbol,
                timeframe_minutes, direction, configuration_json, status,
                created_at, updated_at, revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "existing-strategy",
                "range",
                "Existing Range",
                "paper",
                "BTC_USDT",
                15,
                "both",
                "{}",
                "running",
                now,
                now,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO strategy_configuration_version (
                instance_id, revision, configuration_json, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            ("existing-strategy", 1, "{}", now),
        )
        connection.execute(
            """
            INSERT INTO strategy_run (
                run_id, instance_id, mode, status, started_at, ended_at, end_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("existing-run", "existing-strategy", "automatic", "active", now, None, None),
        )
        connection.commit()

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        instance_values = connection.execute(
            "SELECT requested_margin, requested_leverage FROM strategy_instance "
            "WHERE instance_id = ?",
            ("existing-strategy",),
        ).fetchone()
        version_values = connection.execute(
            "SELECT requested_margin, requested_leverage "
            "FROM strategy_configuration_version WHERE instance_id = ?",
            ("existing-strategy",),
        ).fetchone()
        run_values = connection.execute(
            "SELECT configuration_revision FROM strategy_run WHERE run_id = ?",
            ("existing-run",),
        ).fetchone()

    assert instance_values == (20, 3)
    assert version_values == (20, 3)
    assert run_values == (1,)
