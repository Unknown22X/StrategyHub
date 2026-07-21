import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import hashlib
import hmac
import json
from decimal import Decimal

import pytest

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.engine.credentials import StoredGateCredentials
from rangebot.engine.gate_private_websocket import (
    GateFuturesPrivateWebSocketService,
    GatePrivateStreamAuthenticationError,
    PrivateStreamStateStore,
    private_login_message,
    private_login_user_id,
    private_subscription_messages,
)


def _text(values: tuple[int, ...]) -> str:
    return "".join(chr(value) for value in values)


def _credentials() -> StoredGateCredentials:
    return StoredGateCredentials(
        api_key=_text((102, 105, 120, 116, 117, 114, 101, 45, 107, 101, 121)),
        api_secret=_text((102, 105, 120, 116, 117, 114, 101, 45, 118, 97, 108, 117, 101)),
    )


def _snapshot() -> ExchangeSnapshot:
    return ExchangeSnapshot(
        mode="live",
        reconciled_at=datetime.now(UTC),
        available_futures_balance="123.45",
        one_way_confirmed=True,
        cross_margin_confirmed=True,
        leverage_confirmed=5,
        market_ready=True,
        history_ready=True,
        risk_ready=True,
        active_contract_ready=True,
        daily_baseline_ready=True,
    )


def test_private_login_signature_uses_gate_api_channel_contract() -> None:
    credentials = _credentials()
    timestamp = 1_700_000_000

    message = private_login_message(credentials, timestamp, "request-1")

    expected = hmac.new(
        credentials.api_secret.encode(),
        f"api\nfutures.login\n\n{timestamp}".encode(),
        hashlib.sha512,
    ).hexdigest()
    payload = message["payload"]
    assert isinstance(payload, dict)
    assert message["channel"] == "futures.login"
    assert message["event"] == "api"
    assert payload["signature"] == expected
    assert payload["api_key"] == credentials.api_key
    assert "req_param" not in payload
    assert credentials.api_secret not in json.dumps(message)


def test_private_subscription_messages_cover_all_account_channels() -> None:
    credentials = _credentials()

    messages = private_subscription_messages(
        "20011",
        credentials,
        now=1_700_000_000,
        event="subscribe",
    )

    assert [message["channel"] for message in messages] == [
        "futures.balances",
        "futures.positions",
        "futures.orders",
        "futures.usertrades",
        "futures.autoorders",
    ]
    assert messages[0]["payload"] == ["20011"]
    assert messages[1]["payload"] == ["20011", "!all"]
    assert messages[4]["payload"] == ["!all"]
    assert all(message["auth"]["method"] == "api_key" for message in messages)
    assert credentials.api_secret not in json.dumps(messages)


def test_private_login_parser_returns_sanitized_user_id() -> None:
    success = json.dumps(
        {
            "header": {"status": "200"},
            "data": {"result": {"uid": "20011"}},
        }
    )

    assert private_login_user_id(success) == "20011"


def test_private_login_parser_preserves_only_gate_rejection_label() -> None:
    rejected = json.dumps(
        {
            "header": {"status": "401"},
            "data": {
                "errs": {
                    "label": "IP_FORBIDDEN",
                    "message": "This message must not be exposed.",
                }
            },
        }
    )

    with pytest.raises(GatePrivateStreamAuthenticationError) as captured:
        private_login_user_id(rejected)

    assert captured.value.reason == "gate_login_ip_forbidden"
    assert "This message" not in str(captured.value)


class _FakeConnection:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.sent: list[dict[str, object]] = []
        self._wait_forever = asyncio.Event()

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str:
        if self.messages:
            return self.messages.pop(0)
        await self._wait_forever.wait()
        raise AssertionError("unreachable")


