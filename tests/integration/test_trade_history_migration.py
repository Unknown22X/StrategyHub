from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config

from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.database import create_database_engine
from rangebot.engine.trade_history import TradeHistoryRepository


def _configuration(database_url: str) -> Config:
    root = Path(__file__).resolve().parents[2]
    configuration = Config(str(root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    return configuration


def test_trade_fill_ledger_upgrades_an_existing_database_and_accepts_nullable_gate_pnl(
    tmp_path,
) -> None:
    database_path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{database_path}"
    configuration = _configuration(database_url)
    command.upgrade(configuration, "0024_strategy_execution_settings")
    command.upgrade(configuration, "head")

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(trade_fill)").fetchall()
        }
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(trade_fill)").fetchall()
        }

    assert columns["environment"][3] == 1
    assert columns["external_trade_id"][3] == 1
    assert columns["realized_pnl"][3] == 0
    assert "ix_trade_fill_occurred_at" in indexes
    assert "ix_trade_fill_instance" in indexes

    repository = TradeHistoryRepository(create_database_engine(database_url))
    row = repository.record(
        TradeFillCreate(
            environment="testnet",
            external_trade_id="migration-trade",
            order_id="migration-order",
            contract="BTC_USDT",
            side="buy",
            position_effect="open",
            quantity=Decimal("1"),
            price=Decimal("65000"),
            fee=Decimal("0.5"),
            trade_value=Decimal("65000"),
            occurred_at=datetime(2026, 7, 18, 12, 0, tzinfo=UTC),
            source="gate_rest",
            origin="external",
        )
    )

    assert row.realized_pnl is None
    assert repository.summary(environment="testnet").realized_pnl is None
