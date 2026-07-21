import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from rangebot.domain.strategy import StrategyInstance
from rangebot.domain.strategy_workflow import (
    EntryExecutionSettings,
    StrategyExecutionPlan,
)
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.strategy_runtime_runner import StrategyRuntimeRunner


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _instance(status: str = "running") -> StrategyInstance:
    return StrategyInstance(
        type_id="test_strategy",
        template_id="builtin:test_strategy",
        template_version="test",
        name="Test strategy",
        environment="paper",
        symbol="BTC_USDT",
        timeframe_minutes=15,
        direction="both",
        requested_margin=Decimal("25"),
        requested_leverage=5,
        configuration={},
        instance_id="instance-1",
        status=status,
        created_at=NOW,
        updated_at=NOW,
        revision=1,
    )


def _context(evaluated_at: datetime = NOW) -> StrategyEvaluationContext:
    candle = NormalizedCandle(
        opened_at=evaluated_at - timedelta(minutes=15),
        closed_at=evaluated_at,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("1000"),
    )
    return StrategyEvaluationContext(
        symbol="BTC_USDT",
        evaluated_at=evaluated_at,
        timeframe_minutes=15,
        candles=(candle,),
        last_price=Decimal("101"),
        mark_price=Decimal("101"),
        best_bid=Decimal("100.9"),
        best_ask=Decimal("101.1"),
    )


class Repository:
    def __init__(self, instance: StrategyInstance) -> None:
        self.instance = instance
        self.run_instance = instance
        self.run_extensions = {}
        self.blocks = []

    def list(self):
        return [self.instance]

    def active_run(self, instance_id):
        assert instance_id == self.instance.instance_id
        return SimpleNamespace(
            run_id="run-1",
            configuration_snapshot={
                "schema_version": 1,
                "instance": self.run_instance.model_dump(mode="json"),
                **self.run_extensions,
            },
        )

    def decisions(self, instance_id, limit=100):
        assert instance_id == self.instance.instance_id
        return list(reversed(self.blocks))[:limit]

    def record_decision(self, instance_id, change):
        assert instance_id == self.instance.instance_id
        self.blocks.append(change)


class Registry:
    def __init__(self, cadence: str) -> None:
        self.cadence = cadence

    def get(self, type_id):
        assert type_id == "test_strategy"
        return SimpleNamespace(evaluation_cadence=self.cadence)


class MarketData:
    def __init__(self, context: StrategyEvaluationContext) -> None:
        self.context = context

    def strategy_context(self, symbol, timeframe_minutes):
        assert symbol == "BTC_USDT"
        assert timeframe_minutes == 15
        return self.context


class StrategyManager:
    def __init__(self, result: StrategyEvaluationResult) -> None:
        self.result = result
        self.calls = 0
        self.runtime_event_keys = []

    def evaluate(
        self,
        instance_id,
        context,
        *,
        runtime_event_key=None,
        instance_snapshot=None,
    ):
        self.calls += 1
        self.runtime_event_keys.append(runtime_event_key)
        self.instance_snapshot = instance_snapshot
        return self.result


class OrderManager:
    def __init__(self) -> None:
        self.calls = []

    def submit_automatic(self, request, **context):
        self.calls.append((request, context))
        return SimpleNamespace(accepted=True)


def _evaluation(*, trailing: bool = False) -> StrategyEvaluationResult:
    return StrategyEvaluationResult(
        type_id="test_strategy",
        symbol="BTC_USDT",
        evaluated_at=NOW,
        signal="long",
        eligible=True,
        reason_codes=("eligible",),
        explanation_ar="eligible",
        used_closed_candles=1,
        trade_request=StrategyTradeRequest(
            symbol="BTC_USDT",
            direction="long",
            reference_price=Decimal("101"),
            take_profit_price=Decimal("105"),
            stop_loss_price=Decimal("98"),
            trailing_stop_price=Decimal("99") if trailing else None,
            reason_code="eligible",
        ),
    )


def _runner(instance, *, cadence="closed_candle", evaluation=None, execution_plan=None):
    repository = Repository(instance)
    manager = StrategyManager(evaluation or _evaluation())
    orders = OrderManager()
    runner = StrategyRuntimeRunner(
        instance_repository=repository,
        strategy_registry=Registry(cadence),
        strategy_manager=manager,
        market_data_manager=MarketData(_context()),
        order_manager=orders,
        execution_plan_resolver=(
            (lambda _instance: execution_plan) if execution_plan is not None else None
        ),
    )
    return runner, repository, manager, orders


def test_monitoring_evaluates_once_per_closed_candle_without_order_submission() -> None:
    runner, _, manager, orders = _runner(_instance("monitoring"))

    first = asyncio.run(runner.run_once())
    duplicate = asyncio.run(runner.run_once())

    assert first[0].evaluated is True
    assert first[0].reason == "monitoring_only"
    assert duplicate[0].reason == "duplicate_market_event"
    assert manager.calls == 1
    assert orders.calls == []


