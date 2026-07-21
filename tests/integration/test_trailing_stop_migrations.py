from decimal import Decimal
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config

from rangebot.domain.strategy import TradeOwnershipCreate
from rangebot.engine.database import create_database_engine
from rangebot.engine.strategy_instances import StrategyInstanceRepository


def _configuration(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_trailing_protection_migrations_upgrade_existing_database_and_persist_recovery_state(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _configuration(database_url)
    command.upgrade(configuration, "0025_trade_fill_ledger")
    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        paper_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(paper_protection)").fetchall()
        }
        ownership_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(trade_ownership)").fetchall()
        }

    assert {
        "trailing_stop_price",
        "trailing_distance",
        "trailing_extremum_price",
    }.issubset(paper_columns)
    assert {
        "trailing_stop_price",
        "trailing_stop_distance",
        "trailing_state",
        "trailing_order_id",
        "trailing_last_error",
        "trailing_updated_at",
    }.issubset(ownership_columns)

    repository = StrategyInstanceRepository(create_database_engine(database_url))
    created = repository.record_trade_ownership(
        TradeOwnershipCreate(
            identity_kind="position",
            external_identity="testnet:BTC_USDT:long",
            origin="manual",
            environment="testnet",
            symbol="BTC_USDT",
            direction="long",
            trailing_stop_price=Decimal("64000"),
            trailing_stop_distance=Decimal("1000"),
            trailing_state="desired",
        )
    )
    updated = repository.update_trailing_protection(
        "position",
        created.external_identity,
        state="active",
        trailing_order_id="trail-after-upgrade",
    )

    assert updated.trailing_stop_price == Decimal("64000")
    assert updated.trailing_stop_distance == Decimal("1000")
    assert updated.trailing_state == "active"
    assert updated.trailing_order_id == "trail-after-upgrade"
    assert updated.trailing_last_error is None
