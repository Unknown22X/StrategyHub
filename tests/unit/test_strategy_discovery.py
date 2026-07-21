from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.analysis import RangeAnalysisConfig
from rangebot.domain.discovery import DiscoveryMarketContract, StrategyScanRequest
from rangebot.domain.strategy_runtime import NormalizedCandle, StrategyEvaluationContext
from rangebot.engine.discovery import (
    GateStrategyDiscoveryCoordinator,
    StrategyDiscoveryService,
)
from rangebot.engine.strategy_registry import discover_strategy_registry


def _candles(base: datetime, count: int = 210) -> tuple[NormalizedCandle, ...]:
    candles: list[NormalizedCandle] = []
    for index in range(count):
        opened = base + timedelta(minutes=index)
        close = Decimal("105") if index % 2 == 0 else Decimal("115")
        candles.append(
            NormalizedCandle(
                opened_at=opened,
                closed_at=opened + timedelta(minutes=5),
                open=Decimal("110"),
                high=Decimal("120"),
                low=Decimal("100"),
                close=close,
                volume=Decimal("100000"),
                closed=True,
            )
        )
    return tuple(candles)


def _context(symbol: str, last_price: str) -> StrategyEvaluationContext:
    candles = _candles(datetime(2026, 1, 1, tzinfo=UTC))
    return StrategyEvaluationContext(
        symbol=symbol,
        evaluated_at=candles[-1].closed_at,
        timeframe_minutes=5,
        candles=candles,
        last_price=Decimal(last_price),
        mark_price=Decimal(last_price),
        best_bid=Decimal(last_price) - Decimal("0.01"),
        best_ask=Decimal(last_price) + Decimal("0.01"),
        market_data_state="fresh",
        reconciliation_ready=True,
    )


def test_builtin_strategies_declare_scanning_and_backtesting_contracts() -> None:
    registry = discover_strategy_registry()

    for type_id in ("range", "adaptive_trend", "range_breakout"):
        metadata = registry.get(type_id)
        assert metadata.supports_scanning is True
        assert metadata.supports_backtesting is True
        assert metadata.minimum_backtest_candles >= 200
        assert metadata.candidate_metrics
        assert registry.scanner(type_id).type_id == type_id


def test_range_discovery_ranks_boundary_candidate_above_middle_of_range() -> None:
    registry = discover_strategy_registry()
    service = StrategyDiscoveryService(registry)
    configuration = RangeAnalysisConfig(
        mode="rolling_window",
        timeframe_minutes=5,
        range_mode="interval",
        minimum_range_percentage=Decimal("15"),
        maximum_range_percentage=Decimal("25"),
        proximity_percentage=Decimal("3"),
        direction="both",
    ).model_dump(mode="json")

    result = service.scan(
        StrategyScanRequest(
            strategy_type_id="range",
            timeframe_minutes=5,
            configuration=configuration,
            maximum_candidates=2,
        ),
        [_context("CENTER_USDT", "110"), _context("EDGE_USDT", "101")],
    )

    assert result.scanned_symbols == 2
    assert [candidate.symbol for candidate in result.candidates] == [
        "EDGE_USDT",
        "CENTER_USDT",
    ]
    edge = result.candidates[0]
    assert edge.signal == "long"
    assert edge.backtest_ready is True
    assert edge.metrics["range_percentage"] == Decimal("20")
    assert edge.metrics["nearest_proximity_percentage"] == Decimal("1")


class _FakeDiscoveryMarketData:
    def __init__(self) -> None:
        self.contract_arguments: tuple[Decimal, int | None] | None = None

    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]:
        self.contract_arguments = (minimum_quote_volume, maximum_contracts)
        return (
            DiscoveryMarketContract(
                symbol="EDGE_USDT",
                last_price=Decimal("101"),
                mark_price=Decimal("101"),
                best_bid=Decimal("100.99"),
                best_ask=Decimal("101.01"),
                volume_24h_quote=Decimal("2000000"),
            ),
            DiscoveryMarketContract(
                symbol="BAD_USDT",
                last_price=Decimal("10"),
                volume_24h_quote=Decimal("1500000"),
            ),
            DiscoveryMarketContract(
                symbol="CENTER_USDT",
                last_price=Decimal("110"),
                mark_price=Decimal("110"),
                best_bid=Decimal("109.99"),
                best_ask=Decimal("110.01"),
                volume_24h_quote=Decimal("1000000"),
            ),
        )

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]:
        assert timeframe_minutes == 5
        assert limit == 200
        if symbol == "BAD_USDT":
            raise ConnectionError("simulated Gate history failure")
        return _candles(datetime(2026, 1, 1, tzinfo=UTC), count=limit)


def test_gate_coordinator_scans_liquid_universe_and_isolates_symbol_failure() -> None:
    registry = discover_strategy_registry()
    market_data = _FakeDiscoveryMarketData()
    coordinator = GateStrategyDiscoveryCoordinator(
        registry,
        market_data,
        maximum_workers=2,
    )
    request = StrategyScanRequest(
        strategy_type_id="range",
        timeframe_minutes=5,
        configuration=RangeAnalysisConfig(
            timeframe_minutes=5,
            minimum_range_percentage=Decimal("15"),
            maximum_range_percentage=Decimal("25"),
        ).model_dump(mode="json"),
        minimum_quote_volume=Decimal("500000"),
        maximum_symbols=3,
        maximum_candidates=2,
    )

    result = coordinator.scan(request)

    assert market_data.contract_arguments == (Decimal("500000"), 3)
    assert result.universe_symbols == 3
    assert result.scanned_symbols == 2
    assert [candidate.symbol for candidate in result.candidates] == [
        "EDGE_USDT",
        "CENTER_USDT",
    ]
    assert [failure.symbol for failure in result.failures] == ["BAD_USDT"]
    assert result.failures[0].reason_code == "market_history_unavailable"


def test_discovery_rejects_timeframe_that_conflicts_with_configuration() -> None:
    registry = discover_strategy_registry()
    service = StrategyDiscoveryService(registry)
    request = StrategyScanRequest(
        strategy_type_id="range",
        timeframe_minutes=15,
        configuration=RangeAnalysisConfig(timeframe_minutes=5).model_dump(mode="json"),
    )

    try:
        service.scan(request, [_context("BTC_USDT", "101")])
    except ValueError as error:
        assert "configuration timeframe" in str(error)
    else:
        raise AssertionError("Conflicting scanner timeframes must be rejected.")


def test_discovery_deduplicates_symbol_and_ignores_other_timeframes() -> None:
    registry = discover_strategy_registry()
    service = StrategyDiscoveryService(registry)
    request = StrategyScanRequest(
        strategy_type_id="range",
        timeframe_minutes=5,
        configuration=RangeAnalysisConfig(timeframe_minutes=5).model_dump(mode="json"),
    )
    old = _context("BTC_USDT", "101")
    newer = old.model_copy(update={"evaluated_at": old.evaluated_at + timedelta(minutes=5)})
    wrong_timeframe = old.model_copy(
        update={"symbol": "ETH_USDT", "timeframe_minutes": 15}
    )

    result = service.scan(request, [old, newer, wrong_timeframe])

    assert result.scanned_symbols == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].evaluated_at == newer.evaluated_at
