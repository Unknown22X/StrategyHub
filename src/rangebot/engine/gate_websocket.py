"""Gate futures public WebSocket transport and REST gap recovery.

The transport owns connection/reconnect/subscription lifecycle. It never submits orders,
never accepts credentials, and writes only normalized values into MarketDataManager.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from threading import RLock
import time
from typing import Any, Literal, Protocol, cast

import httpx

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.engine.market_data_manager import MarketDataManager


GateFuturesEnvironment = Literal["live", "testnet"]
RestSnapshotLoader = Callable[[str], MarketPriceUpdate]
AsyncSleep = Callable[[float], Awaitable[None]]
EpochClock = Callable[[], float]

LIVE_WEBSOCKET_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"
TESTNET_WEBSOCKET_URL = "wss://ws-testnet.gate.com/v4/ws/futures/usdt"
LIVE_REST_URL = "https://api.gateio.ws/api/v4/futures/usdt"
TESTNET_REST_URL = "https://fx-api-testnet.gateio.ws/api/v4/futures/usdt"

_TIMEFRAME_INTERVALS: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    240: "4h",
    480: "8h",
    1440: "1d",
    10080: "7d",
}
_INTERVAL_TIMEFRAMES = {value: key for key, value in _TIMEFRAME_INTERVALS.items()}


class GateWebSocketConnection(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


ConnectionFactory = Callable[
    [str], AbstractAsyncContextManager[GateWebSocketConnection]
]


class GateWebSocketHeartbeatTimeout(TimeoutError):
    """Raised when Gate sends no data or pong inside the heartbeat window."""


@dataclass(frozen=True)
class GateMarketTarget:
    symbol: str
    timeframe_minutes: int | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper():
            raise ValueError("Gate market symbols must be uppercase.")
        if (
            self.timeframe_minutes is not None
            and self.timeframe_minutes not in _TIMEFRAME_INTERVALS
        ):
            supported = ", ".join(str(value) for value in _TIMEFRAME_INTERVALS)
            raise ValueError(
                f"Unsupported Gate candle timeframe {self.timeframe_minutes}; "
                f"supported minute values: {supported}."
            )


class MarketSubscriptionRegistry:
    """Thread-safe desired subscription set shared by sync API and async transport."""

    def __init__(self, targets: tuple[GateMarketTarget, ...] = ()) -> None:
        self._lock = RLock()
        self._targets = frozenset(targets)
        self._revision = 1

    def replace(self, targets: tuple[GateMarketTarget, ...]) -> int:
        normalized = frozenset(targets)
        with self._lock:
            if normalized == self._targets:
                return self._revision
            self._targets = normalized
            self._revision += 1
            return self._revision

    def snapshot(self) -> tuple[int, tuple[GateMarketTarget, ...]]:
        with self._lock:
            return self._revision, tuple(sorted(self._targets, key=_target_sort_key))


class GateFuturesRestSnapshotProvider:
    """Public REST replacement snapshot including Gate's order-book update ID."""

    def __init__(
        self,
        environment: GateFuturesEnvironment,
        *,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Gate REST timeout must be positive.")
        self._base_url = (
            base_url
            or (LIVE_REST_URL if environment == "live" else TESTNET_REST_URL)
        ).rstrip("/")
        self._transport = transport
        self._timeout_seconds = timeout_seconds

    def snapshot(self, symbol: str) -> MarketPriceUpdate:
        contract = self._get_json(f"contracts/{symbol}")
        order_book = self._get_json(
            "order_book",
            params={
                "contract": symbol,
                "limit": "1",
                "with_id": "true",
            },
        )
        if not isinstance(contract, dict) or not isinstance(order_book, dict):
            raise LookupError(f"Gate REST snapshot is malformed for {symbol}.")

        bids = order_book.get("bids")
        asks = order_book.get("asks")
        best_bid = _first_book_price(bids)
        best_ask = _first_book_price(asks)
        observed_at = _rest_observed_at(order_book)
        last_value = contract.get("last_price", contract.get("last"))
        if last_value in {None, ""}:
            raise LookupError(f"Gate REST snapshot has no last price for {symbol}.")

        return MarketPriceUpdate(
            symbol=symbol,
            last_price=_decimal(last_value, "last price"),
            mark_price=_optional_decimal(contract.get("mark_price"), "mark price"),
            index_price=_optional_decimal(contract.get("index_price"), "index price"),
            best_bid=best_bid,
            best_ask=best_ask,
            volume_24h=_optional_nonnegative_decimal(
                contract.get("volume_24h_quote", contract.get("volume_24h")),
                "24h volume",
            ),
            open_interest=_optional_nonnegative_decimal(
                contract.get("position_size"), "open interest"
            ),
            funding_rate=_optional_finite_decimal(
                contract.get("funding_rate"), "funding rate"
            ),
            next_funding_at=_optional_epoch_datetime(
                contract.get("funding_next_apply"), "next funding time"
            ),
            observed_at=observed_at,
            source="gate_rest",
            sequence=_optional_integer(order_book.get("id"), "order-book ID"),
        )

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> object:
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout_seconds,
                headers={"Accept": "application/json", "X-Gate-Size-Decimal": "1"},
            ) as client:
                response = client.get(f"{self._base_url}/{path}", params=params)
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LookupError("Gate public REST market data is unavailable.") from error
        return response.json()


