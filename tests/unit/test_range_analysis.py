from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from rangebot.domain.analysis import Candle, RangeAnalysisConfig, evaluate_range


def _candles(count: int, start: datetime | None = None) -> list[Candle]:
    opened_at = start or datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    return [
        Candle(
            opened_at=opened_at + timedelta(minutes=index),
            open=Decimal("100"),
            high=Decimal("120"),
            low=Decimal("100"),
            close=Decimal("110"),
        )
        for index in range(count)
    ]


def test_rolling_window_uses_forming_candle_and_reports_history_gap() -> None:
    result = evaluate_range(
        RangeAnalysisConfig(timeframe_minutes=5),
        _candles(5),
        Decimal("100"),
    )
    gap = evaluate_range(
        RangeAnalysisConfig(timeframe_minutes=5),
        _candles(5)[:2] + _candles(5)[3:],
        Decimal("100"),
    )

    assert result.history_status == "ready"
    assert result.opening_price == Decimal("100")
    assert result.high == Decimal("120")
    assert gap.history_status == "history_gap"
    assert gap.entry_blocked is True
    assert gap.protective_actions_available is True


def test_current_gate_candle_requires_interval_boundary() -> None:
    candle = _candles(1, datetime(2026, 7, 12, 12, 10, tzinfo=UTC))[0]
    valid = evaluate_range(
        RangeAnalysisConfig(mode="current_gate_candle", timeframe_minutes=5),
        [candle],
        Decimal("100"),
        evaluated_at=datetime(2026, 7, 12, 12, 12, tzinfo=UTC),
    )
    invalid = evaluate_range(
        RangeAnalysisConfig(mode="current_gate_candle", timeframe_minutes=5),
        [
            candle.model_copy(
                update={"opened_at": candle.opened_at + timedelta(minutes=1)}
            )
        ],
        Decimal("100"),
        evaluated_at=datetime(2026, 7, 12, 12, 12, tzinfo=UTC),
    )

    assert valid.history_status == "ready"
    assert invalid.history_status == "history_gap"


def test_current_gate_candle_rejects_a_prior_interval() -> None:
    candle = _candles(1, datetime(2026, 7, 12, 12, 5, tzinfo=UTC))[0]

    result = evaluate_range(
        RangeAnalysisConfig(mode="current_gate_candle", timeframe_minutes=5),
        [candle],
        Decimal("100"),
        evaluated_at=datetime(2026, 7, 12, 12, 12, tzinfo=UTC),
    )

    assert result.history_status == "history_gap"


def test_gate_candle_adapter_orders_normalized_candles() -> None:
    from rangebot.engine.market import GatePublicMarketAdapter

    candles = GatePublicMarketAdapter.map_candles(
        [
            {
                "timestamp": 120,
                "open": "100",
                "high": "101",
                "low": "99",
                "close": "100",
            },
            {"timestamp": 60, "open": "99", "high": "100", "low": "98", "close": "99"},
        ]
    )

    assert [candle.opened_at.minute for candle in candles] == [1, 2]


def test_conflicting_long_and_short_signal_is_rejected() -> None:
    result = evaluate_range(
        RangeAnalysisConfig(timeframe_minutes=5, proximity_percentage=Decimal("100")),
        _candles(5),
        Decimal("110"),
    )

    assert result.long_eligible is False
    assert result.short_eligible is False
    assert "conflicting_signals" in result.blocking_reasons


@given(
    low=st.decimals(min_value="1", max_value="100000", places=4),
    span=st.decimals(min_value="0", max_value="100000", places=4),
)
def test_range_and_proximity_never_use_float(low: Decimal, span: Decimal) -> None:
    high = low + span
    candles = [
        Candle(
            opened_at=datetime(2026, 7, 12, 12, index, tzinfo=UTC),
            open=low,
            high=high,
            low=low,
            close=low,
        )
        for index in range(5)
    ]

    result = evaluate_range(
        RangeAnalysisConfig(timeframe_minutes=5, proximity_percentage=Decimal("3")),
        candles,
        low,
    )

    assert isinstance(result.range_percentage, Decimal)
    assert isinstance(result.long_proximity_percentage, Decimal)
    assert result.long_proximity_percentage == Decimal("0")