def test_running_strategy_submits_protected_intent_through_central_order_manager() -> (
    None
):
    runner, _, manager, orders = _runner(_instance("running"))

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.submitted is True
    request, context = orders.calls[0]
    assert request.size_mode == "margin"
    assert request.margin_amount == Decimal("25")
    assert request.leverage == 5
    assert context["instance_id"] == "instance-1"
    assert context["run_id"] == "run-1"
    assert manager.runtime_event_keys == [
        f"candle:{(NOW - timedelta(minutes=15)).isoformat()}"
    ]
    assert context["take_profit_price"] == Decimal("105")
    assert context["stop_loss_price"] == Decimal("98")


def test_approved_execution_plan_controls_limit_entry_submission() -> None:
    plan = StrategyExecutionPlan(
        entry=EntryExecutionSettings(
            order_type="limit",
            limit_price_formula="last-1%",
            time_in_force="gtc",
            expires_after_minutes=5,
            partial_fill_behavior="require_full_fill",
        )
    )
    runner, _, _, orders = _runner(_instance("running"), execution_plan=plan)

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.submitted is True
    request, _ = orders.calls[0]
    assert request.order_type == "limit"
    assert request.limit_price == Decimal("99.99")
    assert request.time_in_force == "fok"
    assert request.expires_at == NOW + timedelta(minutes=5)


def test_stored_run_execution_plan_overrides_mutable_resolver() -> None:
    stored_plan = StrategyExecutionPlan(
        entry=EntryExecutionSettings(
            order_type="limit",
            limit_price_formula="last-2%",
            time_in_force="gtc",
            expires_after_minutes=3,
        )
    )
    mutable_plan = StrategyExecutionPlan()
    runner, repository, _, orders = _runner(
        _instance("running"), execution_plan=mutable_plan
    )
    repository.run_extensions["execution_plan"] = stored_plan.model_dump(mode="json")

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.submitted is True
    request, _ = orders.calls[0]
    assert request.order_type == "limit"
    assert request.limit_price == Decimal("98.98")
    assert request.expires_at == NOW + timedelta(minutes=3)


def test_trailing_stop_intent_is_submitted_with_exact_initial_stop() -> None:
    runner, repository, _, orders = _runner(
        _instance("running"), evaluation=_evaluation(trailing=True)
    )

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.submitted is True
    assert outcome.reason == "order_submitted"
    assert repository.blocks == []
    _, context = orders.calls[0]
    assert context["trailing_stop_price"] == Decimal("99")


def test_persisted_runtime_event_prevents_same_candle_replay_after_restart() -> None:
    runner, repository, manager, orders = _runner(_instance("running"))
    event_key = f"candle:{(NOW - timedelta(minutes=15)).isoformat()}"
    repository.blocks.append(SimpleNamespace(analysis={"runtime_event_key": event_key}))

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.reason == "duplicate_market_event"
    assert outcome.evaluated is False
    assert manager.calls == 0
    assert orders.calls == []


def test_market_update_cadence_evaluates_only_when_observed_timestamp_changes() -> None:
    runner, _, manager, _ = _runner(_instance("monitoring"), cadence="market_update")

    asyncio.run(runner.run_once())
    asyncio.run(runner.run_once())
    runner._market_data.context = _context(NOW + timedelta(seconds=1))
    asyncio.run(runner.run_once())

    assert manager.calls == 2


def test_runtime_uses_stored_run_snapshot_for_signal_and_order_sizing() -> None:
    runner, repository, manager, orders = _runner(_instance("running"))
    repository.instance = repository.instance.model_copy(
        update={
            "requested_margin": Decimal("99"),
            "requested_leverage": 10,
            "configuration": {"mutated": True},
        }
    )

    outcome = asyncio.run(runner.run_once())[0]

    assert outcome.submitted is True
    request, _ = orders.calls[0]
    assert request.margin_amount == Decimal("25")
    assert request.leverage == 5
    assert manager.instance_snapshot.requested_margin == Decimal("25")
    assert manager.instance_snapshot.requested_leverage == 5
    assert manager.instance_snapshot.configuration == {}


def test_context_failure_is_audited_once_until_the_runtime_recovers() -> None:
    runner, repository, manager, orders = _runner(_instance("running"))

    class UnavailableMarketData:
        def strategy_context(self, *_args, **_kwargs):
            raise LookupError("market data unavailable")

    runner._market_data = UnavailableMarketData()
    first = asyncio.run(runner.run_once())[0]
    duplicate = asyncio.run(runner.run_once())[0]

    assert first.reason == "context_unavailable:LookupError"
    assert duplicate.reason == "context_unavailable:LookupError"
    assert manager.calls == 0
    assert orders.calls == []
    assert len(repository.blocks) == 1
    assert repository.blocks[0].signal == "runtime_waiting"
    assert repository.blocks[0].reason_codes == ("context_unavailable:LookupError",)

    runner._market_data = MarketData(_context(NOW + timedelta(seconds=1)))
    recovered = asyncio.run(runner.run_once())[0]

    assert recovered.submitted is True
    assert manager.calls == 1
