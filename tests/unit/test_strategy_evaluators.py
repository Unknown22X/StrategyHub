from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from rangebot.domain.analysis import Candle, RangeAnalysisConfig, evaluate_range
from rangebot.domain.strategy_runtime import NormalizedCandle, StrategyEvaluationContext
from rangebot.strategies.adaptive_trend import AdaptiveTrendEvaluator
from rangebot.strategies.range_breakout import RangeBreakoutEvaluator
from rangebot.strategies.range_strategy import RangeStrategyEvaluator


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(
    index: int,
    close: str,
    *,
    interval_minutes: int = 15,
    volume: str = "100",
    closed: bool = True,
    high: str | None = None,
    low: str | None = None,
) -> NormalizedCandle:
    close_value = Decimal(close)
    open_value = close_value - Decimal("0.5")
    opened_at = BASE + timedelta(minutes=index * interval_minutes)
    return NormalizedCandle(
        opened_at=opened_at,
        closed_at=opened_at + timedelta(minutes=interval_minutes),
        open=open_value,
        high=Decimal(high) if high is not None else close_value + Decimal("1"),
        low=Decimal(low) if low is not None else open_value - Decimal("1"),
        close=close_value,
        volume=Decimal(volume),
        closed=closed,
    )


def _context(
    candles: tuple[NormalizedCandle, ...],
    *,
    timeframe_minutes: int = 15,
    last_price: str | None = None,
    market_data_state: str = "fresh",
) -> StrategyEvaluationContext:
    completed = [candle for candle in candles if candle.closed]
    evaluated_at = max(candle.closed_at for candle in completed)
    price = Decimal(last_price) if last_price else completed[-1].close
    return StrategyEvaluationContext(
        symbol="BTC_USDT",
        evaluated_at=evaluated_at,
        timeframe_minutes=timeframe_minutes,
        candles=candles,
        last_price=price,
        mark_price=price,
        best_bid=price - Decimal("0.05"),
        best_ask=price + Decimal("0.05"),
        market_data_state=market_data_state,
        reconciliation_ready=True,
        emergency_stop=False,
    )


def test_adaptive_trend_uses_only_completed_candles_and_blocks_stale_data() -> None:
    closed = tuple(_candle(index, str(100 + index)) for index in range(10))
    config = {
        "fast_ema_period": 3,
        "slow_ema_period": 5,
        "adx_period": 3,
        "minimum_adx": "0",
        "atr_period": 3,
        "maximum_spread_percentage": "1",
        "trailing_stop_atr_multiple": "0.5",
    }
    evaluator = AdaptiveTrendEvaluator()
    baseline = evaluator.evaluate(_context(closed), config)
    unfinished = _candle(
        10,
        "1",
        closed=False,
        high="1000",
        low="0.1",
        volume="1000000",
    )
    with_unfinished = evaluator.evaluate(_context((*closed, unfinished)), config)
    stale = evaluator.evaluate(
        _context(closed, market_data_state="stale"), config
    )

    assert baseline.eligible is True
    assert baseline.signal == "long"
    assert baseline.trade_request is not None
    assert baseline.trade_request.trailing_stop_price is not None
    assert baseline.analysis["trend"] == "upward"
    assert with_unfinished.signal == baseline.signal
    assert with_unfinished.analysis["fast_ema"] == baseline.analysis["fast_ema"]
    assert with_unfinished.analysis["slow_ema"] == baseline.analysis["slow_ema"]
    assert with_unfinished.used_closed_candles == len(closed)
    assert stale.eligible is False
    assert stale.trade_request is None
    assert "market_data_stale" in stale.reason_codes


def test_breakout_channel_excludes_confirmation_and_unfinished_candles() -> None:
    prior_prices = ("99", "100", "101", "100", "102", "101")
    prior = tuple(
        _candle(index, price, volume="100")
        for index, price in enumerate(prior_prices)
    )
    confirmation = _candle(6, "104", volume="250", high="110")
    config = {
        "channel_period": 5,
        "confirmation_closes": 1,
        "volume_period": 5,
        "volume_multiplier": "1.5",
        "atr_period": 3,
        "minimum_breakout_atr_multiple": "0",
        "maximum_breakout_atr_multiple": "10",
        "maximum_spread_percentage": "1",
        "trailing_stop_atr_multiple": "0.5",
    }
    evaluator = RangeBreakoutEvaluator()
    baseline = evaluator.evaluate(_context((*prior, confirmation)), config)
    unfinished = _candle(
        7,
        "200",
        volume="10000",
        closed=False,
        high="250",
        low="90",
    )
    with_unfinished = evaluator.evaluate(
        _context((*prior, confirmation, unfinished)), config
    )

    assert baseline.eligible is True
    assert baseline.signal == "long"
    assert baseline.analysis["channel_high"] == Decimal("103")
    assert baseline.analysis["channel_high"] != confirmation.high
    assert baseline.trade_request is not None
    assert baseline.trade_request.trailing_stop_price is not None
    assert baseline.trade_request.trailing_stop_price < baseline.trade_request.reference_price
    assert with_unfinished.signal == baseline.signal
    assert with_unfinished.analysis["channel_high"] == baseline.analysis["channel_high"]
    assert with_unfinished.used_closed_candles == 7