def test_private_service_marks_missing_credentials_without_connecting() -> None:
    async def scenario() -> None:
        status = PrivateStreamStateStore("live")
        stop = asyncio.Event()
        connection_attempts = 0

        @asynccontextmanager
        async def connection_factory(_: str):
            nonlocal connection_attempts
            connection_attempts += 1
            yield _FakeConnection([])

        async def stop_sleep(_: float) -> None:
            stop.set()

        service = GateFuturesPrivateWebSocketService(
            mode="live",
            credentials=lambda _: None,
            reconcile=lambda _: _snapshot(),
            persist_snapshot=lambda _: None,
            status_store=status,
            connection_factory=connection_factory,
            sleep=stop_sleep,
        )

        await service.run(stop)

        state = status.snapshot()
        assert state.status == "credentials_missing"
        assert state.connected is False
        assert state.last_error == "credentials_missing"
        assert connection_attempts == 0

    asyncio.run(scenario())


def test_private_notification_triggers_authoritative_rest_reconciliation() -> None:
    async def scenario() -> None:
        login = json.dumps(
            {
                "header": {"status": "200"},
                "data": {"result": {"uid": "20011"}},
            }
        )
        private_update = json.dumps(
            {
                "channel": "futures.balances",
                "event": "update",
                "time_ms": 1_700_000_000_000,
                "result": [{"balance": "999999"}],
            }
        )
        connection = _FakeConnection([login, private_update])

        @asynccontextmanager
        async def connection_factory(_: str):
            yield connection

        stop = asyncio.Event()
        status = PrivateStreamStateStore("live")
        reconciled: list[ExchangeSnapshot] = []
        persisted: list[ExchangeSnapshot] = []
        loop = asyncio.get_running_loop()

        def reconcile(_: str) -> ExchangeSnapshot:
            snapshot = _snapshot()
            reconciled.append(snapshot)
            return snapshot

        def persist(snapshot: ExchangeSnapshot) -> None:
            persisted.append(snapshot)
            if len(persisted) == 2:
                loop.call_soon_threadsafe(stop.set)

        service = GateFuturesPrivateWebSocketService(
            mode="live",
            credentials=lambda _: _credentials(),
            reconcile=reconcile,
            persist_snapshot=persist,
            status_store=status,
            connection_factory=connection_factory,
            heartbeat_interval_seconds=1,
            heartbeat_timeout_seconds=1,
            epoch_clock=lambda: 1_700_000_000.0,
        )

        await service.run(stop)

        state = status.snapshot()
        assert len(reconciled) == 2
        assert len(persisted) == 2
        assert all(
            snapshot.available_futures_balance == Decimal("123.45") for snapshot in persisted
        )
        assert state.status == "connected"
        assert state.connected is True
        assert state.last_event_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
        assert state.last_reconciled_at is not None
        assert set(state.subscribed_channels) == {
            "futures.balances",
            "futures.positions",
            "futures.orders",
            "futures.usertrades",
            "futures.autoorders",
        }
        assert connection.sent[0]["channel"] == "futures.login"
        assert len(connection.sent) == 6

    asyncio.run(scenario())


def test_private_service_waits_for_login_result_after_gate_acknowledgement() -> None:
    async def scenario() -> None:
        acknowledgement = json.dumps(
            {
                "ack": True,
                "header": {"status": "200", "channel": "futures.login"},
                "data": {"result": {"req_id": "rangebot-1"}},
            }
        )
        login = json.dumps(
            {
                "ack": False,
                "header": {"status": "200", "channel": "futures.login"},
                "data": {"result": {"uid": "20011"}},
            }
        )
        connection = _FakeConnection([acknowledgement, login])

        @asynccontextmanager
        async def connection_factory(_: str):
            yield connection

        stop = asyncio.Event()
        status = PrivateStreamStateStore("live")

        def persist(_: ExchangeSnapshot) -> None:
            stop.set()

        service = GateFuturesPrivateWebSocketService(
            mode="live",
            credentials=lambda _: _credentials(),
            reconcile=lambda _: _snapshot(),
            persist_snapshot=persist,
            status_store=status,
            connection_factory=connection_factory,
            epoch_clock=lambda: 1_700_000_000.0,
        )

        await service.run(stop)

        assert status.snapshot().status == "connected"
        assert [message["channel"] for message in connection.sent] == [
            "futures.login",
            "futures.balances",
            "futures.positions",
            "futures.orders",
            "futures.usertrades",
            "futures.autoorders",
        ]

    asyncio.run(scenario())
