from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.backtesting import BacktestSettings, BacktestSpec
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.backtesting import BacktestEngine
from rangebot.engine.strategy_registry import StrategyRegistry
from rangebot.domain.strategy import StrategyTypeMetadata


class _ScriptedEvaluator:
    type_id = "scripted"
    configuration_model = type(
        "ConfigurationModel",
        (),
        {"model_validate": staticmethod(lambda value: value)},
    )

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, object],
    ) -> StrategyEvaluationResult:
        signal_close = Decimal(str(configuration.get("signal_close", "100")))
        eligible = context.last_price == signal_close
        request = None
        if eligible:
            request = StrategyTradeRequest(
                symbol=context.symbol,
                direction="long",
                reference_price=context.last_price,
                take_profit_price=Decimal("105"),
                stop_loss_price=Decimal("95"),
                reason_code="scripted_signal",
            )
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal="long" if eligible else "none",
            eligible=eligible,
            reason_codes=("scripted",),
            explanation_ar="اختبار حتمي",
            used_closed_candles=len(context.completed_candles()),
            trade_request=request,
        )


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        StrategyTypeMetadata(
            type_id="scripted",
            display_name_ar="اختبار",
            display_name_en="Scripted",
            description_ar="استراتيجية اختبار",
            description_en="Test strategy",
            version="1",
            configuration_schema={},
        ),
        _ScriptedEvaluator,
    )
    return registry


def _candle(
    base: datetime,
    index: int,
    *,
    open_: str,
    high: str,
    low: str,
    close: str,
) -> NormalizedCandle:
    opened = base + timedelta(minutes=index)
    return NormalizedCandle(
        opened_at=opened,
        closed_at=opened + timedelta(minutes=1),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        closed=True,
    )


def _spec(**settings: object) -> BacktestSpec:
    setting_values: dict[str, object] = {
        "initial_balance": Decimal("1000"),
        "margin_per_trade": Decimal("100"),
        "leverage": 1,
        "taker_fee_rate": Decimal("0"),
        "slippage_basis_points": Decimal("0"),
        "minimum_trades_for_assessment": 1,
    }
    setting_values.update(settings)
    return BacktestSpec(
        strategy_type_id="scripted",
        symbol="BTC_USDT",
        timeframe_minutes=1,
        configuration={"signal_close": "100"},
        settings=BacktestSettings.model_validate(setting_values),
    )


def test_signal_fills_on_next_candle_and_take_profit_is_net_result() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles = (
        _candle(base, 0, open_="99", high="101", low="98", close="100"),
        _candle(base, 1, open_="100", high="106", low="99", close="104"),
    )

    result = BacktestEngine(_registry()).run(_spec(), candles)

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.signal_at == candles[0].closed_at
    assert trade.entered_at == candles[1].opened_at
    assert trade.entry_price == Decimal("100")
    assert trade.exit_price == Decimal("105")
    assert trade.exit_reason == "take_profit"
    assert trade.net_pnl == Decimal("5")
    assert result.metrics.ending_balance == Decimal("1005")
    assert result.metrics.return_percentage == Decimal("0.5")


def test_same_candle_stop_and_target_uses_conservative_stop_first() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles = (
        _candle(base, 0, open_="99", high="101", low="98", close="100"),
        _candle(base, 1, open_="100", high="106", low="94", close="101"),
    )

    result = BacktestEngine(_registry()).run(_spec(), candles)

    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == Decimal("95")
    assert trade.net_pnl == Decimal("-5")
    assert result.metrics.maximum_drawdown_percentage == Decimal("0.5")
    assert result.assessment.label == "weak"


def test_fees_and_adverse_slippage_are_included_in_net_results() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles = (
        _candle(base, 0, open_="99", high="101", low="98", close="100"),
        _candle(base, 1, open_="100", high="110", low="99", close="106"),
    )
    spec = BacktestSpec(
        strategy_type_id="scripted",
        symbol="BTC_USDT",
        timeframe_minutes=1,
        configuration={"signal_close": "100"},
        settings=BacktestSettings(
            initial_balance=Decimal("1000"),
            margin_per_trade=Decimal("100"),
            leverage=1,
            taker_fee_rate=Decimal("0.001"),
            slippage_basis_points=Decimal("10"),
            minimum_trades_for_assessment=1,
        ),
    )

    result = BacktestEngine(_registry()).run(spec, candles)

    trade = result.trades[0]
    assert trade.entry_price == Decimal("100.100")
    assert trade.exit_price == Decimal("104.895")
    scale = Decimal("0.000000000001")
    assert trade.fees.quantize(scale) == Decimal("0.204790209790")
    assert trade.net_pnl.quantize(scale) == Decimal("4.585419580420")
    assert result.metrics.net_profit.quantize(scale) == trade.net_pnl.quantize(scale)


def test_too_few_trades_returns_insufficient_data_assessment() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    candles = (
        _candle(base, 0, open_="99", high="101", low="98", close="100"),
        _candle(base, 1, open_="100", high="106", low="99", close="104"),
    )
    spec = _spec(minimum_trades_for_assessment=5)

    result = BacktestEngine(_registry()).run(spec, candles)

    assert result.metrics.total_trades == 1
    assert result.assessment.label == "insufficient_data"
    assert "عدد الصفقات أقل من الحد المطلوب للتقييم." in result.assessment.warnings
