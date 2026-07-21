from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.engine.market_data_manager import MarketDataManager


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _update(
    observed_at: datetime,
    *,
    source: str,
    sequence: int,
    price: str,
) -> MarketPriceUpdate:
    value = Decimal(price)
    return MarketPriceUpdate(
        symbol="BTC_USDT",
        last_price=value,
        mark_price=value - Decimal("0.1"),
        best_bid=value - Decimal("0.2"),
        best_ask=value + Decimal("0.2"),
        volume_24h=Decimal("100000"),
        funding_rate=Decimal("0.0001"),
        observed_at=observed_at,
        source=source,
        sequence=sequence,
    )


def _candle(base: datetime, index: int, close: str) -> NormalizedCandle:
    opened_at = base + timedelta(minutes=index * 15)
    value = Decimal(close)
    return NormalizedCandle(
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=15),
        open=value - Decimal("0.5"),
        high=value + Decimal("1"),
        low=value - Decimal("1"),
        close=value,
        volume=Decimal("100"),
        closed=True,
    )


def test_sequence_gap_requires_rest_snapshot_before_data_becomes_fresh() -> None:
    base = datetime(2026, 3, 1, tzinfo=UTC)
    clock = MutableClock(base)
    manager = MarketDataManager(clock=clock)

    initial = manager.apply_rest_snapshot(
        _update(base, source="gate_rest", sequence=10, price="100")
    )
    next_update = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=11, price="101")
    )
    duplicate = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=11, price="999")
    )
    gap = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=13, price="103")
    )
    ignored_during_gap = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=14, price="104")
    )
    reconciled = manager.apply_rest_snapshot(
        _update(base, source="gate_rest", sequence=13, price="103")
    )

    assert initial.state == "fresh"
    assert next_update.last_price == Decimal("101")
    assert duplicate.last_price == Decimal("101")
    assert gap.state == "stale"
    assert gap.state_reason == "sequence_gap"
    assert gap.sequence_gap is True
    assert gap.last_price == Decimal("101")
    assert ignored_during_gap.last_price == Decimal("101")
    assert reconciled.state == "fresh"
    assert reconciled.sequence_gap is False
    assert reconciled.last_price == Decimal("103")


def test_sequence_ranges_and_partial_channels_preserve_authoritative_state() -> None:
    base = datetime(2026, 3, 1, tzinfo=UTC)
    manager = MarketDataManager(clock=MutableClock(base))
    manager.apply_rest_snapshot(
        _update(base, source="gate_rest", sequence=100, price="100")
    )

    ranged = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=105, price="101").model_copy(
            update={"sequence_start": 101, "best_bid": None, "best_ask": None}
        )
    )
    partial_ticker = manager.apply_websocket_update(
        _update(base, source="gate_websocket", sequence=106, price="102").model_copy(
            update={
                "sequence_start": 106,
                "mark_price": None,
                "volume_24h": None,
                "funding_rate": None,
            }
        )
    )

    assert ranged.state == "fresh"
    assert ranged.sequence == 105
    assert ranged.best_bid == Decimal("99.8")
    assert ranged.best_ask == Decimal("100.2")
    assert partial_ticker.sequence == 106
    assert partial_ticker.mark_price == Decimal("100.9")
    assert partial_ticker.volume_24h == Decimal("100000")
    assert partial_ticker.funding_rate == Decimal("0.0001")


def test_freshness_reconnect_and_unavailable_states_are_explicit() -> None:
    base = datetime(2026, 3, 1, tzinfo=UTC)
    clock = MutableClock(base)
    manager = MarketDataManager(
        clock=clock, freshness_threshold=timedelta(seconds=5)
    )

    assert manager.track("ETH_USDT").state == "reconnecting"
    assert manager.status("UNKNOWN_USDT").state == "unavailable"
    manager.apply_rest_snapshot(
        _update(base, source="gate_rest", sequence=1, price="100")
    )
    clock.current = base + timedelta(seconds=6)

    stale = manager.snapshot("BTC_USDT")
    reconnecting = manager.mark_reconnecting("BTC_USDT")
    unavailable = manager.mark_unavailable("BTC_USDT", "gate_maintenance")

    assert stale.state == "stale"
    assert stale.state_reason == "freshness_timeout"
    assert stale.last_update_age_seconds == Decimal("6")
    assert reconnecting.state == "reconnecting"
    assert unavailable.state == "unavailable"
    assert unavailable.state_reason == "gate_maintenance"


def test_candle_backfill_deduplicates_and_builds_authoritative_strategy_context() -> None:
    base = datetime(2026, 3, 1, tzinfo=UTC)
    clock = MutableClock(base + timedelta(hours=2))
    manager = MarketDataManager(clock=clock, freshness_threshold=timedelta(hours=1))
    first = _candle(base, 0, "100")
    replacement = _candle(base, 0, "101")
    second = _candle(base, 1, "102")

    series = manager.replace_candles(
        "BTC_USDT",
        15,
        [second, first, replacement],
        source="gate_rest",
    )
    third = _candle(base, 2, "103")
    appended = manager.append_candle("BTC_USDT", 15, third)
    manager.apply_rest_snapshot(
        _update(clock.current, source="gate_rest", sequence=1, price="103")
    )
    context = manager.strategy_context(
        "BTC_USDT",
        15,
        evaluated_at=third.closed_at,
        reconciliation_ready=False,
        emergency_stop=True,
        candles_since_last_entry=2,
    )

    assert [candle.close for candle in series.candles] == [Decimal("101"), Decimal("102")]
    assert [candle.close for candle in appended.candles] == [
        Decimal("101"),
        Decimal("102"),
        Decimal("103"),
    ]
    assert context.last_price == Decimal("103")
    assert context.mark_price == Decimal("102.9")
    assert context.market_data_state == "fresh"
    assert context.reconciliation_ready is False
    assert context.emergency_stop is True
    assert context.candles_since_last_entry == 2
