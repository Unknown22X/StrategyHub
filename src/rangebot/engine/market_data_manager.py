"""Authoritative normalized market-data cache and freshness state machine."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import RLock

from rangebot.domain.market_data import (
    MarketCandleSeries,
    MarketDataSnapshot,
    MarketDataSource,
    MarketDataStatus,
    MarketPriceUpdate,
)
from rangebot.domain.strategy_runtime import (
    MarketDataState,
    NormalizedCandle,
    StrategyEvaluationContext,
)


Clock = Callable[[], datetime]


@dataclass
class _StoredMarket:
    update: MarketPriceUpdate
    received_at: datetime
    state: MarketDataState
    state_reason: str | None
    sequence_gap: bool


@dataclass
class _StoredCandles:
    candles: dict[datetime, NormalizedCandle]
    source: MarketDataSource
    updated_at: datetime


class MarketDataManager:
    """Own market truth supplied by Gate REST/WebSocket and expose explicit states."""

    def __init__(
        self,
        *,
        freshness_threshold: timedelta = timedelta(seconds=5),
        clock: Clock | None = None,
    ) -> None:
        if freshness_threshold <= timedelta(0):
            raise ValueError("Freshness threshold must be positive.")
        self._freshness_threshold = freshness_threshold
        self._clock = clock or (lambda: datetime.now(UTC))
        self._markets: dict[str, _StoredMarket] = {}
        self._statuses: dict[str, MarketDataStatus] = {}
        self._candles: dict[tuple[str, int], _StoredCandles] = {}
        self._lock = RLock()

    def track(self, symbol: str) -> MarketDataStatus:
        """Register a symbol before the first subscription/snapshot arrives."""
        with self._lock:
            existing = self._statuses.get(symbol)
            if existing is not None:
                return existing
            status = MarketDataStatus(
                symbol=symbol,
                state="reconnecting",
                state_reason="awaiting_initial_snapshot",
            )
            self._statuses[symbol] = status
            return status

    def apply_rest_snapshot(self, update: MarketPriceUpdate) -> MarketDataSnapshot:
        if update.source != "gate_rest":
            raise ValueError("REST snapshots must declare source=gate_rest.")
        return self._replace_market(update, clear_sequence_gap=True)

    def apply_websocket_update(self, update: MarketPriceUpdate) -> MarketDataSnapshot:
        if update.source != "gate_websocket":
            raise ValueError("WebSocket updates must declare source=gate_websocket.")
        with self._lock:
            current = self._markets.get(update.symbol)
            if current is not None and current.sequence_gap:
                return self._snapshot_locked(update.symbol)
            if (
                current is not None
                and current.update.sequence is not None
                and update.sequence is not None
            ):
                if update.sequence <= current.update.sequence:
                    return self._snapshot_locked(update.symbol)
                sequence_start = update.sequence_start or update.sequence
                if sequence_start > current.update.sequence + 1:
                    current.state = "stale"
                    current.state_reason = "sequence_gap"
                    current.sequence_gap = True
                    self._refresh_status_locked(update.symbol)
                    return self._snapshot_locked(update.symbol)
            if current is not None:
                update = self._merge_websocket_update(current.update, update)
        return self._replace_market(update, clear_sequence_gap=False)

    def mark_reconnecting(self, symbol: str) -> MarketDataStatus:
        return self._mark_state(symbol, "reconnecting", "websocket_reconnecting")

    def mark_unavailable(self, symbol: str, reason: str = "market_data_unavailable") -> MarketDataStatus:
        return self._mark_state(symbol, "unavailable", reason)

    def refresh_freshness(self, symbol: str | None = None) -> None:
        with self._lock:
            now = self._now()
            symbols = (symbol,) if symbol is not None else tuple(self._markets)
            for current_symbol in symbols:
                stored = self._markets.get(current_symbol)
                if stored is None:
                    continue
                if stored.state == "fresh" and now - stored.received_at > self._freshness_threshold:
                    stored.state = "stale"
                    stored.state_reason = "freshness_timeout"
                    self._refresh_status_locked(current_symbol, now=now)

    def snapshot(self, symbol: str) -> MarketDataSnapshot:
        self.refresh_freshness(symbol)
        with self._lock:
            if symbol not in self._markets:
                raise LookupError(f"No market snapshot is available for {symbol}.")
            return self._snapshot_locked(symbol)

    def status(self, symbol: str) -> MarketDataStatus:
        self.refresh_freshness(symbol)
        with self._lock:
            if symbol in self._markets:
                self._refresh_status_locked(symbol)
            status = self._statuses.get(symbol)
            if status is None:
                return MarketDataStatus(
                    symbol=symbol,
                    state="unavailable",
                    state_reason="symbol_not_tracked",
                )
            return status

    def replace_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        candles: tuple[NormalizedCandle, ...] | list[NormalizedCandle],
        *,
        source: MarketDataSource = "gate_rest",
    ) -> MarketCandleSeries:
        if not 1 <= timeframe_minutes <= 10080:
            raise ValueError("Timeframe must be between 1 and 10080 minutes.")
        now = self._now()
        deduplicated = {candle.opened_at: candle for candle in candles}
        with self._lock:
            self._candles[(symbol, timeframe_minutes)] = _StoredCandles(
                candles=deduplicated,
                source=source,
                updated_at=now,
            )
            return self._candle_series_locked(symbol, timeframe_minutes)

    def append_candle(
        self,
        symbol: str,
        timeframe_minutes: int,
        candle: NormalizedCandle,
        *,
        source: MarketDataSource = "gate_websocket",
    ) -> MarketCandleSeries:
        now = self._now()
        with self._lock:
            key = (symbol, timeframe_minutes)
            stored = self._candles.get(key)
            if stored is None:
                stored = _StoredCandles(candles={}, source=source, updated_at=now)
                self._candles[key] = stored
            stored.candles[candle.opened_at] = candle
            stored.source = source
            stored.updated_at = now
            return self._candle_series_locked(symbol, timeframe_minutes)

    def candle_series(self, symbol: str, timeframe_minutes: int) -> MarketCandleSeries:
        with self._lock:
            if (symbol, timeframe_minutes) not in self._candles:
                raise LookupError(
                    f"No candle series is available for {symbol} {timeframe_minutes}m."
                )
            return self._candle_series_locked(symbol, timeframe_minutes)

    def strategy_context(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        evaluated_at: datetime | None = None,
        reconciliation_ready: bool = True,
        emergency_stop: bool = False,
        candles_since_last_entry: int | None = None,
    ) -> StrategyEvaluationContext:
        market = self.snapshot(symbol)
        candles = self.candle_series(symbol, timeframe_minutes)
        return StrategyEvaluationContext(
            symbol=symbol,
            evaluated_at=evaluated_at or self._now(),
            timeframe_minutes=timeframe_minutes,
            candles=candles.candles,
            last_price=market.last_price,
            mark_price=market.mark_price,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
            market_data_state=market.state,
            reconciliation_ready=reconciliation_ready,
            emergency_stop=emergency_stop,
            candles_since_last_entry=candles_since_last_entry,
        )

    def _replace_market(
        self, update: MarketPriceUpdate, *, clear_sequence_gap: bool
    ) -> MarketDataSnapshot:
        now = self._now()
        with self._lock:
            self._markets[update.symbol] = _StoredMarket(
                update=update,
                received_at=now,
                state="fresh",
                state_reason=None,
                sequence_gap=False if clear_sequence_gap else False,
            )
            self._refresh_status_locked(update.symbol, now=now)
            return self._snapshot_locked(update.symbol, now=now)

    @staticmethod
    def _merge_websocket_update(
        current: MarketPriceUpdate,
        incoming: MarketPriceUpdate,
    ) -> MarketPriceUpdate:
        """Keep fields and order-book sequence omitted by a partial WS channel."""
        return incoming.model_copy(
            update={
                "mark_price": (
                    incoming.mark_price
                    if incoming.mark_price is not None
                    else current.mark_price
                ),
                "index_price": (
                    incoming.index_price
                    if incoming.index_price is not None
                    else current.index_price
                ),
                "best_bid": (
                    incoming.best_bid
                    if incoming.best_bid is not None
                    else current.best_bid
                ),
                "best_ask": (
                    incoming.best_ask
                    if incoming.best_ask is not None
                    else current.best_ask
                ),
                "change_percentage_24h": (
                    incoming.change_percentage_24h
                    if incoming.change_percentage_24h is not None
                    else current.change_percentage_24h
                ),
                "high_24h": (
                    incoming.high_24h
                    if incoming.high_24h is not None
                    else current.high_24h
                ),
                "low_24h": (
                    incoming.low_24h
                    if incoming.low_24h is not None
                    else current.low_24h
                ),
                "volume_24h": (
                    incoming.volume_24h
                    if incoming.volume_24h is not None
                    else current.volume_24h
                ),
                "open_interest": (
                    incoming.open_interest
                    if incoming.open_interest is not None
                    else current.open_interest
                ),
                "funding_rate": (
                    incoming.funding_rate
                    if incoming.funding_rate is not None
                    else current.funding_rate
                ),
                "next_funding_at": (
                    incoming.next_funding_at
                    if incoming.next_funding_at is not None
                    else current.next_funding_at
                ),
                "sequence_start": (
                    incoming.sequence_start
                    if incoming.sequence is not None
                    else current.sequence_start
                ),
                "sequence": (
                    incoming.sequence
                    if incoming.sequence is not None
                    else current.sequence
                ),
            }
        )

    def _mark_state(
        self, symbol: str, state: MarketDataState, reason: str
    ) -> MarketDataStatus:
        with self._lock:
            stored = self._markets.get(symbol)
            if stored is not None:
                stored.state = state
                stored.state_reason = reason
                self._refresh_status_locked(symbol)
            else:
                self._statuses[symbol] = MarketDataStatus(
                    symbol=symbol,
                    state=state,
                    state_reason=reason,
                )
            return self._statuses[symbol]

    def _snapshot_locked(
        self, symbol: str, *, now: datetime | None = None
    ) -> MarketDataSnapshot:
        stored = self._markets[symbol]
        current_time = now or self._now()
        return MarketDataSnapshot(
            symbol=symbol,
            last_price=stored.update.last_price,
            mark_price=stored.update.mark_price,
            index_price=stored.update.index_price,
            best_bid=stored.update.best_bid,
            best_ask=stored.update.best_ask,
            change_percentage_24h=stored.update.change_percentage_24h,
            high_24h=stored.update.high_24h,
            low_24h=stored.update.low_24h,
            volume_24h=stored.update.volume_24h,
            open_interest=stored.update.open_interest,
            funding_rate=stored.update.funding_rate,
            next_funding_at=stored.update.next_funding_at,
            observed_at=stored.update.observed_at,
            received_at=stored.received_at,
            source=stored.update.source,
            sequence=stored.update.sequence,
            state=stored.state,
            state_reason=stored.state_reason,
            sequence_gap=stored.sequence_gap,
            last_update_age_seconds=self._age_seconds(
                current_time, stored.received_at
            ),
        )

    def _refresh_status_locked(
        self, symbol: str, *, now: datetime | None = None
    ) -> None:
        stored = self._markets[symbol]
        current_time = now or self._now()
        self._statuses[symbol] = MarketDataStatus(
            symbol=symbol,
            state=stored.state,
            state_reason=stored.state_reason,
            source=stored.update.source,
            sequence_gap=stored.sequence_gap,
            last_update_at=stored.received_at,
            last_update_age_seconds=self._age_seconds(
                current_time, stored.received_at
            ),
        )

    def _candle_series_locked(
        self, symbol: str, timeframe_minutes: int
    ) -> MarketCandleSeries:
        stored = self._candles[(symbol, timeframe_minutes)]
        return MarketCandleSeries(
            symbol=symbol,
            timeframe_minutes=timeframe_minutes,
            candles=tuple(
                stored.candles[key] for key in sorted(stored.candles)
            ),
            source=stored.source,
            updated_at=stored.updated_at,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Market Data Manager clock must return timezone-aware values.")
        return value

    @staticmethod
    def _age_seconds(now: datetime, then: datetime) -> Decimal:
        delta = max(now - then, timedelta(0))
        return (
            Decimal(delta.days * 86400 + delta.seconds)
            + (Decimal(delta.microseconds) / Decimal("1000000"))
        )
