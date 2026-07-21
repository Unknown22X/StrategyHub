from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.strategy import StrategyInstanceCreate
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.api import create_app


def _candle(base: datetime, index: int) -> NormalizedCandle:
    opened_at = base + timedelta(minutes=index * 15)
    price = Decimal("100") + Decimal(index)
    return NormalizedCandle(
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=15),
        open=price,
        high=price + Decimal("1"),
        low=price - Decimal("1"),
        close=price + Decimal("0.5"),
        volume=Decimal("1000"),
        closed=True,
    )


def test_runtime_context_uses_real_market_manager_and_restart_safe_fill_cooldown(
    tmp_path,
) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    now = datetime.now(UTC)
    base = now - timedelta(minutes=60)

    with TestClient(app):
        instance = app.state.strategy_instance_repository.create(
            StrategyInstanceCreate(
                type_id="range_breakout",
                name="Cooldown context",
                environment="paper",
                symbol="BTC_USDT",
                timeframe_minutes=15,
                direction="both",
                configuration={},
            )
        )
        market_snapshot = app.state.market_data_manager.apply_rest_snapshot(
            MarketPriceUpdate(
                symbol="BTC_USDT",
                last_price=Decimal("104"),
                mark_price=Decimal("104"),
                best_bid=Decimal("103.9"),
                best_ask=Decimal("104.1"),
                volume_24h=Decimal("1000000"),
                funding_rate=Decimal("0.0001"),
                observed_at=now,
                source="gate_rest",
                sequence=1,
            )
        )
        candles = tuple(_candle(base, index) for index in range(4))
        app.state.market_data_manager.replace_candles(
            "BTC_USDT",
            15,
            candles,
            source="gate_rest",
        )
        app.state.trade_history_repository.record(
            TradeFillCreate(
                environment="paper",
                external_trade_id="cooldown-open",
                contract="BTC_USDT",
                side="buy",
                position_effect="open",
                quantity=Decimal("1"),
                price=Decimal("102"),
                occurred_at=candles[1].closed_at + timedelta(seconds=1),
                source="paper_engine",
                origin="automatic_strategy",
                instance_id=instance.instance_id,
            )
        )

        context = app.state.strategy_runtime_runner._build_context(instance)

    assert context.market_data_state == "fresh"
    assert context.evaluated_at == market_snapshot.received_at
    assert context.reconciliation_ready is True
    assert context.emergency_stop is False
    assert context.candles_since_last_entry == 2
