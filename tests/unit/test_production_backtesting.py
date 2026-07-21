from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.backtesting import (
    BacktestExecutionSettings,
    BacktestPortfolioRequest,
    BacktestSettings,
)
from rangebot.domain.discovery import StrategyScanCandidate
from rangebot.domain.orders import FuturesContractRules
from rangebot.domain.strategy import StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.backtesting import BacktestEngine
from rangebot.engine.strategy_registry import StrategyRegistry


class _Configuration:
    @staticmethod
    def model_validate(value):
        return value


class _Evaluator:
    type_id = "production_test"
    configuration_model = _Configuration

    def evaluate(self, context: StrategyEvaluationContext, configuration):
        signal_at = Decimal(str(configuration.get("signal_at", "100")))
        eligible = context.last_price == signal_at
        direction = str(configuration.get("direction", "long"))
        request = None
        if eligible:
            take_profit_value = configuration.get("take_profit", "110")
            stop_loss_value = configuration.get("stop_loss", "90")
            request = StrategyTradeRequest(
                symbol=context.symbol,
                direction=direction,
                order_type=str(configuration.get("order_type", "market")),
                reference_price=Decimal(str(configuration.get("limit_price", context.last_price))),
                take_profit_price=(
                    Decimal(str(take_profit_value)) if take_profit_value is not None else None
                ),
                stop_loss_price=(
                    Decimal(str(stop_loss_value)) if stop_loss_value is not None else None
                ),
                reason_code="fixture_signal",
            )
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal=direction if eligible else "none",
            eligible=eligible,
            reason_codes=("fixture_signal",) if eligible else ("waiting",),
            explanation_ar="إشارة حتمية" if eligible else "لا توجد إشارة",
            used_closed_candles=len(context.completed_candles()),
            trade_request=request,
        )


class _Scanner:
    type_id = "production_test"

    def scan_candidate(
        self, context: StrategyEvaluationContext, configuration, *, minimum_backtest_candles: int
    ) -> StrategyScanCandidate:
        del configuration, minimum_backtest_candles
        return StrategyScanCandidate(
            symbol=context.symbol,
            current_price=context.last_price,
            price_observed_at=context.evaluated_at,
            score=90,
            signal="long",
            eligible_now=True,
            evaluated_at=context.evaluated_at,
            market_data_state="fresh",
            explanation_ar="مرشح حتمي",
            reason_codes=("fixture_scan",),
            completed_candles=len(context.completed_candles()),
            backtest_ready=True,
        )


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        StrategyTypeMetadata(
            type_id="production_test",
            display_name_ar="اختبار",
            display_name_en="Test",
            description_ar="اختبار",
            description_en="Test",
            version="1",
            supported_timeframes=(60,),
            supports_scanning=True,
            supports_backtesting=True,
            configuration_schema={},
        ),
        _Evaluator,
        _Scanner,
    )
    return registry


def _candle(index: int, open_: str, high: str, low: str, close: str) -> NormalizedCandle:
    opened = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=index)
    return NormalizedCandle(
        opened_at=opened,
        closed_at=opened + timedelta(hours=1),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("10000"),
        closed=True,
    )


def _request(**updates) -> BacktestPortfolioRequest:
    values = {
        "mode": "manual_symbols",
        "strategy_type_id": "production_test",
        "strategy_version": "1",
        "symbols": ("BTC_USDT",),
        "timeframe_minutes": 60,
        "configuration": {"signal_at": "100"},
        "start": datetime(2026, 1, 1, tzinfo=UTC),
        "end": datetime(2026, 1, 3, tzinfo=UTC),
        "settings": BacktestSettings(
            initial_balance=Decimal("1000"),
            margin_per_trade=Decimal("100"),
            leverage=1,
            maker_fee_rate=Decimal("0"),
            taker_fee_rate=Decimal("0"),
            minimum_trades_for_assessment=1,
        ),
    }
    values.update(updates)
    return BacktestPortfolioRequest.model_validate(values)


def _rules(symbol: str = "BTC_USDT") -> FuturesContractRules:
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("1"),
        quantity_step=Decimal("0.01"),
        minimum_quantity=Decimal("0.01"),
        price_step=Decimal("0.1"),
        maximum_leverage=100,
    )