def test_breakout_signal_reset_blocks_consecutive_extension_until_disabled() -> None:
    closes = ("99", "100", "101", "100", "102", "104", "106")
    candles = tuple(
        _candle(index, close, volume="250")
        for index, close in enumerate(closes)
    )
    configuration = {
        "channel_period": 5,
        "confirmation_closes": 1,
        "volume_period": 5,
        "volume_multiplier": "0",
        "atr_period": 3,
        "minimum_breakout_atr_multiple": "0",
        "maximum_breakout_atr_multiple": "10",
        "maximum_spread_percentage": "1",
        "require_signal_reset": True,
    }
    evaluator = RangeBreakoutEvaluator()

    blocked = evaluator.evaluate(_context(candles), configuration)
    allowed = evaluator.evaluate(
        _context(candles),
        {**configuration, "require_signal_reset": False},
    )

    assert blocked.eligible is False
    assert "signal_not_reset" in blocked.reason_codes
    assert blocked.analysis["previous_breakout_direction"] == "long"
    assert allowed.eligible is True
    assert allowed.signal == "long"


def test_breakout_reentry_into_channel_resets_signal_and_allows_new_breakout() -> None:
    closes = ("99", "100", "101", "100", "102", "104", "101", "106")
    candles = tuple(
        _candle(index, close, volume="250")
        for index, close in enumerate(closes)
    )
    result = RangeBreakoutEvaluator().evaluate(
        _context(candles),
        {
            "channel_period": 5,
            "confirmation_closes": 1,
            "volume_period": 5,
            "volume_multiplier": "0",
            "atr_period": 3,
            "minimum_breakout_atr_multiple": "0",
            "maximum_breakout_atr_multiple": "10",
            "maximum_spread_percentage": "1",
            "require_signal_reset": True,
        },
    )

    assert result.eligible is True
    assert result.signal == "long"
    assert result.analysis["previous_breakout_direction"] is None
    assert "signal_not_reset" not in result.reason_codes


def test_breakout_cooldown_blocks_until_configured_candle_count_is_reached() -> None:
    prior_prices = ("99", "100", "101", "100", "102", "101")
    prior = tuple(
        _candle(index, price, volume="100")
        for index, price in enumerate(prior_prices)
    )
    confirmation = _candle(6, "104", volume="250", high="110")
    base_context = _context((*prior, confirmation))
    configuration = {
        "channel_period": 5,
        "confirmation_closes": 1,
        "volume_period": 5,
        "volume_multiplier": "1.5",
        "atr_period": 3,
        "minimum_breakout_atr_multiple": "0",
        "maximum_breakout_atr_multiple": "10",
        "maximum_spread_percentage": "1",
        "cooldown_candles": 3,
    }
    evaluator = RangeBreakoutEvaluator()

    blocked = evaluator.evaluate(
        base_context.model_copy(update={"candles_since_last_entry": 2}),
        configuration,
    )
    allowed = evaluator.evaluate(
        base_context.model_copy(update={"candles_since_last_entry": 3}),
        configuration,
    )

    assert blocked.eligible is False
    assert "cooldown_active" in blocked.reason_codes
    assert allowed.eligible is True
    assert allowed.signal == "long"


def test_range_wrapper_preserves_existing_range_calculation() -> None:
    values = (
        ("100", "101", "100", "100"),
        ("105", "110", "104", "105"),
        ("110", "122", "109", "110"),
        ("105", "106", "104", "105"),
        ("101", "102", "100.5", "101"),
    )
    normalized = tuple(
        NormalizedCandle(
            opened_at=BASE + timedelta(minutes=index),
            closed_at=BASE + timedelta(minutes=index + 1),
            open=Decimal(open_value),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("100"),
            closed=True,
        )
        for index, (open_value, high, low, close) in enumerate(values)
    )
    configuration = {
        "mode": "rolling_window",
        "timeframe_minutes": 5,
        "range_mode": "interval",
        "minimum_range_percentage": "20",
        "maximum_range_percentage": "25",
        "proximity_percentage": "3",
        "direction": "both",
    }
    context = _context(normalized, timeframe_minutes=5, last_price="101")
    wrapped = RangeStrategyEvaluator().evaluate(context, configuration)
    direct = evaluate_range(
        RangeAnalysisConfig.model_validate(configuration),
        [
            Candle(
                opened_at=candle.opened_at,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
            )
            for candle in normalized
        ],
        Decimal("101"),
        context.evaluated_at,
    )

    assert wrapped.eligible is True
    assert wrapped.signal == "long"
    assert wrapped.analysis["range_percentage"] == direct.range_percentage
    assert wrapped.analysis["long_proximity_percentage"] == (
        direct.long_proximity_percentage
    )
    assert wrapped.protective_actions_available is True


