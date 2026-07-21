from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.trade_history import TradeHistoryRepository


NOW = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)


def _fill(**updates) -> TradeFillCreate:
    values = {
        "environment": "testnet",
        "external_trade_id": "trade-1",
        "order_id": "order-1",
        "contract": "BTC_USDT",
        "side": "buy",
        "position_effect": "open",
        "quantity": Decimal("2"),
        "price": Decimal("65000"),
        "fee": Decimal("0.5"),
        "role": "taker",
        "close_quantity": Decimal("0"),
        "trade_value": Decimal("130000"),
        "occurred_at": NOW,
        "source": "gate_rest",
        "origin": "external",
    }
    values.update(updates)
    return TradeFillCreate(**values)


def test_trade_history_is_idempotent_and_late_ownership_does_not_rewrite_financials(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    apply_migrations(database_url)
    repository = TradeHistoryRepository(create_database_engine(database_url))

    first = repository.record(_fill())
    duplicate = repository.record(_fill(price=Decimal("1"), fee=Decimal("999")))
    updated = repository.attach_order_ownership(
        environment="testnet",
        order_id="order-1",
        origin="automatic_strategy",
        instance_id="strategy-1",
        run_id="run-1",
        strategy_name_snapshot="BTC Trend",
    )
    rows = repository.list(instance_id="strategy-1")
    summary = repository.summary(instance_id="strategy-1")

    assert duplicate.fill_id == first.fill_id
    assert duplicate.price == Decimal("65000")
    assert duplicate.fee == Decimal("0.5")
    assert updated == 1
    assert len(rows) == 1
    assert rows[0].origin == "automatic_strategy"
    assert rows[0].run_id == "run-1"
    assert rows[0].strategy_name_snapshot == "BTC Trend"
    assert summary.fills == 1
    assert summary.opened_quantity == Decimal("2")
    assert summary.closed_quantity == Decimal("0")
    assert summary.realized_pnl is None
    assert summary.realized_pnl_known_fills == 0
    assert summary.winning_fills == 0
    assert summary.losing_fills == 0
    assert summary.win_rate_percentage is None
    assert summary.fees == Decimal("0.5")


def test_trade_history_filters_and_restart_persistence(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    apply_migrations(database_url)
    repository = TradeHistoryRepository(create_database_engine(database_url))
    repository.record(_fill())
    repository.record(
        _fill(
            external_trade_id="trade-2",
            order_id="order-2",
            contract="ETH_USDT",
            side="sell",
            position_effect="close",
            quantity=Decimal("1"),
            close_quantity=Decimal("1"),
            realized_pnl=Decimal("15"),
            occurred_at=NOW + timedelta(minutes=1),
        )
    )
    repository.record(
        _fill(
            external_trade_id="trade-3",
            order_id="order-3",
            contract="ETH_USDT",
            side="sell",
            position_effect="close",
            quantity=Decimal("1"),
            close_quantity=Decimal("1"),
            realized_pnl=Decimal("-5"),
            occurred_at=NOW + timedelta(minutes=2),
        )
    )

    restarted = TradeHistoryRepository(create_database_engine(database_url))
    recent = restarted.list(since=NOW + timedelta(seconds=30))
    btc = restarted.list(contract="BTC_USDT")
    summary = restarted.summary(environment="testnet")

    assert [row.external_trade_id for row in recent] == ["trade-3", "trade-2"]
    assert [row.external_trade_id for row in btc] == ["trade-1"]
    assert summary.fills == 3
    assert summary.opened_quantity == Decimal("2")
    assert summary.closed_quantity == Decimal("2")
    assert summary.realized_pnl == Decimal("10")
    assert summary.realized_pnl_known_fills == 2
    assert summary.winning_fills == 1
    assert summary.losing_fills == 1
    assert summary.win_rate_percentage == Decimal("50")
    assert summary.gross_profit == Decimal("15")
    assert summary.gross_loss == Decimal("-5")
    assert summary.average_win == Decimal("15")
    assert summary.average_loss == Decimal("-5")
    assert summary.profit_factor == Decimal("3")