def test_closed_candle_signal_fills_only_at_next_open_and_is_repeatable() -> None:
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "120", "80", "100"),
            _candle(1, "101", "109", "100", "105"),
            _candle(2, "106", "111", "105", "110"),
        )
    }
    engine = BacktestEngine(_registry())

    first = engine.run_portfolio(_request(), candles, {"BTC_USDT": _rules()})
    second = engine.run_portfolio(_request(), candles, {"BTC_USDT": _rules()})

    assert first == second
    assert first.trades[0].signal_at == candles["BTC_USDT"][0].closed_at
    assert first.trades[0].entered_at == candles["BTC_USDT"][1].opened_at
    assert first.orders[0].submitted_at == candles["BTC_USDT"][0].closed_at
    assert first.fills[0].filled_at == candles["BTC_USDT"][1].opened_at


def test_limit_order_waits_for_later_candle_and_expires() -> None:
    request = _request(
        configuration={"signal_at": "100", "order_type": "limit", "limit_price": "95"},
        execution=BacktestExecutionSettings(entry_expiration_candles=1),
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "101", "102", "99", "101"),
            _candle(2, "100", "101", "94", "96"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(request, candles, {"BTC_USDT": _rules()})

    assert result.trades == ()
    assert result.orders[0].status == "expired"
    assert result.metrics.total_trades == 0
    assert result.metrics.profit_factor is None


def test_gap_stop_and_ambiguity_policies_are_explicit() -> None:
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "105", "95", "103"),
            _candle(2, "85", "115", "80", "100"),
        )
    }
    conservative = BacktestEngine(_registry()).run_portfolio(
        _request(), candles, {"BTC_USDT": _rules()}
    )
    ambiguous_candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "105", "95", "103"),
            _candle(2, "100", "115", "80", "100"),
        )
    }
    optimistic = BacktestEngine(_registry()).run_portfolio(
        _request(settings=_request().settings.model_copy(update={"ambiguity_policy": "optimistic"})),
        ambiguous_candles,
        {"BTC_USDT": _rules()},
    )

    assert conservative.trades[0].exit_reason == "stop_loss"
    assert conservative.trades[0].exit_price == Decimal("85")
    assert conservative.trades[0].ambiguous is True
    assert optimistic.trades[0].exit_reason == "take_profit"
    assert optimistic.metrics.ambiguous_trades == 1


def test_fees_slippage_rounding_and_minimum_notional_are_applied() -> None:
    settings = _request().settings.model_copy(
        update={
            "taker_fee_rate": Decimal("0.001"),
            "slippage_basis_points": Decimal("10"),
            "spread_basis_points": Decimal("20"),
        }
    )
    candles = {"BTC_USDT": (_candle(0, "99", "101", "98", "100"), _candle(1, "100", "111", "99", "110"))}
    result = BacktestEngine(_registry()).run_portfolio(
        _request(settings=settings), candles, {"BTC_USDT": _rules()}
    )

    assert result.fills[0].price == Decimal("100.2")
    assert result.fills[0].filled_at == candles["BTC_USDT"][1].opened_at
    assert result.fills[0].quantity == Decimal("0.99")
    assert result.metrics.total_fees > 0
    assert result.metrics.total_slippage > 0

    rejecting_rules = _rules().model_copy(update={"minimum_quantity": Decimal("2")})
    rejected = BacktestEngine(_registry()).run_portfolio(
        _request(), candles, {"BTC_USDT": rejecting_rules}
    )
    assert rejected.orders[0].status == "rejected"
    assert rejected.orders[0].rejection_reason == "minimum_quantity"


def test_contract_multiplier_controls_sizing_and_mark_to_market() -> None:
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "111", "99", "110"),
        )
    }
    rules = _rules().model_copy(
        update={"contract_multiplier": Decimal("0.1"), "quantity_step": Decimal("1")}
    )

    result = BacktestEngine(_registry()).run_portfolio(
        _request(), candles, {"BTC_USDT": rules}
    )

    assert result.fills[0].quantity == Decimal("10")
    assert result.trades[0].gross_pnl == Decimal("10.0")


