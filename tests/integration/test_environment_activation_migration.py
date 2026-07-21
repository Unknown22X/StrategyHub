from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config

from rangebot.engine.database import create_database_engine
from rangebot.engine.environment_activation import EnvironmentActivationRepository


def _alembic_config(database_url: str) -> Config:
    repository_root = Path(__file__).resolve().parents[2]
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_environment_activation_migration_does_not_trust_existing_preferences(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "0030_production_backtesting")

    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(environment_activation)")
        }
        rows = connection.execute(
            "SELECT environment, confirmed_at, revision FROM environment_activation"
        ).fetchall()

    assert columns == {"id", "environment", "confirmed_at", "revision"}
    assert rows == []


def test_confirmed_environment_is_persisted_separately_from_settings(tmp_path) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _alembic_config(database_url)
    command.upgrade(configuration, "head")
    repository = EnvironmentActivationRepository(create_database_engine(database_url))

    first = repository.save("testnet")
    second = repository.save("live")
    restored = repository.get()

    assert first.environment == "testnet"
    assert first.revision == 1
    assert second.environment == "live"
    assert second.revision == 2
    assert restored == second
