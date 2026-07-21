from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def _alembic_config(database_url: str) -> Config:
    repository_root = Path(__file__).resolve().parents[2]
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_account_risk_policy_upgrades_existing_database_with_safe_defaults(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0027_trailing_protection_recovery")

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(account_risk_policy)")
        }
        values = connection.execute(
            """
            SELECT daily_loss_enabled, daily_loss_limit,
                   losing_trade_enabled, losing_trade_limit,
                   automatic_trade_enabled, automatic_trade_limit,
                   revision
            FROM account_risk_policy WHERE id = 1
            """
        ).fetchone()
        baseline_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(account_daily_risk_baseline)"
            )
        }
        baselines = connection.execute(
            "SELECT environment, day, baseline_equity FROM account_daily_risk_baseline"
        ).fetchall()

    assert columns == {
        "id",
        "daily_loss_enabled",
        "daily_loss_limit",
        "losing_trade_enabled",
        "losing_trade_limit",
        "automatic_trade_enabled",
        "automatic_trade_limit",
        "revision",
        "updated_at",
    }
    assert values == (1, 100, 1, 3, 1, 5, 1)
    assert baseline_columns == {
        "environment",
        "day",
        "baseline_equity",
        "captured_at",
        "source",
    }
    assert baselines == []