def test_candle_closing_after_requested_end_cannot_affect_run() -> None:
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "101", "99", "100"),
            _candle(2, "100", "150", "50", "120"),
        )
    }
    request = _request(end=datetime(2026, 1, 1, 2, tzinfo=UTC))

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {"BTC_USDT": _rules()}
    )

    assert result.ended_at == candles["BTC_USDT"][1].closed_at
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.trades[0].exit_price == Decimal("100")


def test_intrabar_limit_fill_cannot_reuse_earlier_same_candle_range_for_exit() -> None:
    request = _request(
        configuration={
            "signal_at": "100", "order_type": "limit", "limit_price": "95",
            "take_profit": "110", "stop_loss": "90",
        }
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "120", "94", "100"),
            _candle(2, "100", "111", "99", "110"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {"BTC_USDT": _rules()}
    )

    assert result.trades[0].entered_at == candles["BTC_USDT"][1].closed_at
    assert result.trades[0].exited_at == candles["BTC_USDT"][2].closed_at


def test_gap_stop_cancels_dca_before_it_can_average_down() -> None:
    request = _request(
        execution=BacktestExecutionSettings(
            dca_enabled=True,
            dca_spacing_percentage=Decimal("10"),
            dca_allocations=(Decimal("50"), Decimal("50")),
        )
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "101", "99", "100"),
            _candle(2, "80", "85", "75", "80"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {"BTC_USDT": _rules()}
    )

    assert result.trades[0].exit_price == Decimal("80")
    assert len(result.trades[0].entry_fills) == 1
    assert next(order for order in result.orders if order.role == "dca").status == "canceled"


def test_fallback_percentage_target_recalculates_after_dca() -> None:
    request = _request(
        configuration={"signal_at": "100", "take_profit": None, "stop_loss": "80"},
        execution=BacktestExecutionSettings(
            dca_enabled=True,
            dca_spacing_percentage=Decimal("10"),
            dca_allocations=(Decimal("50"), Decimal("50")),
        ),
        settings=_request().settings.model_copy(
            update={"default_take_profit_percentage": Decimal("10")}
        ),
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "101", "99", "100"),
            _candle(2, "95", "96", "89", "90"),
            _candle(3, "96", "106", "95", "105"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {"BTC_USDT": _rules()}
    )

    trade = result.trades[0]
    assert trade.take_profit_price.quantize(Decimal("0.00000001")) == (
        trade.average_entry_price * Decimal("1.10")
    ).quantize(Decimal("0.00000001"))


def test_lower_timeframe_policy_resolves_target_before_later_stop() -> None:
    request = _request(
        additional_timeframes=(15,),
        settings=_request().settings.model_copy(
            update={"ambiguity_policy": "lower_timeframe"}
        ),
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "105", "95", "103"),
            _candle(2, "100", "115", "85", "100"),
        )
    }
    start = candles["BTC_USDT"][2].opened_at
    lower = (
        NormalizedCandle(
            opened_at=start, closed_at=start + timedelta(minutes=15),
            open=Decimal("100"), high=Decimal("111"), low=Decimal("99"),
            close=Decimal("110"), volume=Decimal("100"), closed=True,
        ),
        NormalizedCandle(
            opened_at=start + timedelta(minutes=15),
            closed_at=start + timedelta(minutes=30),
            open=Decimal("110"), high=Decimal("111"), low=Decimal("89"),
            close=Decimal("90"), volume=Decimal("100"), closed=True,
        ),
    )

    result = BacktestEngine(_registry()).run_portfolio(
        request,
        candles,
        {"BTC_USDT": _rules()},
        {"BTC_USDT": {15: lower}},
    )

    assert result.trades[0].exit_reason == "take_profit"
    assert result.trades[0].ambiguous is False


def test_percentage_available_sizing_accounts_for_pending_reservations() -> None:
    candles = {
        symbol: (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "105", "95", "101"),
        )
        for symbol in ("AAA_USDT", "BBB_USDT")
    }
    settings = _request().settings.model_copy(
        update={
            "maximum_positions": 2,
            "position_sizing_mode": "percentage_available",
            "position_size_percentage": Decimal("60"),
        }
    )
    request = _request(
        mode="historical_scanner",
        scanner_version="1",
        symbols=("AAA_USDT", "BBB_USDT"),
        settings=settings,
    )

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {symbol: _rules(symbol) for symbol in candles}
    )

    assert [trade.allocated_margin for trade in result.trades] == [
        Decimal("600.00"), Decimal("240.00")
    ]


