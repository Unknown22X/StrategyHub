from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeSnapshot,
    MarketEntryGuardRequest,
    OrderBookLevel,
)
from rangebot.engine.api import create_app
from rangebot.engine.exchange import GateIoConfiguration, GateIoV4Adapter, MockGateIoAdapter, guard_market_entry


def _ready_snapshot() -> dict[str, object]:
    return {
        "available_futures_balance": "1000",
        "position_quantity": "0",
        "one_way_confirmed": True,
        "cross_margin_confirmed": True,
        "leverage_confirmed": 5,
        "market_ready": True,
        "history_ready": True,
        "protection_ready": True,
        "subscription_confirmed": True,
        "rest_snapshot_confirmed": True,
        "websocket_price_updates": 2,
        "market_observed_at": datetime.now(UTC),
    }


def _market_guard_payload() -> dict[str, object]:
    now = datetime.now(UTC).isoformat()
    return {
        "direction": "long",
        "quantity": "1",
        "last_price": "100",
        "last_price_observed_at": now,
        "asks": [{"price": "100.1", "quantity": "1", "observed_at": now}],
    }


class FakeGateAdapter:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values
        self.submitted: list[ExchangeEntryRequest] = []
        self.cancelled_modes: list[str] = []
        self.closed_modes: list[str] = []
        self.protected_modes: list[str] = []

    def reconcile(self, mode: str) -> ExchangeSnapshot:
        return ExchangeSnapshot(mode=mode, reconciled_at=datetime.now(UTC), **self.values)  # type: ignore[arg-type]

    def submit_entry(self, mode: str, request: ExchangeEntryRequest) -> ExchangeOperationResult:
        self.submitted.append(request)
        return ExchangeOperationResult(accepted=True, client_request_id=request.client_request_id, order_id="mock-1", message_ar="تم قبول الأمر الوهمي.")

    def cancel_managed_entry(self, mode: str) -> ExchangeOperationResult:
        self.cancelled_modes.append(mode)
        return ExchangeOperationResult(accepted=True, client_request_id="cancel", message_ar="تم إلغاء الأمر المُدار.")

    def close_managed_position(self, mode: str) -> ExchangeOperationResult:
        self.closed_modes.append(mode)
        return ExchangeOperationResult(accepted=True, client_request_id="close", message_ar="تم طلب الإغلاق المُدار.")

    def ensure_protection(self, mode: str) -> ExchangeOperationResult:
        self.protected_modes.append(mode)
        return ExchangeOperationResult(accepted=True, client_request_id="protection", message_ar="تم تأكيد الحماية المُدارة.")


