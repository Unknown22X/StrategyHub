"""Authenticated Gate futures notifications that trigger authoritative REST reconciliation.

Private WebSocket payloads are never used to independently calculate balances, positions,
orders, or risk state. Every accepted notification causes the existing signed Gate adapter
to reconcile through REST and persist one sanitized ExchangeSnapshot.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
import hashlib
import hmac
import json
from threading import RLock
import time
from typing import Any, Literal

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode
from rangebot.domain.private_stream import (
    PrivateStreamConnectionState,
    PrivateStreamState,
)
from rangebot.engine.credentials import StoredGateCredentials
from rangebot.engine.gate_websocket import (
    ConnectionFactory,
    GateWebSocketConnection,
    LIVE_WEBSOCKET_URL,
    TESTNET_WEBSOCKET_URL,
    websockets_connection,
)


CredentialsProvider = Callable[[TradingMode], StoredGateCredentials | None]
ReconcileAccount = Callable[[TradingMode], ExchangeSnapshot]
PersistSnapshot = Callable[[ExchangeSnapshot], None]
AsyncSleep = Callable[[float], Awaitable[None]]
EpochClock = Callable[[], float]

_PRIVATE_CHANNELS = (
    "futures.balances",
    "futures.positions",
    "futures.orders",
    "futures.usertrades",
    "futures.autoorders",
)


class PrivateStreamStateStore:
    """Thread-safe, sanitized status shared by the async transport and sync FastAPI."""

    def __init__(self, mode: TradingMode | None = None) -> None:
        self._lock = RLock()
        self._state = PrivateStreamState(mode=mode)

    def snapshot(self) -> PrivateStreamState:
        with self._lock:
            return self._state

    def update(
        self,
        *,
        status: PrivateStreamConnectionState,
        connected: bool,
        channels: tuple[str, ...] | None = None,
        event_at: datetime | None = None,
        reconciled_at: datetime | None = None,
        error: str | None = None,
    ) -> PrivateStreamState:
        with self._lock:
            previous = self._state
            self._state = PrivateStreamState(
                mode=previous.mode,
                status=status,
                connected=connected,
                subscribed_channels=(
                    previous.subscribed_channels if channels is None else channels
                ),
                last_event_at=event_at or previous.last_event_at,
                last_reconciled_at=reconciled_at or previous.last_reconciled_at,
                last_error=error,
                revision=previous.revision + 1,
            )
            return self._state


class GatePrivateStreamAuthenticationError(RuntimeError):
    """Raised when Gate rejects or cannot complete private-stream login."""

    def __init__(self, message: str, *, reason: str = "authentication_failed") -> None:
        super().__init__(message)
        self.reason = reason


class GatePrivateStreamCredentialsChanged(RuntimeError):
    """Internal control signal requesting a clean authenticated reconnect."""


class GateFuturesPrivateWebSocketService:
    """Authenticate, subscribe, reconnect, and reconcile after private notifications."""

    def __init__(
        self,
        *,
        mode: TradingMode,
        credentials: CredentialsProvider,
        reconcile: ReconcileAccount,
        persist_snapshot: PersistSnapshot,
        status_store: PrivateStreamStateStore,
        connection_factory: ConnectionFactory | None = None,
        heartbeat_interval_seconds: float = 15.0,
        heartbeat_timeout_seconds: float = 10.0,
        login_timeout_seconds: float = 10.0,
        reconnect_delays_seconds: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0),
        sleep: AsyncSleep = asyncio.sleep,
        epoch_clock: EpochClock = time.time,
    ) -> None:
        if min(
            heartbeat_interval_seconds,
            heartbeat_timeout_seconds,
            login_timeout_seconds,
        ) <= 0:
            raise ValueError("Gate private-stream timeouts must be positive.")
        if not reconnect_delays_seconds or any(
            delay < 0 for delay in reconnect_delays_seconds
        ):
            raise ValueError("Gate private reconnect delays must be non-negative.")
        self._mode = mode
        self._url = LIVE_WEBSOCKET_URL if mode == "live" else TESTNET_WEBSOCKET_URL
        self._credentials = credentials
        self._reconcile = reconcile
        self._persist_snapshot = persist_snapshot
        self._status = status_store
        self._connection_factory = connection_factory or websockets_connection
        self._heartbeat_interval = heartbeat_interval_seconds
        self._heartbeat_timeout = heartbeat_timeout_seconds
        self._login_timeout = login_timeout_seconds
        self._reconnect_delays = reconnect_delays_seconds
        self._sleep = sleep
        self._epoch_clock = epoch_clock
        self._loop: asyncio.AbstractEventLoop | None = None
        self._credential_change_event: asyncio.Event | None = None

    def request_reconnect(self) -> None:
        """Close the current auth session after credentials are saved or removed."""
        loop = self._loop
        event = self._credential_change_event
        if loop is not None and event is not None and not loop.is_closed():
            loop.call_soon_threadsafe(event.set)

    async def run(self, stop_event: asyncio.Event) -> None:
        failures = 0
        self._loop = asyncio.get_running_loop()
        self._credential_change_event = asyncio.Event()
        try:
            while not stop_event.is_set():
                self._credential_change_event.clear()
                stored = await asyncio.to_thread(self._credentials, self._mode)
                if stored is None:
                    self._status.update(
                        status="credentials_missing",
                        connected=False,
                        channels=(),
                        error="credentials_missing",
                    )
                    await self._sleep_or_stop(stop_event, 1.0)
                    continue

                self._status.update(
                    status="connecting" if failures == 0 else "reconnecting",
                    connected=False,
                    error=None,
                )
                try:
                    async with self._connection_factory(self._url) as connection:
                        user_id = await self._login(connection, stored)
                        channels = await self._subscribe(connection, user_id, stored)
                        snapshot = await self._reconcile_and_persist()
                        self._status.update(
                            status="connected",
                            connected=True,
                            channels=channels,
                            reconciled_at=snapshot.reconciled_at,
                            error=None,
                        )
                        failures = 0
                        while not stop_event.is_set():
                            raw = await self._receive_with_heartbeat(
                                connection, stop_event
                            )
                            if raw is None:
                                return
                            await self._handle_message(raw)
                except GatePrivateStreamCredentialsChanged:
                    failures = 0
                    self._status.update(
                        status="reconnecting",
                        connected=False,
                        error=None,
                    )
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    failures += 1
                    self._status.update(
                        status="error" if failures >= 3 else "reconnecting",
                        connected=False,
                        error=_safe_error(error),
                    )
                    delay = self._reconnect_delays[
                        min(failures - 1, len(self._reconnect_delays) - 1)
                    ]
                    await self._sleep_or_stop(stop_event, delay)
        finally:
            self._loop = None
            self._credential_change_event = None

    async def _login(
        self,
        connection: GateWebSocketConnection,
        credentials: StoredGateCredentials,
    ) -> str:
        timestamp = int(self._epoch_clock())
        request_id = f"rangebot-{int(self._epoch_clock() * 1_000_000)}"
        await connection.send(
            json.dumps(
                private_login_message(credentials, timestamp, request_id),
                separators=(",", ":"),
            )
        )
        deadline = asyncio.get_running_loop().time() + self._login_timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise GatePrivateStreamAuthenticationError(
                    "Gate private-stream login timed out.",
                    reason="gate_login_timeout",
                )
            try:
                raw = await asyncio.wait_for(connection.recv(), timeout=remaining)
            except TimeoutError as error:
                raise GatePrivateStreamAuthenticationError(
                    "Gate private-stream login timed out.",
                    reason="gate_login_timeout",
                ) from error
            if _is_login_acknowledgement(raw):
                continue
            return private_login_user_id(raw)

    async def _subscribe(
        self,
        connection: GateWebSocketConnection,
        user_id: str,
        credentials: StoredGateCredentials,
    ) -> tuple[str, ...]:
        now = int(self._epoch_clock())
        messages = private_subscription_messages(
            user_id,
            credentials,
            now=now,
            event="subscribe",
        )
        for message in messages:
            await connection.send(json.dumps(message, separators=(",", ":")))
        return tuple(str(message["channel"]) for message in messages)

    async def _handle_message(self, raw_message: str | bytes) -> None:
        message = _decode_message(raw_message)
        if message.get("error"):
            raise RuntimeError("Gate private WebSocket returned an error response.")
        channel = str(message.get("channel", ""))
        event = str(message.get("event", ""))
        if event != "update" or channel not in _PRIVATE_CHANNELS:
            return
        observed_at = _message_time(message)
        self._status.update(
            status="reconciling",
            connected=True,
            event_at=observed_at,
            error=None,
        )
        snapshot = await self._reconcile_and_persist()
        self._status.update(
            status="connected",
            connected=True,
            event_at=observed_at,
            reconciled_at=snapshot.reconciled_at,
            error=None,
        )

    async def _reconcile_and_persist(self) -> ExchangeSnapshot:
        snapshot = await asyncio.to_thread(self._reconcile, self._mode)
        await asyncio.to_thread(self._persist_snapshot, snapshot)
        return snapshot

    async def _receive_with_heartbeat(
        self,
        connection: GateWebSocketConnection,
        stop_event: asyncio.Event,
    ) -> str | bytes | None:
        credential_change = self._credential_change_event
        if credential_change is None:
            raise RuntimeError("Gate private WebSocket service is not running.")
        receive_task = asyncio.create_task(connection.recv())
        stop_task = asyncio.create_task(stop_event.wait())
        credential_task = asyncio.create_task(credential_change.wait())
        tasks = {receive_task, stop_task, credential_task}
        try:
            done, _ = await asyncio.wait(
                tasks,
                timeout=self._heartbeat_interval,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if credential_task in done and credential_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                raise GatePrivateStreamCredentialsChanged
            if stop_task in done and stop_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                return None
            if receive_task in done:
                return receive_task.result()
            await connection.send(
                json.dumps(
                    {"time": int(self._epoch_clock()), "channel": "futures.ping"},
                    separators=(",", ":"),
                )
            )
            done, _ = await asyncio.wait(
                tasks,
                timeout=self._heartbeat_timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if credential_task in done and credential_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                raise GatePrivateStreamCredentialsChanged
            if stop_task in done and stop_task.result():
                receive_task.cancel()
                await _suppress_cancelled(receive_task)
                return None
            if receive_task in done:
                return receive_task.result()
            receive_task.cancel()
            await _suppress_cancelled(receive_task)
            raise TimeoutError("Gate private WebSocket heartbeat timed out.")
        finally:
            for task in (stop_task, credential_task):
                task.cancel()
                await _suppress_cancelled(task)

    async def _sleep_or_stop(self, stop_event: asyncio.Event, delay: float) -> None:
        credential_change = self._credential_change_event
        if credential_change is None:
            raise RuntimeError("Gate private WebSocket service is not running.")
        if delay == 0:
            await asyncio.sleep(0)
            return
        sleep_task = asyncio.create_task(self._sleep(delay))
        stop_task = asyncio.create_task(stop_event.wait())
        credential_task = asyncio.create_task(credential_change.wait())
        done, _ = await asyncio.wait(
            {sleep_task, stop_task, credential_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in (sleep_task, stop_task, credential_task):
            if task not in done:
                task.cancel()
                await _suppress_cancelled(task)


def private_login_message(
    credentials: StoredGateCredentials,
    timestamp: int,
    request_id: str,
) -> dict[str, object]:
    channel = "futures.login"
    signing_string = f"api\n{channel}\n\n{timestamp}"
    signature = hmac.new(
        credentials.api_secret.encode("utf-8"),
        signing_string.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()
    return {
        "time": timestamp,
        "channel": channel,
        "event": "api",
        "payload": {
            "api_key": credentials.api_key,
            "signature": signature,
            "timestamp": str(timestamp),
            "req_id": request_id,
        },
    }


def private_login_user_id(raw_message: str | bytes) -> str:
    message = _decode_message(raw_message)
    header = message.get("header")
    if isinstance(header, dict) and str(header.get("status", "")) not in {"", "200"}:
        data = message.get("data")
        errors = data.get("errs") if isinstance(data, dict) else None
        label = errors.get("label") if isinstance(errors, dict) else None
        raise GatePrivateStreamAuthenticationError(
            "Gate private-stream authentication was rejected.",
            reason=_login_rejection_reason(label),
        )
    data = message.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    user_id = result.get("uid") if isinstance(result, dict) else None
    if user_id in {None, ""}:
        raise GatePrivateStreamAuthenticationError(
            "Gate private-stream login did not return a user id."
        )
    return str(user_id)


def private_subscription_messages(
    user_id: str,
    credentials: StoredGateCredentials,
    *,
    now: int,
    event: Literal["subscribe", "unsubscribe"],
) -> tuple[dict[str, object], ...]:
    messages: list[dict[str, object]] = []
    for channel, payload in (
        ("futures.balances", [user_id]),
        ("futures.positions", [user_id, "!all"]),
        ("futures.orders", [user_id, "!all"]),
        ("futures.usertrades", [user_id, "!all"]),
        ("futures.autoorders", ["!all"]),
    ):
        signing_string = f"channel={channel}&event={event}&time={now}"
        signature = hmac.new(
            credentials.api_secret.encode("utf-8"),
            signing_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        messages.append(
            {
                "time": now,
                "channel": channel,
                "event": event,
                "payload": payload,
                "auth": {
                    "method": "api_key",
                    "KEY": credentials.api_key,
                    "SIGN": signature,
                },
            }
        )
    return tuple(messages)


def _decode_message(raw_message: str | bytes) -> dict[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    try:
        decoded = json.loads(raw_message)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Gate private WebSocket message is not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise ValueError("Gate private WebSocket message must be a JSON object.")
    return decoded


def _message_time(message: dict[str, Any]) -> datetime:
    raw = message.get("time_ms", message.get("time"))
    if raw in {None, ""}:
        return datetime.now(UTC)
    value = float(str(raw))
    if value > 10_000_000_000:
        value /= 1000
    return datetime.fromtimestamp(value, UTC)


def _safe_error(error: Exception) -> str:
    if isinstance(error, GatePrivateStreamAuthenticationError):
        return error.reason
    if isinstance(error, TimeoutError):
        return "heartbeat_timeout"
    return error.__class__.__name__.casefold()


def _login_rejection_reason(label: object) -> str:
    """Return only Gate's non-sensitive error label for the local status endpoint."""
    if not isinstance(label, str):
        return "authentication_failed"
    normalized = "".join(
        character.lower() if character.isascii() and character.isalnum() else "_"
        for character in label
    ).strip("_")
    if not normalized:
        return "authentication_failed"
    return f"gate_login_{normalized[:64]}"


def _is_login_acknowledgement(raw_message: str | bytes) -> bool:
    """Ignore Gate's preliminary API acknowledgement before the login result."""
    message = _decode_message(raw_message)
    header = message.get("header")
    return bool(
        message.get("ack") is True
        and isinstance(header, dict)
        and header.get("channel") == "futures.login"
    )


async def _suppress_cancelled(task: asyncio.Task[object]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        pass
