"""Engine-owned watchlist projection from normalized Gate market data."""

from decimal import Decimal

from rangebot.domain.market import (
    WatchlistOverview,
    WatchlistOverviewItem,
    WatchlistStrategyReference,
)
from rangebot.engine.market_data_manager import MarketDataManager
from rangebot.engine.repository import PaperWatchlistRepository
from rangebot.engine.strategy_instances import StrategyInstanceRepository


class WatchlistOverviewService:
    """Join watched contracts, Gate snapshots, and saved strategy decisions."""

    def __init__(
        self,
        watchlist_repository: PaperWatchlistRepository,
        market_data: MarketDataManager,
        strategy_repository: StrategyInstanceRepository,
    ) -> None:
        self._watchlist = watchlist_repository
        self._market_data = market_data
        self._strategies = strategy_repository

    def get(self) -> WatchlistOverview:
        watchlist = self._watchlist.get()
        strategy_by_symbol: dict[str, list[WatchlistStrategyReference]] = {}
        for strategy in self._strategies.list():
            decisions = self._strategies.decisions(strategy.instance_id, limit=1)
            latest = decisions[0] if decisions else None
            strategy_by_symbol.setdefault(strategy.symbol, []).append(
                WatchlistStrategyReference(
                    instance_id=strategy.instance_id,
                    name=strategy.name,
                    environment=strategy.environment,
                    status=strategy.status,
                    current_signal=(latest.signal if latest else None),
                    last_decision_at=(latest.occurred_at if latest else None),
                )
            )
        for references in strategy_by_symbol.values():
            references.sort(key=self._strategy_sort_key)

        items = tuple(
            self._item(item, tuple(strategy_by_symbol.get(item.symbol, ())))
            for item in watchlist.items
        )
        return WatchlistOverview(
            items=items,
            automatic_trading_enabled=watchlist.automatic_trading_enabled,
        )

    def _item(
        self,
        item,
        strategies: tuple[WatchlistStrategyReference, ...],
    ) -> WatchlistOverviewItem:
        try:
            market = self._market_data.snapshot(item.symbol)
        except LookupError:
            status = self._market_data.status(item.symbol)
            return WatchlistOverviewItem(
                symbol=item.symbol,
                priority=item.priority,
                is_active=item.is_active,
                monitoring_only=item.monitoring_only,
                direction=item.direction,
                state=status.state,
                state_reason=status.state_reason,
                last_update_age_seconds=status.last_update_age_seconds,
                current_signal=self._preferred_signal(strategies),
                strategies=strategies,
            )

        return WatchlistOverviewItem(
            symbol=item.symbol,
            priority=item.priority,
            is_active=item.is_active,
            monitoring_only=item.monitoring_only,
            direction=item.direction,
            last_price=market.last_price,
            mark_price=market.mark_price,
            index_price=market.index_price,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
            spread_percentage=self._spread_percentage(
                market.best_bid,
                market.best_ask,
            ),
            change_percentage_24h=market.change_percentage_24h,
            high_24h=market.high_24h,
            low_24h=market.low_24h,
            volume_24h=market.volume_24h,
            open_interest=market.open_interest,
            funding_rate=market.funding_rate,
            next_funding_at=market.next_funding_at,
            observed_at=market.observed_at,
            source=market.source,
            state=market.state,
            state_reason=market.state_reason,
            last_update_age_seconds=market.last_update_age_seconds,
            current_signal=self._preferred_signal(strategies),
            strategies=strategies,
        )

    @staticmethod
    def _spread_percentage(
        bid: Decimal | None,
        ask: Decimal | None,
    ) -> Decimal | None:
        if bid is None or ask is None or ask < bid:
            return None
        midpoint = (bid + ask) / Decimal("2")
        if midpoint <= 0:
            return None
        return (ask - bid) / midpoint * Decimal("100")

    @staticmethod
    def _strategy_sort_key(reference: WatchlistStrategyReference) -> tuple[int, str]:
        priority = {
            "running": 0,
            "monitoring": 1,
            "starting": 2,
            "recovering": 3,
            "paused": 4,
            "stopped": 5,
            "error": 6,
        }
        return priority.get(reference.status, 99), reference.name.casefold()

    @staticmethod
    def _preferred_signal(
        strategies: tuple[WatchlistStrategyReference, ...],
    ) -> str | None:
        for strategy in strategies:
            if strategy.status in {"running", "monitoring", "starting", "recovering"}:
                return strategy.current_signal
        return strategies[0].current_signal if strategies else None