def test_live_is_locked_until_exact_confirmation_and_ready_reconciliation(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        initial = client.get("/v1/exchange/live/state")
        missing = client.post("/v1/live/activate", json={"confirmation": "LIVE"})
        client.post("/v1/exchange/live/reconcile")
        wrong = client.post("/v1/live/activate", json={"confirmation": "live"})
        activated = client.post("/v1/live/activate", json={"confirmation": "LIVE"})

    assert initial.json()["live_locked"] is True
    assert missing.status_code == 409
    assert wrong.status_code == 422
    assert activated.json()["live_locked"] is False


def test_unmanaged_state_and_emergency_stop_block_testnet_and_persist(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    unsafe = _ready_snapshot() | {"unmanaged_state": True}
    adapter = FakeGateAdapter(unsafe)
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        state = client.post("/v1/exchange/testnet/reconcile")
        stopped = client.post("/v1/exchange/testnet/emergency-stop")
    with TestClient(create_app(database_url)) as restarted:
        persisted = restarted.get("/v1/exchange/testnet/state")

    assert state.json()["can_enter"] is False
    assert "غير مُدارة" in " ".join(state.json()["blocked_reasons_ar"])
    assert stopped.json()["emergency_stop"] is True
    assert persisted.json()["emergency_stop"] is True


def test_live_high_risk_confirmations_and_entry_uses_only_injected_adapter(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        client.post("/v1/live/activate", json={"confirmation": "LIVE"})
        rejected = client.post("/v1/live/protection", json={"protection": "sl", "enabled": False, "confirmation": "no"})
        unprotected = client.post("/v1/live/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "protections_enabled": False})
        adapter_missing = client.post("/v1/live/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "protections_enabled": False, "confirmation": "UNPROTECTED POSITION", "market_guard": _market_guard_payload()})

    assert rejected.status_code == 422
    assert unprotected.status_code == 422
    assert adapter_missing.status_code == 200
    assert len(adapter.submitted) == 1


def test_live_relocks_on_engine_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        assert client.post("/v1/live/activate", json={"confirmation": "LIVE"}).json()["live_locked"] is False
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as restarted:
        assert restarted.get("/v1/exchange/live/state").json()["live_locked"] is True


def test_testnet_execution_uses_engine_generated_identity_and_managed_actions(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        entry = client.post("/v1/exchange/testnet/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "market_guard": _market_guard_payload()})
        cancelled = client.post("/v1/exchange/testnet/cancel-entry")
        closed = client.post("/v1/exchange/testnet/close", json={"confirmation": "CLOSE POSITION"})
        protection = client.post("/v1/exchange/testnet/protection/check")
        client.post("/v1/exchange/testnet/emergency-stop")

    assert entry.status_code == 200
    assert adapter.submitted[0].client_request_id
    assert cancelled.status_code == 200
    assert closed.status_code == 200
    assert protection.status_code == 200
    assert adapter.cancelled_modes == ["testnet", "testnet"]
    assert adapter.closed_modes == ["testnet"]
    assert adapter.protected_modes == ["testnet"]


def test_testnet_entry_requires_fresh_reconnect_stages(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    stale = _ready_snapshot() | {"market_observed_at": datetime(2020, 1, 1, tzinfo=UTC), "websocket_price_updates": 1}
    adapter = FakeGateAdapter(stale)
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        state = client.post("/v1/exchange/testnet/reconcile")
        entry = client.post("/v1/exchange/testnet/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "market_guard": _market_guard_payload()})

    assert state.json()["can_enter"] is False
    assert entry.status_code == 409
    assert adapter.submitted == []


def test_existing_exchange_position_blocks_new_entry_even_when_ready(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot() | {"position_quantity": "1"})
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        state = client.post("/v1/exchange/testnet/reconcile")
        entry = client.post(
            "/v1/exchange/testnet/entries",
            json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "market_guard": _market_guard_payload()},
        )

    assert state.json()["can_enter"] is False
    assert entry.status_code == 409


def test_market_entry_cannot_submit_without_guard_payload(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        response = client.post(
            "/v1/exchange/testnet/entries",
            json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1"},
        )

    assert response.status_code == 409
    assert adapter.submitted == []


def test_unknown_exchange_outcome_blocks_retry_with_same_identity(tmp_path) -> None:
    class UnknownAdapter(FakeGateAdapter):
        def submit_entry(self, mode: str, request: ExchangeEntryRequest) -> ExchangeOperationResult:
            self.submitted.append(request)
            return ExchangeOperationResult(accepted=False, pending_unknown=True, client_request_id=request.client_request_id, message_ar="نتيجة غير معروفة")

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = UnknownAdapter(_ready_snapshot())
    payload = {"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "market_guard": _market_guard_payload(), "client_request_id": "stable-request"}
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        first = client.post("/v1/exchange/testnet/entries", json=payload)
        retry = client.post("/v1/exchange/testnet/entries", json=payload)

    assert first.status_code == 503
    assert retry.status_code == 409
    assert len(adapter.submitted) == 1


def test_gate_configuration_stays_engine_private_and_redacts_values(monkeypatch) -> None:
    monkeypatch.setenv("GATE_TESTNET_KEY", "abc-secret-key")
    monkeypatch.setenv("GATE_TESTNET_SECRET", "do-not-show")

    configuration = GateIoConfiguration.from_environment("testnet")

    assert configuration.base_url.startswith("https://fx-api-testnet")
    assert "do-not-show" not in configuration.redacted_description()
    assert "abc-secret-key" not in configuration.redacted_description()


def test_gate_v4_adapter_signs_mocked_requests_and_refuses_orders_by_default(monkeypatch) -> None:
    monkeypatch.setenv("GATE_TESTNET_KEY", "test-key")
    monkeypatch.setenv("GATE_TESTNET_SECRET", "test-secret")
    calls: list[tuple[str, str, dict[str, str], str]] = []

    def transport(method: str, path: str, headers: dict[str, str], body: str) -> dict[str, object]:
        calls.append((method, path, headers, body))
        if path.endswith("accounts"):
            return {"available": "1000"}
        return []  # type: ignore[return-value]

    adapter = GateIoV4Adapter(GateIoConfiguration.from_environment("testnet"), transport, allow_network=True)
    snapshot = adapter.reconcile("testnet")
    blocked = adapter.submit_entry("testnet", ExchangeEntryRequest(symbol="BTC_USDT", direction="long", quantity="1", client_request_id="request-1"))

    assert snapshot.available_futures_balance == 1000
    assert calls[0][2]["KEY"] == "test-key"
    assert len(calls[0][2]["SIGN"]) == 128
    assert blocked.accepted is False


def test_mock_exchange_manages_partial_fill_protection_close_and_idempotency() -> None:
    adapter = MockGateIoAdapter()
    request = ExchangeEntryRequest(symbol="BTC_USDT", direction="long", quantity="3", client_request_id="managed-1")

    accepted = adapter.submit_entry("testnet", request)
    duplicate = adapter.submit_entry("testnet", request)
    adapter.apply_partial_fill(Decimal("1"))
    protected_quantity = (adapter.take_profit_quantity, adapter.stop_loss_quantity)
    protected = adapter.ensure_protection("testnet")
    closed = adapter.close_managed_position("testnet")

    assert accepted.order_id == duplicate.order_id
    assert protected_quantity == (Decimal("1"), Decimal("1"))
    assert adapter.take_profit_quantity == Decimal("0")
    assert adapter.stop_loss_quantity == Decimal("0")
    assert adapter.reconcile("testnet").position_quantity == 0
    assert protected.accepted is True
    assert closed.accepted is True


def test_mock_exchange_requires_full_reconnect_before_automatic_recovery() -> None:
    adapter = MockGateIoAdapter()
    adapter.start_automatic()
    adapter.begin_reconnect()

    assert adapter.may_resume_automatic() is False

    adapter.confirm_reconnect(websocket_updates=2)

    assert adapter.may_resume_automatic() is True


def test_market_entry_guard_uses_correct_side_vwap_and_rejects_stale_or_slippage() -> None:
    now = datetime.now(UTC)
    allowed = guard_market_entry(MarketEntryGuardRequest(direction="long", quantity="2", last_price="100", last_price_observed_at=now, asks=[OrderBookLevel(price="100.1", quantity="2", observed_at=now)]))
    rejected = guard_market_entry(MarketEntryGuardRequest(direction="short", quantity="1", last_price="100", last_price_observed_at=now, bids=[OrderBookLevel(price="99", quantity="1", observed_at=now)]))
    stale = guard_market_entry(MarketEntryGuardRequest(direction="long", quantity="1", last_price="100", last_price_observed_at=datetime(2020, 1, 1, tzinfo=UTC), asks=[OrderBookLevel(price="100", quantity="1", observed_at=now)]))

    assert allowed.allowed is True
    assert rejected.allowed is False
    assert stale.allowed is False
