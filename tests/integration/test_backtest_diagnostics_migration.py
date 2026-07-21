from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


def _config(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_backtest_diagnostics_migration_adds_nullable_fields_without_rows(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    config = _config(database_url)
    command.upgrade(config, "0035_strategy_instance_lifecycle")
    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(backtest_portfolio_run)")
        }
        count = connection.execute(
            "SELECT COUNT(*) FROM backtest_portfolio_run"
        ).fetchone()[0]

    assert {"failure_code", "failure_stage"}.issubset(columns)
    assert count == 0
