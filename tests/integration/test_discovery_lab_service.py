from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from rangebot.domain.backtesting import (
    BacktestRunRequest,
    BacktestSettings,
    BacktestStrategyCreateRequest,
)
from rangebot.domain.discovery import DiscoveryMarketContract
from rangebot.domain.strategy import StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.discovery_lab import DiscoveryLabService
from rangebot.engine.discovery_repository import DiscoveryResearchRepository
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_registry import StrategyRegistry


class _Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_close: Decimal = Decimal("100")
    direction: Literal["long_only", "short_only", "both"] = "both"
    timeframe_minutes: int = 1


class _Evaluator:
    type_id = "scripted_research"
    configuration_model = _Configuration

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult:
        parsed = self.configuration_model.model_validate(configuration)
        eligible = context.last_price == parsed.signal_close
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal="long" if eligible else "none",
            eligible=eligible,
            reason_codes=("scripted",),
            explanation_ar="قرار بحث حتمي.",
            used_closed_candles=len(context.completed_candles()),
            trade_request=StrategyTradeRequest(
                symbol=context.symbol,
                direction="long",
                reference_price=context.last_price,
                take_profit_price=Decimal("105"),
                stop_loss_price=Decimal("95"),
                reason_code="scripted",
            )
            if eligible
            else None,
        )


class _MarketData:
    def __init__(self, candles: tuple[NormalizedCandle, ...]) -> None:
        self._candles = candles

    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]:
        del minimum_quote_volume, maximum_contracts
        return ()

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]:
        del symbol, timeframe_minutes
        return self._candles[-limit:]

    def candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedCandle, ...]:
        del symbol, timeframe_minutes
        return tuple(
            candle
            for candle in self._candles
            if start <= candle.opened_at < end
        )


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        StrategyTypeMetadata(
            type_id="scripted_research",
            display_name_ar="بحث حتمي",
            display_name_en="Scripted Research",
            description_ar="استراتيجية اختبار البحث.",
            description_en="Research test strategy.",
            version="3.1.0",
            supported_timeframes=(1,),
            supports_backtesting=True,
            minimum_backtest_candles=2,
            configuration_schema=_Configuration.model_json_schema(),
        ),
        _Evaluator,
    )
    return registry


def _candles() -> tuple[NormalizedCandle, ...]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (
        NormalizedCandle(
            opened_at=base,
            closed_at=base + timedelta(minutes=1),
            open=Decimal("99"),
            high=Decimal("101"),
            low=Decimal("98"),
            close=Decimal("100"),
            volume=Decimal("1000"),
        ),
        NormalizedCandle(
            opened_at=base + timedelta(minutes=1),
            closed_at=base + timedelta(minutes=2),
            open=Decimal("100"),
            high=Decimal("106"),
            low=Decimal("99"),
            close=Decimal("104"),
            volume=Decimal("1000"),
        ),
    )


def _service(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    apply_migrations(database_url)
    engine = create_database_engine(database_url)
    research = DiscoveryResearchRepository(engine)
    instances = StrategyInstanceRepository(engine)
    service = DiscoveryLabService(
        _registry(),
        _MarketData(_candles()),
        research,
        instances,
    )
    return engine, service, research, instances


def _request() -> BacktestRunRequest:
    candles = _candles()
    return BacktestRunRequest(
        strategy_type_id="scripted_research",
        symbol="BTC_USDT",
        timeframe_minutes=1,
        configuration={"signal_close": "100", "direction": "both"},
        start=candles[0].opened_at,
        end=candles[-1].closed_at,
        settings=BacktestSettings(
            initial_balance=Decimal("1000"),
            margin_per_trade=Decimal("100"),
            leverage=1,
            taker_fee_rate=Decimal("0"),
            minimum_trades_for_assessment=1,
        ),
    )


def test_backtest_runs_with_registered_evaluator_and_persists_version(tmp_path) -> None:
    engine, service, _, _ = _service(tmp_path)

    stored = service.run_backtest(_request())

    assert stored.strategy_version == "3.1.0"
    assert stored.result.metrics.total_trades == 1
    assert stored.result.trades[0].entered_at == _candles()[1].opened_at
    assert stored.result.assessment.label in {"promising", "mixed"}
    engine.dispose()


def test_apply_backtest_creates_stopped_strategy_and_records_one_time_link(tmp_path) -> None:
    engine, service, research, instances = _service(tmp_path)
    stored = service.run_backtest(_request())

    instance = service.create_stopped_strategy(
        stored.backtest_id,
        BacktestStrategyCreateRequest(
            name="BTC Research Result",
            environment="paper",
            direction="both",
        ),
    )

    assert instance.status == "stopped"
    assert instance.symbol == "BTC_USDT"
    assert instance.configuration == {
        "signal_close": "100",
        "direction": "both",
    }
    assert research.get_backtest(stored.backtest_id).applied_instance_id == instance.instance_id
    assert instances.get(instance.instance_id).status == "stopped"

    try:
        service.create_stopped_strategy(
            stored.backtest_id,
            BacktestStrategyCreateRequest(name="Duplicate application"),
        )
    except RuntimeError as error:
        assert "already created" in str(error)
    else:
        raise AssertionError("A backtest must not create more than one strategy.")
    engine.dispose()


def test_backtest_rejects_timeframe_that_conflicts_with_configuration(tmp_path) -> None:
    engine, service, _, _ = _service(tmp_path)
    request = _request().model_copy(
        update={
            "timeframe_minutes": 1,
            "configuration": {
                "signal_close": "100",
                "direction": "both",
                "timeframe_minutes": 5,
            },
        }
    )

    try:
        service.run_backtest(request)
    except ValueError as error:
        assert "configuration timeframe" in str(error)
    else:
        raise AssertionError("Conflicting backtest timeframes must be rejected.")
    engine.dispose()


def test_apply_backtest_rejects_direction_change_from_tested_configuration(tmp_path) -> None:
    engine, service, _, instances = _service(tmp_path)
    stored = service.run_backtest(_request())

    try:
        service.create_stopped_strategy(
            stored.backtest_id,
            BacktestStrategyCreateRequest(
                name="Wrong direction",
                direction="long_only",
            ),
        )
    except ValueError as error:
        assert "direction used by the backtest" in str(error)
    else:
        raise AssertionError("Applying a different direction must be rejected.")

    assert instances.list() == []
    engine.dispose()