class GateFuturesMessageHandler:
    """Parse Gate public messages and apply normalized updates atomically."""

    def __init__(
        self,
        market_data: MarketDataManager,
        rest_snapshot: RestSnapshotLoader,
    ) -> None:
        self._market_data = market_data
        self._rest_snapshot = rest_snapshot

    async def bootstrap(self, symbols: tuple[str, ...]) -> None:
        for symbol in sorted(set(symbols)):
            self._market_data.track(symbol)
            await self.restore(symbol)

    async def restore(self, symbol: str) -> None:
        snapshot = await asyncio.to_thread(self._rest_snapshot, symbol)
        self._market_data.apply_rest_snapshot(snapshot)

    async def handle(self, raw_message: str | bytes) -> None:
        message = _decode_message(raw_message)
        if message.get("error"):
            raise RuntimeError(f"Gate WebSocket error: {message['error']}")
        if message.get("event") != "update":
            return

        channel = message.get("channel")
        result = message.get("result")
        if channel == "futures.tickers":
            await self._handle_tickers(result, message)
        elif channel == "futures.book_ticker":
            await self._handle_book_ticker(result, message)
        elif channel == "futures.order_book_update":
            await self._handle_order_book_update(result, message)
        elif channel == "futures.candlesticks":
            self._handle_candlesticks(result)

    async def _handle_tickers(self, result: object, envelope: dict[str, Any]) -> None:
        if not isinstance(result, list):
            raise ValueError("Gate ticker update result must be a list.")
        for item in result:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("contract", ""))
            last = item.get("last")
            if not symbol or last in {None, ""}:
                continue
            update = MarketPriceUpdate(
                symbol=symbol,
                last_price=_decimal(last, "ticker last price"),
                mark_price=_optional_decimal(item.get("mark_price"), "mark price"),
                index_price=_optional_decimal(item.get("index_price"), "index price"),
                best_bid=_optional_decimal(item.get("highest_bid"), "best bid"),
                best_ask=_optional_decimal(item.get("lowest_ask"), "best ask"),
                change_percentage_24h=_optional_finite_decimal(
                    item.get("change_percentage"), "24h change percentage"
                ),
                high_24h=_optional_decimal(item.get("high_24h"), "24h high"),
                low_24h=_optional_decimal(item.get("low_24h"), "24h low"),
                volume_24h=_optional_nonnegative_decimal(
                    item.get("volume_24h_quote", item.get("volume_24h")),
                    "24h volume",
                ),
                open_interest=_optional_nonnegative_decimal(
                    item.get("total_size"), "open interest"
                ),
                funding_rate=_optional_finite_decimal(
                    item.get("funding_rate"), "funding rate"
                ),
                observed_at=_message_observed_at(item, envelope),
                source="gate_websocket",
            )
            self._market_data.apply_websocket_update(update)

    async def _handle_book_ticker(
        self,
        result: object,
        envelope: dict[str, Any],
    ) -> None:
        if not isinstance(result, dict):
            raise ValueError("Gate book ticker result must be an object.")
        symbol = str(result.get("s", ""))
        if not symbol:
            return
        current = await self._current_or_restore(symbol)
        update = MarketPriceUpdate(
            symbol=symbol,
            last_price=current.last_price,
            best_bid=_optional_decimal(result.get("b"), "best bid"),
            best_ask=_optional_decimal(result.get("a"), "best ask"),
            observed_at=_message_observed_at(result, envelope),
            source="gate_websocket",
        )
        self._market_data.apply_websocket_update(update)

    async def _handle_order_book_update(
        self,
        result: object,
        envelope: dict[str, Any],
    ) -> None:
        if not isinstance(result, dict):
            raise ValueError("Gate order-book update result must be an object.")
        symbol = str(result.get("s", ""))
        if not symbol:
            return
        current = await self._current_or_restore(symbol)
        sequence_start = _required_integer(result.get("U"), "first update ID")
        sequence = _required_integer(result.get("u"), "last update ID")
        updated = self._market_data.apply_websocket_update(
            MarketPriceUpdate(
                symbol=symbol,
                last_price=current.last_price,
                observed_at=_message_observed_at(result, envelope),
                source="gate_websocket",
                sequence_start=sequence_start,
                sequence=sequence,
            )
        )
        if updated.sequence_gap:
            await self.restore(symbol)

    def _handle_candlesticks(self, result: object) -> None:
        if not isinstance(result, list):
            raise ValueError("Gate candlestick update result must be a list.")
        for item in result:
            if not isinstance(item, dict):
                continue
            name = str(item.get("n", ""))
            interval, separator, symbol = name.partition("_")
            if not separator or interval not in _INTERVAL_TIMEFRAMES or not symbol:
                continue
            timeframe_minutes = _INTERVAL_TIMEFRAMES[interval]
            opened_at = datetime.fromtimestamp(
                _required_integer(item.get("t"), "candle timestamp"), UTC
            )
            self._market_data.append_candle(
                symbol,
                timeframe_minutes,
                NormalizedCandle(
                    opened_at=opened_at,
                    closed_at=opened_at + timedelta(minutes=timeframe_minutes),
                    open=_decimal(item.get("o"), "candle open"),
                    high=_decimal(item.get("h"), "candle high"),
                    low=_decimal(item.get("l"), "candle low"),
                    close=_decimal(item.get("c"), "candle close"),
                    volume=_nonnegative_decimal(item.get("v", "0"), "candle volume"),
                    closed=bool(item.get("w", False)),
                ),
                source="gate_websocket",
            )

    async def _current_or_restore(self, symbol: str):
        try:
            return self._market_data.snapshot(symbol)
        except LookupError:
            await self.restore(symbol)
            return self._market_data.snapshot(symbol)


