"""Engine-owned account dashboard projection for saved strategy instances."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from rangebot.domain.strategy import StrategyOverviewItem
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.trade_history import TradeHistoryRepository


class StrategyOverviewService:
    """Join persisted strategy, decision, and immutable fill facts for the UI."""

    def __init__(
        self,
        strategy_repository: StrategyInstanceRepository,
        trade_history_repository: TradeHistoryRepository,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._strategies = strategy_repository
        self._trades = trade_history_repository
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def list(self) -> list[StrategyOverviewItem]:
        today_start = self._riyadh_day_start(self._now_factory())
        items: list[StrategyOverviewItem] = []
        for instance in self._strategies.list():
            decisions = self._strategies.decisions(instance.instance_id, limit=1)
            latest_decision = decisions[0] if decisions else None
            total = self._trades.summary(
                environment=instance.environment,
                instance_id=instance.instance_id,
            )
            today = self._trades.summary(
                environment=instance.environment,
                instance_id=instance.instance_id,
                since=today_start,
            )
            latest_fills = self._trades.list(
                environment=instance.environment,
                instance_id=instance.instance_id,
                limit=1,
            )
            latest_fill = latest_fills[0] if latest_fills else None
            warnings = self._warning_codes(instance.status, latest_decision)
            items.append(
                StrategyOverviewItem(
                    **instance.model_dump(),
                    current_signal=(latest_decision.signal if latest_decision else None),
                    latest_decision_eligible=(
                        latest_decision.eligible if latest_decision else None
                    ),
                    latest_reason_codes=(
                        latest_decision.reason_codes if latest_decision else ()
                    ),
                    last_decision_at=(
                        latest_decision.occurred_at if latest_decision else None
                    ),
                    today_realized_pnl=today.realized_pnl,
                    total_realized_pnl=total.realized_pnl,
                    win_rate_percentage=total.win_rate_percentage,
                    total_fills=total.fills,
                    last_trade_at=(latest_fill.occurred_at if latest_fill else None),
                    warning_codes=warnings,
                )
            )
        return items

    @staticmethod
    def _riyadh_day_start(value: datetime) -> datetime:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        local = aware.astimezone(ZoneInfo("Asia/Riyadh"))
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    @staticmethod
    def _warning_codes(status: str, latest_decision) -> tuple[str, ...]:
        warnings: list[str] = []
        if status == "error":
            warnings.append("strategy_error")
        if status in {"running", "monitoring"}:
            if latest_decision is None:
                warnings.append("awaiting_first_decision")
            elif not latest_decision.eligible:
                warnings.extend(latest_decision.reason_codes)
        return tuple(dict.fromkeys(warnings))
