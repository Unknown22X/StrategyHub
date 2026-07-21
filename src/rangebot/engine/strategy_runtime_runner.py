"""Background evaluation loop for running and monitoring strategy instances."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import re
from typing import Callable

from rangebot.domain.orders import ManualOrderPreviewRequest
from rangebot.domain.strategy import (
    StrategyDecisionCreate,
    StrategyInstance,
    StrategyRun,
)
from rangebot.domain.strategy_workflow import (
    EntryExecutionSettings,
    StrategyExecutionPlan,
)
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
)
from rangebot.engine.order_manager import OrderValidationError


@dataclass(frozen=True)
class StrategyRuntimeOutcome:
    instance_id: str
    status: str
    event_key: str | None
    evaluated: bool
    submitted: bool
    reason: str | None = None


class StrategyRuntimeRunner:
    """Evaluate persisted active instances without granting strategies order authority."""

    def __init__(
        self,
        *,
        instance_repository,
        strategy_registry,
        strategy_manager,
        market_data_manager,
        order_manager,
        context_builder: Callable[[StrategyInstance], StrategyEvaluationContext]
        | None = None,
        execution_plan_resolver: Callable[
            [StrategyInstance], StrategyExecutionPlan | None
        ]
        | None = None,
        poll_interval_seconds: float = 1.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("Strategy runtime poll interval must be positive.")
        self._instances = instance_repository
        self._registry = strategy_registry
        self._strategy_manager = strategy_manager
        self._market_data = market_data_manager
        self._order_manager = order_manager
        self._context_builder = context_builder
        self._execution_plan_resolver = execution_plan_resolver
        self._poll_interval = poll_interval_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_event: dict[str, str] = {}
        self._last_runtime_error: dict[str, str] = {}

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval)
            except TimeoutError:
                continue

    async def run_once(self) -> tuple[StrategyRuntimeOutcome, ...]:
        outcomes: list[StrategyRuntimeOutcome] = []
        for instance in self._instances.list():
            if instance.status not in {"running", "monitoring"}:
                continue
            outcomes.append(await self._evaluate_instance(instance))
        return tuple(outcomes)

    async def _evaluate_instance(
        self, instance: StrategyInstance
    ) -> StrategyRuntimeOutcome:
        try:
            active_run = self._instances.active_run(instance.instance_id)
            runtime_instance = self._instance_from_run_snapshot(instance, active_run)
            descriptor = self._registry.get(runtime_instance.type_id)
            context = self._build_context(runtime_instance)
            event_key = self._event_key(descriptor.metadata.evaluation_cadence, context)
        except Exception as error:
            reason = f"context_unavailable:{type(error).__name__}"
            self._record_runtime_error_once(instance, reason)
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=None,
                evaluated=False,
                submitted=False,
                reason=reason,
            )
        self._last_runtime_error.pop(instance.instance_id, None)
        if self._last_event.get(
            instance.instance_id
        ) == event_key or self._persisted_event_seen(instance.instance_id, event_key):
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=event_key,
                evaluated=False,
                submitted=False,
                reason="duplicate_market_event",
            )
        self._last_event[instance.instance_id] = event_key

        try:
            evaluation: StrategyEvaluationResult = self._strategy_manager.evaluate(
                instance.instance_id,
                context,
                runtime_event_key=event_key,
                instance_snapshot=runtime_instance,
            )
        except Exception as error:
            reason = f"evaluation_error:{type(error).__name__}"
            self._record_runtime_error_once(instance, reason)
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=event_key,
                evaluated=False,
                submitted=False,
                reason=reason,
            )
        if instance.status == "monitoring" or evaluation.trade_request is None:
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=event_key,
                evaluated=True,
                submitted=False,
                reason="monitoring_only"
                if instance.status == "monitoring"
                else "no_trade",
            )

        trade_request = evaluation.trade_request
        try:
            execution_plan = self._execution_plan_for_run(
                active_run,
                runtime_instance,
            )
            entry = execution_plan.entry if execution_plan is not None else None
            order_type = (
                entry.order_type if entry is not None else trade_request.order_type
            )
            limit_price = (
                self._resolve_limit_price(entry, context, trade_request.reference_price)
                if order_type == "limit"
                else None
            )
            time_in_force = self._entry_time_in_force(entry, order_type)
            expires_at = (
                context.evaluated_at + timedelta(minutes=entry.expires_after_minutes)
                if order_type == "limit"
                and entry is not None
                and entry.expires_after_minutes is not None
                else None
            )
            order_request = ManualOrderPreviewRequest(
                environment=runtime_instance.environment,
                symbol=runtime_instance.symbol,
                direction=trade_request.direction,
                order_type=order_type,
                size_mode="margin",
                margin_amount=runtime_instance.requested_margin,
                leverage=runtime_instance.requested_leverage,
                limit_price=limit_price,
                time_in_force=time_in_force,
                expires_at=expires_at,
            )
            self._order_manager.submit_automatic(
                order_request,
                origin="automatic_strategy",
                instance_id=instance.instance_id,
                run_id=active_run.run_id,
                signal_zone=",".join(evaluation.reason_codes)[:200] or None,
                signal_symbol=runtime_instance.symbol,
                take_profit_price=trade_request.take_profit_price,
                stop_loss_price=trade_request.stop_loss_price,
                trailing_stop_price=trade_request.trailing_stop_price,
            )
        except OrderValidationError as error:
            reason = "order_validation:" + ",".join(
                issue.code for issue in error.issues
            )
            self._record_execution_block(
                instance,
                context.evaluated_at,
                reason,
                evaluation,
            )
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=event_key,
                evaluated=True,
                submitted=False,
                reason=reason,
            )
        except Exception as error:
            reason = f"submission_error:{type(error).__name__}"
            self._record_execution_block(
                instance,
                context.evaluated_at,
                reason,
                evaluation,
            )
            return StrategyRuntimeOutcome(
                instance_id=instance.instance_id,
                status=instance.status,
                event_key=event_key,
                evaluated=True,
                submitted=False,
                reason=reason,
            )
        return StrategyRuntimeOutcome(
            instance_id=instance.instance_id,
            status=instance.status,
            event_key=event_key,
            evaluated=True,
            submitted=True,
            reason="order_submitted",
        )

    @staticmethod
    def _instance_from_run_snapshot(
        current: StrategyInstance,
        run: StrategyRun,
    ) -> StrategyInstance:
        payload = run.configuration_snapshot.get("instance")
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Strategy Run is missing its immutable Instance snapshot."
            )
        snapshot = StrategyInstance.model_validate(payload)
        return snapshot.model_copy(update={"status": current.status})

    def _execution_plan_for_run(
        self,
        run: StrategyRun,
        instance: StrategyInstance,
    ) -> StrategyExecutionPlan | None:
        payload = run.configuration_snapshot.get("execution_plan")
        if isinstance(payload, dict):
            return StrategyExecutionPlan.model_validate(payload)
        if self._execution_plan_resolver is None:
            return None
        return self._execution_plan_resolver(instance)

    @staticmethod
    def _entry_time_in_force(
        entry: EntryExecutionSettings | None,
        order_type: str,
    ) -> str:
        if order_type == "market":
            if entry is not None and entry.partial_fill_behavior == "require_full_fill":
                return "fok"
            return "ioc"
        if entry is None:
            return "gtc"
        if entry.partial_fill_behavior == "require_full_fill":
            return "fok"
        if entry.partial_fill_behavior == "cancel_remainder":
            return "ioc"
        return entry.time_in_force

    @staticmethod
    def _resolve_limit_price(
        entry: EntryExecutionSettings | None,
        context: StrategyEvaluationContext,
        strategy_reference_price: Decimal,
    ) -> Decimal:
        if entry is None:
            return strategy_reference_price
        if entry.limit_price is not None:
            return entry.limit_price
        formula = (entry.limit_price_formula or "").strip().lower().replace(" ", "")
        references = {
            "last": context.last_price,
            "mark": context.mark_price or context.last_price,
            "best_bid": context.best_bid or context.last_price,
            "best_ask": context.best_ask or context.last_price,
            "strategy": strategy_reference_price,
        }
        if formula in references:
            return references[formula]
        match = re.fullmatch(
            r"(last|mark|best_bid|best_ask|strategy)([+-])(\d+(?:\.\d+)?)%",
            formula,
        )
        if match is None:
            raise ValueError(
                "Unsupported Limit formula. Use last, mark, best_bid, best_ask, "
                "strategy, or one of those followed by +/-N%."
            )
        reference = references[match.group(1)]
        percentage = Decimal(match.group(3)) / Decimal("100")
        multiplier = (
            Decimal("1") + percentage
            if match.group(2) == "+"
            else Decimal("1") - percentage
        )
        resolved = reference * multiplier
        if resolved <= 0:
            raise ValueError("Limit formula resolved to a non-positive price.")
        return resolved

    def _build_context(self, instance: StrategyInstance) -> StrategyEvaluationContext:
        if self._context_builder is not None:
            return self._context_builder(instance)
        return self._market_data.strategy_context(
            instance.symbol,
            instance.timeframe_minutes,
        )

    def _persisted_event_seen(self, instance_id: str, event_key: str) -> bool:
        decisions_method = getattr(self._instances, "decisions", None)
        if not callable(decisions_method):
            return False
        try:
            decisions = decisions_method(instance_id, limit=20)
        except Exception:
            return False
        return any(
            decision.analysis.get("runtime_event_key") == event_key
            for decision in decisions
        )

    def _record_runtime_error_once(
        self,
        instance: StrategyInstance,
        reason: str,
    ) -> None:
        if self._last_runtime_error.get(instance.instance_id) == reason:
            return
        self._last_runtime_error[instance.instance_id] = reason
        try:
            self._instances.record_decision(
                instance.instance_id,
                StrategyDecisionCreate(
                    occurred_at=self._clock(),
                    signal="runtime_waiting",
                    eligible=False,
                    reason_codes=(reason,),
                    analysis={"runtime_status": reason},
                ),
            )
        except Exception:
            return

    def _record_execution_block(
        self,
        instance: StrategyInstance,
        decision_at: datetime,
        reason: str,
        evaluation: StrategyEvaluationResult,
    ) -> None:
        try:
            self._instances.record_decision(
                instance.instance_id,
                StrategyDecisionCreate(
                    occurred_at=decision_at,
                    signal="execution_blocked",
                    eligible=False,
                    reason_codes=(reason,),
                    analysis={
                        "strategy_signal": evaluation.signal,
                        "strategy_reason_codes": list(evaluation.reason_codes),
                    },
                ),
            )
        except Exception:
            return

    @staticmethod
    def _event_key(cadence: str, context) -> str:
        if cadence == "closed_candle":
            if not context.candles:
                raise LookupError(
                    "No closed candles available for strategy evaluation."
                )
            return f"candle:{context.candles[-1].opened_at.astimezone(UTC).isoformat()}"
        return f"market:{context.evaluated_at.astimezone(UTC).isoformat()}"