class GateFuturesWebSocketService:
    """Reconnect, heartbeat, and dynamically resubscribe Gate public channels."""

    def __init__(
        self,
        *,
        environment: GateFuturesEnvironment,
        market_data: MarketDataManager,
        subscriptions: MarketSubscriptionRegistry,
        rest_snapshot: RestSnapshotLoader,
        connection_factory: ConnectionFactory | None = None,
        heartbeat_interval_seconds: float = 15.0,
        heartbeat_timeout_seconds: float = 10.0,
        reconnect_delays_seconds: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0),
        unavailable_after_failures: int = 3,
        sleep: AsyncSleep = asyncio.sleep,
        epoch_clock: EpochClock = time.time,
    ) -> None:
        if heartbeat_interval_seconds <= 0 or heartbeat_timeout_seconds <= 0:
            raise ValueError("Gate heartbeat intervals must be positive.")
        if not reconnect_delays_seconds or any(
            delay < 0 for delay in reconnect_delays_seconds
        ):
            raise ValueError("Gate reconnect delays must be non-negative.")
        if unavailable_after_failures < 1:
            raise ValueError("Unavailable failure threshold must be positive.")
        self._url = (
            LIVE_WEBSOCKET_URL
            if environment == "live"
            else TESTNET_WEBSOCKET_URL
        )
        self._market_data = market_data
        self._subscriptions = subscriptions
        self._handler = GateFuturesMessageHandler(market_data, rest_snapshot)
        self._connection_factory = connection_factory or websockets_connection
        self._heartbeat_interval = heartbeat_interval_seconds
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._reconnect_delays = reconnect_delays_seconds
        self._unavailable_after = unavailable_after_failures
        self._sleep = sleep
        self._epoch_clock = epoch_clock

    async def run(self, stop_event: asyncio.Event) -> None:
        failures = 0
        while not stop_event.is_set():
            revision, targets = self._subscriptions.snapshot()
            if not targets:
                await self._sleep_or_stop(stop_event, 0.25)
                continue
            symbols = _target_symbols(targets)
            for symbol in symbols:
                if failures >= self._unavailable_after:
                    self._market_data.mark_unavailable(
                        symbol, "websocket_reconnect_exhausted"
                    )
                else:
                    self._market_data.mark_reconnecting(symbol)
            try:
                await self._handler.bootstrap(symbols)
                async with self._connection_factory(self._url) as connection:
                    active_targets: tuple[GateMarketTarget, ...] = ()
                    active_targets = await self._replace_subscriptions(
                        connection, active_targets, targets
                    )
                    failures = 0
                    while not stop_event.is_set():
                        raw = await self._receive_with_heartbeat(connection, stop_event)
                        if raw is None:
                            return
                        await self._handler.handle(raw)
                        current_revision, desired_targets = self._subscriptions.snapshot()
                        if current_revision != revision:
                            await self._handler.bootstrap(
                                tuple(
                                    sorted(
                                        set(_target_symbols(desired_targets))
                                        - set(_target_symbols(active_targets))
                                    )
                                )
                            )
                            active_targets = await self._replace_subscriptions(
                                connection, active_targets, desired_targets
                            )
                            revision = current_revision
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
                for symbol in symbols:
                    if failures >= self._unavailable_after:
                        self._market_data.mark_unavailable(
                            symbol, "websocket_reconnect_exhausted"
                        )
                    else:
                        self._market_data.mark_reconnecting(symbol)
                delay = self._reconnect_delays[
                    min(failures - 1, len(self._reconnect_delays) - 1)
                ]
                await self._sleep_or_stop(stop_event, delay)

    async def _replace_subscriptions(
        self,
        connection: GateWebSocketConnection,
        active: tuple[GateMarketTarget, ...],
        desired: tuple[GateMarketTarget, ...],
    ) -> tuple[GateMarketTarget, ...]:
        if active:
            await _send_subscription_messages(
                connection,
                active,
                event="unsubscribe",
                epoch_clock=self._epoch_clock,
            )
        if desired:
            await _send_subscription_messages(
                connection,
                desired,
                event="subscribe",
                epoch_clock=self._epoch_clock,
            )
        return desired

    async def _receive_with_heartbeat(
        self,
        connection: GateWebSocketConnection,
        stop_event: asyncio.Event,
    ) -> str | bytes | None:
        receive_task = asyncio.create_task(connection.recv())
        stop_task = asyncio.create_task(stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {receive_task, stop_task},
                timeout=self._heartbeat_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done and stop_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                return None
            if receive_task in done:
                return receive_task.result()

            await connection.send(
                json.dumps(
                    {
                        "time": int(self._epoch_clock()),
                        "channel": "futures.ping",
                    },
                    separators=(",", ":"),
                )
            )
            done, _ = await asyncio.wait(
                {receive_task, stop_task},
                timeout=self._heartbeat_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done and stop_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                return None
            if receive_task in done:
                return receive_task.result()
            receive_task.cancel()
            await _suppress_cancelled(receive_task)
            raise GateWebSocketHeartbeatTimeout(
                "Gate WebSocket heartbeat timed out."
            )
        finally:
            stop_task.cancel()
            await _suppress_cancelled(stop_task)

    async def _sleep_or_stop(
        self,
        stop_event: asyncio.Event,
        delay: float,
    ) -> None:
        if delay == 0:
            await asyncio.sleep(0)
            return
        sleep_task = asyncio.create_task(self._sleep(delay))
        stop_task = asyncio.create_task(stop_event.wait())
        done, _ = await asyncio.wait(
            {sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in (sleep_task, stop_task):
            if task not in done:
                task.cancel()
                await _suppress_cancelled(task)


def websockets_connection(
    url: str,
) -> AbstractAsyncContextManager[GateWebSocketConnection]:
    """Create the real network connection lazily so pure unit tests need no package."""
    try:
        from websockets.asyncio.client import connect
    except ImportError as error:  # pragma: no cover - exercised only in packaged runtime
        raise RuntimeError(
            "The optional `websockets` runtime dependency is not installed."
        ) from error
    return cast(
        AbstractAsyncContextManager[GateWebSocketConnection],
        connect(
            url,
            additional_headers={"X-Gate-Size-Decimal": "1"},
            ping_interval=None,
            close_timeout=5,
            max_queue=256,
        ),
    )


async def _send_subscription_messages(
    connection: GateWebSocketConnection,
    targets: tuple[GateMarketTarget, ...],
    *,
    event: Literal["subscribe", "unsubscribe"],
    epoch_clock: EpochClock,
) -> None:
    for payload in subscription_messages(targets, event=event, now=int(epoch_clock())):
        await connection.send(json.dumps(payload, separators=(",", ":")))


def subscription_messages(
    targets: tuple[GateMarketTarget, ...],
    *,
    event: Literal["subscribe", "unsubscribe"],
    now: int,
) -> tuple[dict[str, object], ...]:
    symbols = _target_symbols(targets)
    messages: list[dict[str, object]] = []
    for symbol in symbols:
        for channel, payload in (
            ("futures.tickers", [symbol]),
            ("futures.book_ticker", [symbol]),
            ("futures.order_book_update", [symbol, "100ms", "100"]),
        ):
            messages.append(
                {
                    "time": now,
                    "channel": channel,
                    "event": event,
                    "payload": payload,
                }
            )
    for target in sorted(set(targets), key=_target_sort_key):
        if target.timeframe_minutes is None:
            continue
        messages.append(
            {
                "time": now,
                "channel": "futures.candlesticks",
                "event": event,
                "payload": [
                    _TIMEFRAME_INTERVALS[target.timeframe_minutes],
                    target.symbol,
                ],
            }
        )
    return tuple(messages)


def _target_sort_key(target: GateMarketTarget) -> tuple[str, int]:
    return (
        target.symbol,
        -1 if target.timeframe_minutes is None else target.timeframe_minutes,
    )


def _target_symbols(targets: tuple[GateMarketTarget, ...]) -> tuple[str, ...]:
    return tuple(sorted({target.symbol for target in targets}))


def _decode_message(raw_message: str | bytes) -> dict[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    try:
        decoded = json.loads(raw_message)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Gate WebSocket message is not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise ValueError("Gate WebSocket message must be a JSON object.")
    return decoded


def _message_observed_at(
    payload: dict[str, object],
    envelope: dict[str, Any],
) -> datetime:
    milliseconds = payload.get("t", envelope.get("time_ms"))
    if milliseconds not in {None, ""}:
        value = float(str(milliseconds))
        if value > 10_000_000_000:
            value /= 1000
        return datetime.fromtimestamp(value, UTC)
    seconds = envelope.get("time")
    if seconds not in {None, ""}:
        return datetime.fromtimestamp(float(str(seconds)), UTC)
    return datetime.now(UTC)


def _rest_observed_at(order_book: dict[str, object]) -> datetime:
    raw = order_book.get("update", order_book.get("current"))
    if raw in {None, ""}:
        return datetime.now(UTC)
    value = float(str(raw))
    if value > 10_000_000_000:
        value /= 1000
    return datetime.fromtimestamp(value, UTC)


def _first_book_price(value: object) -> Decimal | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    if not isinstance(first, dict):
        return None
    return _optional_decimal(first.get("p"), "order-book price")


def _decimal(value: object, field: str) -> Decimal:
    if value in {None, ""}:
        raise ValueError(f"Gate {field} is missing.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Gate {field} is not numeric.") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"Gate {field} must be positive.")
    return parsed


def _nonnegative_decimal(value: object, field: str) -> Decimal:
    if value in {None, ""}:
        raise ValueError(f"Gate {field} is missing.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Gate {field} is not numeric.") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"Gate {field} must be non-negative.")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value in {None, ""}:
        return None
    return _decimal(value, field)


def _optional_nonnegative_decimal(value: object, field: str) -> Decimal | None:
    if value in {None, ""}:
        return None
    return _nonnegative_decimal(value, field)


def _optional_finite_decimal(value: object, field: str) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Gate {field} is not numeric.") from error
    if not parsed.is_finite():
        raise ValueError(f"Gate {field} must be finite.")
    return parsed


def _optional_epoch_datetime(value: object, field: str) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        timestamp = float(str(value))
    except ValueError as error:
        raise ValueError(f"Gate {field} is not numeric.") from error
    if timestamp < 0:
        raise ValueError(f"Gate {field} must be non-negative.")
    return datetime.fromtimestamp(timestamp, UTC)


def _required_integer(value: object, field: str) -> int:
    parsed = _optional_integer(value, field)
    if parsed is None:
        raise ValueError(f"Gate {field} is missing.")
    return parsed


def _optional_integer(value: object, field: str) -> int | None:
    if value in {None, ""}:
        return None
    try:
        parsed = int(str(value))
    except ValueError as error:
        raise ValueError(f"Gate {field} is not an integer.") from error
    if parsed < 0:
        raise ValueError(f"Gate {field} must be non-negative.")
    return parsed


async def _suppress_cancelled(task: asyncio.Task[object]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        pass
