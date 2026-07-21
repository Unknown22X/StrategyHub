"""Central strategy orchestration without exchange submission side effects."""

from rangebot.domain.strategy import StrategyDecisionCreate
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
)
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_registry import StrategyRegistry


class StrategyManager:
    """Resolve registered behavior, evaluate authoritative data, and audit decisions."""

    def __init__(
        self,
        registry: StrategyRegistry,
        instances: StrategyInstanceRepository,
    ) -> None:
        self._registry = registry
        self._instances = instances

    def evaluate(
        self,
        instance_id: str,
        context: StrategyEvaluationContext,
        *,
        runtime_event_key: str | None = None,
    ) -> StrategyEvaluationResult:
        instance = self._instances.get(instance_id)
        if instance.status not in {"running", "monitoring"}:
            raise RuntimeError("Strategy evaluation requires a running or monitoring instance.")
        if context.symbol != instance.symbol:
            raise ValueError("Market context symbol does not match the strategy instance.")
        if context.timeframe_minutes != instance.timeframe_minutes:
            raise ValueError("Market context timeframe does not match the strategy instance.")

        evaluator = self._registry.evaluator(instance.type_id)
        configuration = dict(instance.configuration)
        properties = self._registry.get(instance.type_id).configuration_schema.get(
            "properties", {}
        )
        if "timeframe_minutes" in properties:
            configuration["timeframe_minutes"] = instance.timeframe_minutes
        if "direction" in properties:
            configuration["direction"] = {
                "long": "long_only",
                "short": "short_only",
                "both": "both",
            }[instance.direction]
        self._registry.validate_configuration(instance.type_id, configuration)
        result = evaluator.evaluate(context, configuration)
        self._instances.record_decision(
            instance_id,
            StrategyDecisionCreate(
                signal=result.signal,
                eligible=result.eligible,
                reason_codes=result.reason_codes,
                analysis={
                    **result.analysis,
                    "explanation_ar": result.explanation_ar,
                    "used_closed_candles": result.used_closed_candles,
                    "protective_actions_available": (
                        result.protective_actions_available
                    ),
                    "trade_request": (
                        result.trade_request.model_dump(mode="json")
                        if result.trade_request is not None
                        else None
                    ),
                    "runtime_event_key": runtime_event_key,
                },
                occurred_at=result.evaluated_at,
            ),
        )
        return result
