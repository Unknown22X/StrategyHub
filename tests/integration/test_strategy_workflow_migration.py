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

    command.upgrade(configuration, "0032_account_risk_controls")

    with sqlite3.connect(database_path) as connection:
        setup_id = connection.execute(
            """
            SELECT setup_id FROM strategy_coin_setup
            WHERE runtime_instance_id = 'legacy-running'
            """
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO backtest_run (
                backtest_id, scan_id, strategy_type_id, strategy_version,
                symbol, timeframe_minutes, request_json, result_json,
                started_at, ended_at, created_at, setup_id, setup_revision
            ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-backtest",
                "range",
                "legacy",
                "BTC_USDT",
                15,
                "{}",
                "{}",
                now,
                now,
                now,
                setup_id,
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO trade_fill (
                environment, external_trade_id, order_id, contract, side,
                position_effect, quantity, price, fee, role, close_quantity,
                trade_value, realized_pnl, occurred_at, source, origin,
                instance_id, run_id, strategy_name_snapshot, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                "paper",
                "legacy-fill",
                "legacy-order",
                "BTC_USDT",
                "buy",
                "open",
                1,
                100,
                0.1,
                "taker",
                0,
                100,
                None,
                now,
                "paper_engine",
                "automatic_strategy",
                "legacy-running",
                "Legacy running",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO trade_ownership (
                identity_kind, external_identity, origin, environment,
                symbol, direction, instance_id, run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                "order",
                "legacy-order",
                "automatic_strategy",
                "paper",
                "BTC_USDT",
                "long",
                "legacy-running",
                now,
            ),
        )
        connection.commit()

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        templates = connection.execute(
            "SELECT template_id, type_id, status, current_revision FROM strategy_template"
        ).fetchall()
        setups = connection.execute(
            """
            SELECT runtime_instance_id, template_id, symbol, status, revision,
                   template_revision
            FROM strategy_coin_setup
            ORDER BY runtime_instance_id
            """
        ).fetchall()
        instances = connection.execute(
            """
            SELECT instance_id, type_id, template_id, template_version,
                   preset_id, preset_revision, status
            FROM strategy_instance
            ORDER BY instance_id
            """
        ).fetchall()
        configuration_versions = connection.execute(
            """
            SELECT instance_id, revision
            FROM strategy_configuration_version
            ORDER BY instance_id, revision
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
        preserved_backtests = connection.execute(
            "SELECT backtest_id, setup_id, setup_revision FROM backtest_run"
        ).fetchall()
        preserved_trades = connection.execute(
            """
            SELECT external_trade_id, order_id, instance_id
            FROM trade_fill
            """
        ).fetchall()
        preserved_ownership = connection.execute(
            """
            SELECT external_identity, instance_id
            FROM trade_ownership
            """
        ).fetchall()

    assert [(row[1], row[2], row[3]) for row in templates] == [
        ("range", "active", 1),
        ("range", "active", 1),
    ]
    preset_by_instance = {row[0]: row[1] for row in setups}
    assert [(row[0], row[2], row[3], row[4], row[5]) for row in setups] == [
        ("legacy-running", "BTC_USDT", "approved_paper", 1, 1),
        ("legacy-stopped", "ETH_USDT", "backtest_required", 1, 1),
    ]
    assert instances == [
        (
            "legacy-running",
            "range",
            "builtin:range",
            "legacy",
            preset_by_instance["legacy-running"],
            1,
            "running",
        ),
        (
            "legacy-stopped",
            "range",
            "builtin:range",
            "legacy",
            preset_by_instance["legacy-stopped"],
            1,
            "stopped",
        ),
    ]
    assert configuration_versions == [
        ("legacy-running", 1),
        ("legacy-stopped", 1),
    ]
    assert approvals == [(1, "paper", "approved")]
    assert deployments == [("legacy-running", "paper", "running", 1, 1)]
    assert {"setup_id", "setup_revision"}.issubset(backtest_columns)
    assert preserved_backtests == [("legacy-backtest", setup_id, 1)]
    assert preserved_trades == [("legacy-fill", "legacy-order", "legacy-running")]
    assert preserved_ownership == [("legacy-order", "legacy-running")]