@pytest.mark.parametrize(
    ("range_mode", "direction", "last_price", "expected_signal"),
    (
        ("interval", "both", "100", "long"),
        ("exact", "long_only", "100", "long"),
        ("interval", "both", "120", "short"),
        ("exact", "short_only", "120", "short"),
        ("interval", "short_only", "100", "none"),
        ("interval", "long_only", "120", "none"),
    ),
)
def test_range_wrapper_matches_direct_direction_and_range_rules(
    range_mode: str,
    direction: str,
    last_price: str,
    expected_signal: str,
) -> None:
    normalized = tuple(
        NormalizedCandle(
            opened_at=BASE + timedelta(minutes=index),
            closed_at=BASE + timedelta(minutes=index + 1),
            open=Decimal("100"),
            high=Decimal("120"),
            low=Decimal("100"),
            close=Decimal("110"),
            volume=Decimal("100"),
            closed=True,
        )
        for index in range(5)
    )
    configuration = {
        "mode": "rolling_window",
        "timeframe_minutes": 5,
        "range_mode": range_mode,
        "target_range_percentage": "20",
        "tolerance_percentage_points": "0",
        "minimum_range_percentage": "20",
        "maximum_range_percentage": "25",
        "proximity_percentage": "3",
        "direction": direction,
    }
    context = _context(normalized, timeframe_minutes=5, last_price=last_price)

    wrapped = RangeStrategyEvaluator().evaluate(context, configuration)
    direct = evaluate_range(
        RangeAnalysisConfig.model_validate(configuration),
        [
            Candle(
                opened_at=candle.opened_at,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
            )
            for candle in normalized
        ],
        Decimal(last_price),
        context.evaluated_at,
    )

    direct_signal = (
        "long" if direct.long_eligible else "short" if direct.short_eligible else "none"
    )
    assert wrapped.signal == expected_signal == direct_signal
    assert wrapped.analysis["range_percentage"] == direct.range_percentage
    assert wrapped.analysis["long_eligible"] == direct.long_eligible
    assert wrapped.analysis["short_eligible"] == direct.short_eligible


def test_range_wrapper_preserves_current_gate_candle_mode() -> None:
    forming = NormalizedCandle(
        opened_at=BASE,
        closed_at=BASE + timedelta(minutes=5),
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("100"),
        close=Decimal("110"),
        volume=Decimal("100"),
        closed=False,
    )
    evaluated_at = BASE + timedelta(minutes=2)
    context = StrategyEvaluationContext(
        symbol="BTC_USDT",
        evaluated_at=evaluated_at,
        timeframe_minutes=5,
        candles=(forming,),
        last_price=Decimal("100"),
        mark_price=Decimal("100"),
        best_bid=Decimal("99.95"),
        best_ask=Decimal("100.05"),
        market_data_state="fresh",
        reconciliation_ready=True,
        emergency_stop=False,
    )
    configuration = {
        "mode": "current_gate_candle",
        "timeframe_minutes": 5,
        "range_mode": "exact",
        "target_range_percentage": "20",
        "tolerance_percentage_points": "0",
        "proximity_percentage": "3",
        "direction": "both",
    }

    wrapped = RangeStrategyEvaluator().evaluate(context, configuration)
    direct = evaluate_range(
        RangeAnalysisConfig.model_validate(configuration),
        [
            Candle(
                opened_at=forming.opened_at,
                open=forming.open,
                high=forming.high,
                low=forming.low,
                close=forming.close,
            )
        ],
        context.last_price,
        evaluated_at,
    )

    assert wrapped.signal == "long"
    assert wrapped.analysis["history_status"] == direct.history_status == "ready"
    assert wrapped.analysis["range_percentage"] == direct.range_percentage
    assert wrapped.used_closed_candles == 0


def test_range_wrapper_blocks_stale_market_data_without_disabling_protection() -> None:
    candles = tuple(
        NormalizedCandle(
            opened_at=BASE + timedelta(minutes=index),
            closed_at=BASE + timedelta(minutes=index + 1),
            open=Decimal("100"),
            high=Decimal("120"),
            low=Decimal("100"),
            close=Decimal("110"),
            volume=Decimal("100"),
            closed=True,
        )
        for index in range(5)
    )
    result = RangeStrategyEvaluator().evaluate(
        _context(
            candles,
            timeframe_minutes=5,
            last_price="100",
            market_data_state="stale",
        ),
        {
            "mode": "rolling_window",
            "timeframe_minutes": 5,
            "range_mode": "interval",
            "minimum_range_percentage": "20",
            "maximum_range_percentage": "25",
            "proximity_percentage": "3",
            "direction": "both",
        },
    )

    assert result.eligible is False
    assert result.trade_request is None
    assert "market_data_stale" in result.reason_codes
    assert result.protective_actions_available is True