def test_volume_participation_limit_rejects_complete_fill() -> None:
    settings = _request().settings.model_copy(
        update={"maximum_volume_participation_percentage": Decimal("0.001")}
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "111", "99", "110"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(
        _request(settings=settings), candles, {"BTC_USDT": _rules()}
    )

    assert result.orders[0].status == "rejected"
    assert result.orders[0].rejection_reason == "maximum_volume_participation"


def test_scanner_candidates_rank_deterministically_and_record_rejections() -> None:
    candles = {
        "AAA_USDT": (_candle(0, "99", "101", "98", "100"), _candle(1, "100", "111", "99", "110")),
        "BBB_USDT": (_candle(0, "99", "101", "98", "100"), _candle(1, "100", "111", "99", "110")),
    }
    request = _request(
        mode="historical_scanner",
        symbols=("BBB_USDT", "AAA_USDT"),
        settings=_request().settings.model_copy(update={"maximum_positions": 1}),
    )
    rules = {symbol: _rules(symbol) for symbol in candles}

    result = BacktestEngine(_registry()).run_portfolio(request, candles, rules)

    selected = [item for item in result.candidates if item.selected]
    rejected = [item for item in result.candidates if item.qualified and not item.selected]
    assert selected[0].symbol == "AAA_USDT"
    assert rejected[0].symbol == "BBB_USDT"
    assert rejected[0].rejection_reason == "maximum_open_positions"


def test_dca_updates_weighted_average_and_recalculates_percentage_target() -> None:
    execution = BacktestExecutionSettings(
        dca_enabled=True,
        dca_spacing_percentage=Decimal("10"),
        dca_allocations=(Decimal("50"), Decimal("50")),
        take_profit_percentage=Decimal("10"),
        recalculate_target_after_dca=True,
    )
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "101", "99", "100"),
            _candle(2, "95", "96", "89", "90"),
            _candle(3, "96", "106", "95", "105"),
        )
    }

    result = BacktestEngine(_registry()).run_portfolio(
        _request(execution=execution), candles, {"BTC_USDT": _rules()}
    )

    trade = result.trades[0]
    assert len(trade.entry_fills) == 2
    assert trade.average_entry_price.quantize(Decimal("0.00000001")) == Decimal("94.76190476")
    assert trade.take_profit_price.quantize(Decimal("0.00000001")) == Decimal("104.23809524")


def test_higher_timeframe_context_exposes_only_candles_closed_as_of_decision() -> None:
    decision_candle = _candle(1, "100", "101", "99", "100")
    completed = NormalizedCandle(
        opened_at=datetime(2025, 12, 31, 20, tzinfo=UTC),
        closed_at=datetime(2026, 1, 1, 0, tzinfo=UTC),
        open=Decimal("90"), high=Decimal("101"), low=Decimal("89"),
        close=Decimal("100"), volume=Decimal("100"), closed=True,
    )
    future = completed.model_copy(update={
        "opened_at": datetime(2026, 1, 1, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 1, 1, 4, tzinfo=UTC),
    })
    context = StrategyEvaluationContext(
        symbol="BTC_USDT", evaluated_at=decision_candle.closed_at,
        timeframe_minutes=60, candles=(decision_candle,), last_price=Decimal("100"),
        higher_timeframe_candles={240: (completed, future)},
    )

    assert context.completed_higher_timeframe(240) == (completed,)


def test_time_exit_decision_executes_at_following_candle_open() -> None:
    candles = {
        "BTC_USDT": (
            _candle(0, "99", "101", "98", "100"),
            _candle(1, "100", "105", "95", "103"),
            _candle(2, "104", "105", "100", "102"),
        )
    }
    request = _request(
        configuration={
            "signal_at": "100", "take_profit": "150", "stop_loss": "50"
        },
        execution=BacktestExecutionSettings(time_exit_candles=1),
    )

    result = BacktestEngine(_registry()).run_portfolio(
        request, candles, {"BTC_USDT": _rules()}
    )

    assert result.trades[0].exit_reason == "time_exit"
    assert result.trades[0].exited_at == candles["BTC_USDT"][2].opened_at
    assert result.trades[0].exit_price == Decimal("104")
