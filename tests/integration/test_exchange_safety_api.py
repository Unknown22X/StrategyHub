from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeSnapshot,
    MarketEntryGuardRequest,
    MarketGuardQuoteRequest,
    OrderBookLevel,
)
from rangebot.engine.api import create_app
from rangebot.engine.exchange import (
    GateIoConfiguration,
    GateIoV4Adapter,
    MockGateIoAdapter,
    UnavailableGateIoAdapter,
    configured_gate_adapter,
    entry_blocks,
    guard_market_entry,
)


def _ready_snapshot() -> dict[str, object]:
    return {
        "available_futures_balance": "1000",
        "position_quantity": "0",
        "one_way_confirmed": True,
        "cross_margin_confirmed": True,
        "leverage_confirmed": 5,
        "market_ready": True,
        "history_ready": True,
        "risk_ready": True,
        "active_contract_ready": True,
        "daily_baseline_ready": True,
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
        return ExchangeSnapshot(
            mode=mode, reconciled_at=datetime.now(UTC), **self.values
        )  # type: ignore[arg-type]

    def market_guard_quote(
        self, mode: str, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        return MarketEntryGuardRequest.model_validate(
            _market_guard_payload()
            | {"direction": request.direction, "quantity": request.quantity}
        )

    def submit_entry(
        self, mode: str, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        self.submitted.append(request)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id="mock-1",
            message_ar="تم قبول الأمر الوهمي.",
        )

    def cancel_managed_entry(self, mode: str) -> ExchangeOperationResult:
        self.cancelled_modes.append(mode)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="cancel",
            message_ar="تم إلغاء الأمر المُدار.",
        )

    def close_managed_position(self, mode: str) -> ExchangeOperationResult:
        self.closed_modes.append(mode)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="close",
            message_ar="تم طلب الإغلاق المُدار.",
        )

    def ensure_protection(self, mode: str) -> ExchangeOperationResult:
        self.protected_modes.append(mode)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="protection",
            message_ar="تم تأكيد الحماية المُدارة.",
        )


def test_live_is_locked_until_exact_confirmation_and_ready_reconciliation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        initial = client.get("/v1/exchange/live/state")
        opened_before_reconciliation = client.post(
            "/v1/live/activate", json={"confirmation": "LIVE"}
        )
        client.post("/v1/exchange/live/reconcile")
        wrong = client.post("/v1/live/activate", json={"confirmation": "live"})
        activated = client.post("/v1/live/activate", json={"confirmation": "LIVE"})

    assert initial.json()["live_locked"] is True
    assert opened_before_reconciliation.status_code == 200
    assert opened_before_reconciliation.json()["can_enter"] is False
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


def test_live_high_risk_confirmations_and_entry_uses_only_injected_adapter(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        client.post("/v1/live/activate", json={"confirmation": "LIVE"})
        rejected = client.post(
            "/v1/live/protection",
            json={"protection": "sl", "enabled": False, "confirmation": "no"},
        )
        unprotected = client.post(
            "/v1/live/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "protections_enabled": False,
            },
        )
        adapter_missing = client.post(
            "/v1/live/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "protections_enabled": False,
                "confirmation": "UNPROTECTED POSITION",
                "market_guard": _market_guard_payload(),
            },
        )

    assert rejected.status_code == 422
    assert unprotected.status_code == 422
    assert adapter_missing.status_code == 200
    assert len(adapter.submitted) == 1


def test_live_relocks_on_engine_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        assert (
            client.post("/v1/live/activate", json={"confirmation": "LIVE"}).json()[
                "live_locked"
            ]
            is False
        )
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as restarted:
        assert restarted.get("/v1/exchange/live/state").json()["live_locked"] is True


def test_live_unlock_is_independent_from_paper_and_testnet_activity(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot() | {"position_quantity": "1"})
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        opened = client.post("/v1/live/activate", json={"confirmation": "LIVE"})

    assert opened.status_code == 200
    assert opened.json()["live_locked"] is False


def test_credential_endpoint_never_returns_or_logs_secrets(
    tmp_path, monkeypatch
) -> None:
    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "rangebot.engine.api.save_gate_credentials",
        lambda mode, key, secret: saved.append((mode, key, secret)),
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(create_app(database_url)) as client:
        response = client.post(
            "/v1/exchange/credentials",
            json={
                "mode": "live",
                "api_key": "dummy-key",
                "api_secret": "dummy-secret",
            },
        )

    assert response.json() == {"mode": "live", "configured": True}
    assert "dummy-key" not in response.text
    assert "dummy-secret" not in response.text
    assert saved == [("live", "dummy-key", "dummy-secret")]


def test_testnet_execution_uses_engine_generated_identity_and_managed_actions(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        entry = client.post(
            "/v1/exchange/testnet/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": _market_guard_payload(),
            },
        )
        cancelled = client.post("/v1/exchange/testnet/cancel-entry")
        closed = client.post(
            "/v1/exchange/testnet/close", json={"confirmation": "CLOSE POSITION"}
        )
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
    stale = _ready_snapshot() | {
        "market_observed_at": datetime(2020, 1, 1, tzinfo=UTC),
        "websocket_price_updates": 1,
    }
    adapter = FakeGateAdapter(stale)
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        state = client.post("/v1/exchange/testnet/reconcile")
        entry = client.post(
            "/v1/exchange/testnet/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": _market_guard_payload(),
            },
        )

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
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": _market_guard_payload(),
            },
        )

    assert state.json()["can_enter"] is False
    assert entry.status_code == 409


def test_market_entry_uses_fresh_server_side_guard_without_client_payload(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        response = client.post(
            "/v1/exchange/testnet/entries",
            json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1"},
        )

    assert response.status_code == 200
    assert len(adapter.submitted) == 1


def test_fabricated_client_guard_cannot_bypass_server_side_market_guard(
    tmp_path,
) -> None:
    class StaleQuoteAdapter(FakeGateAdapter):
        def market_guard_quote(
            self, mode: str, request: MarketGuardQuoteRequest
        ) -> MarketEntryGuardRequest:
            stale = _market_guard_payload()
            stale["last_price_observed_at"] = "2020-01-01T00:00:00+00:00"
            stale["asks"] = [
                {
                    "price": "100.1",
                    "quantity": "1",
                    "observed_at": "2020-01-01T00:00:00+00:00",
                }
            ]
            return MarketEntryGuardRequest.model_validate(stale)

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = StaleQuoteAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        response = client.post(
            "/v1/exchange/testnet/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": _market_guard_payload(),
            },
        )

    assert response.status_code == 409
    assert adapter.submitted == []


def test_unknown_exchange_outcome_blocks_retry_with_same_identity(tmp_path) -> None:
    class UnknownAdapter(FakeGateAdapter):
        def submit_entry(
            self, mode: str, request: ExchangeEntryRequest
        ) -> ExchangeOperationResult:
            self.submitted.append(request)
            return ExchangeOperationResult(
                accepted=False,
                pending_unknown=True,
                client_request_id=request.client_request_id,
                message_ar="نتيجة غير معروفة",
            )

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = UnknownAdapter(_ready_snapshot())
    payload = {
        "symbol": "BTC_USDT",
        "direction": "long",
        "quantity": "1",
        "market_guard": _market_guard_payload(),
        "client_request_id": "stable-request",
    }
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        first = client.post("/v1/exchange/testnet/entries", json=payload)
        retry = client.post("/v1/exchange/testnet/entries", json=payload)

    assert first.status_code == 503
    assert retry.status_code == 409
    assert len(adapter.submitted) == 1


def test_transport_exception_marks_unknown_and_blocks_duplicate_retry(tmp_path) -> None:
    class TimeoutAdapter(FakeGateAdapter):
        def submit_entry(
            self, mode: str, request: ExchangeEntryRequest
        ) -> ExchangeOperationResult:
            self.submitted.append(request)
            raise TimeoutError("simulated transport timeout")

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = TimeoutAdapter(_ready_snapshot())
    payload = {
        "symbol": "BTC_USDT",
        "direction": "long",
        "quantity": "1",
        "client_request_id": "timeout-request",
    }
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        first = client.post("/v1/exchange/testnet/entries", json=payload)
        retry = client.post("/v1/exchange/testnet/entries", json=payload)

    assert first.status_code == 503
    assert retry.status_code == 409
    assert len(adapter.submitted) == 1


def test_known_exchange_rejection_is_audited_and_can_be_retried(tmp_path) -> None:
    class RejectedAdapter(FakeGateAdapter):
        def submit_entry(
            self, mode: str, request: ExchangeEntryRequest
        ) -> ExchangeOperationResult:
            self.submitted.append(request)
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="رفض حتمي من المحاكي",
            )

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = RejectedAdapter(_ready_snapshot())
    payload = {
        "symbol": "BTC_USDT",
        "direction": "long",
        "quantity": "1",
        "client_request_id": "rejected-request",
    }
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        first = client.post("/v1/exchange/testnet/entries", json=payload)
        retry = client.post("/v1/exchange/testnet/entries", json=payload)
        audit = client.get("/v1/exchange/testnet/operations")

    assert first.status_code == 503
    assert retry.status_code == 503
    assert len(adapter.submitted) == 2
    matching = [
        item for item in audit.json() if item["client_request_id"] == "rejected-request"
    ]
    assert matching[-1]["status"] == "rejected"


def test_gate_configuration_stays_engine_private_and_redacts_values(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GATE_TESTNET_KEY", "abc-secret-key")
    monkeypatch.setenv("GATE_TESTNET_SECRET", "do-not-show")

    configuration = GateIoConfiguration.from_environment("testnet")

    assert configuration.base_url.startswith("https://fx-api-testnet")
    assert "do-not-show" not in configuration.redacted_description()
    assert "abc-secret-key" not in configuration.redacted_description()


def test_configured_adapter_without_credentials_is_safe_and_offline(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GATE_TESTNET_KEY", raising=False)
    monkeypatch.delenv("GATE_TESTNET_SECRET", raising=False)

    adapter = configured_gate_adapter("testnet", enable_network=False)

    assert isinstance(adapter, UnavailableGateIoAdapter)
    assert adapter.reconcile("testnet").reconciliation_error is not None


def test_gate_v4_adapter_signs_mocked_requests_and_refuses_orders_by_default(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GATE_TESTNET_KEY", "test-key")
    monkeypatch.setenv("GATE_TESTNET_SECRET", "test-secret")
    calls: list[tuple[str, str, str, dict[str, str], str]] = []

    def transport(
        method: str,
        url: str,
        query: str,
        headers: dict[str, str],
        body: str,
    ) -> dict[str, object]:
        calls.append((method, url, query, headers, body))
        if url.endswith("accounts"):
            return {
                "available": "1000",
                "position_mode": "single",
                "margin_mode": "cross",
                "leverage": "5",
            }
        if method == "POST" and url.endswith("orders"):
            return {"id": "mock-order"}
        return []  # type: ignore[return-value]

    adapter = GateIoV4Adapter(
        GateIoConfiguration.from_environment("testnet"), transport, allow_network=True
    )
    snapshot = adapter.reconcile("testnet")
    blocked = adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="1",
            client_request_id="request-1",
        ),
    )

    assert snapshot.available_futures_balance == 1000
    assert calls[0][1].startswith("https://fx-api-testnet")
    assert calls[0][3]["KEY"] == "test-key"
    assert len(calls[0][3]["SIGN"]) == 128
    assert blocked.accepted is False

    enabled_adapter = GateIoV4Adapter(
        GateIoConfiguration.from_environment("testnet"),
        transport,
        allow_network=True,
        allow_order_submission=True,
    )
    accepted = enabled_adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="short",
            quantity="2",
            client_request_id="short-request",
        ),
    )

    assert accepted.order_id == "mock-order"
    assert '"size":"-2"' in calls[-1][4]


def test_mock_exchange_manages_partial_fill_protection_close_and_idempotency() -> None:
    adapter = MockGateIoAdapter()
    request = ExchangeEntryRequest(
        symbol="BTC_USDT", direction="long", quantity="3", client_request_id="managed-1"
    )

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


def test_mock_reconciliation_resizes_protection_after_external_reduction() -> None:
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="4",
            client_request_id="managed-2",
        ),
    )

    reduced = adapter.reconcile_external_position(Decimal("2"))
    closed = adapter.reconcile_external_position(Decimal("0"))

    assert reduced == "external_reduced"
    assert closed == "external_closed"
    assert adapter.take_profit_quantity == 0
    assert adapter.stop_loss_quantity == 0


def test_mock_limit_lifecycle_expires_or_hands_partial_fill_to_protection() -> None:
    adapter = MockGateIoAdapter()
    limit = ExchangeEntryRequest(
        symbol="BTC_USDT",
        direction="long",
        order_type="limit",
        quantity="5",
        limit_price="99",
        client_request_id="limit-1",
    )

    adapter.submit_entry("testnet", limit)
    expired = adapter.settle_limit(Decimal("0"))
    adapter.submit_entry(
        "testnet", limit.model_copy(update={"client_request_id": "limit-2"})
    )
    partial = adapter.settle_limit(Decimal("2"), Decimal("99"))

    assert expired == "expired"
    assert ("BTC_USDT", "long") in adapter.used_signals
    assert partial == "partial_filled"
    assert adapter.position_quantity == 2
    assert (adapter.take_profit_quantity, adapter.stop_loss_quantity) == (2, 2)
    assert MockGateIoAdapter.automatic_limit_price(
        "long", Decimal("100"), Decimal("2")
    ) == Decimal("98")
    assert MockGateIoAdapter.automatic_limit_price(
        "short", Decimal("100"), Decimal("2")
    ) == Decimal("102")


def test_emergency_close_stops_then_reconciles_and_closes_only_managed_state(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "live",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="1",
            client_request_id="managed-close",
        ),
    )
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        response = client.post("/v1/exchange/live/emergency-close")
        state = client.get("/v1/exchange/live/state")

    assert response.status_code == 200
    assert adapter.position_quantity == 0
    assert state.json()["emergency_stop"] is True


def test_failed_emergency_close_never_queues_a_later_close(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "live",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="2",
            client_request_id="failed-emergency-close",
        ),
    )
    adapter.manual_close_plan = [Decimal("1")]
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        result = client.post("/v1/exchange/live/emergency-close")
        adapter.manual_close_plan = [Decimal("0")]
        state = client.get("/v1/exchange/live/state")

    assert result.json()["accepted"] is False
    assert adapter.position_quantity == 1
    assert state.json()["emergency_stop"] is True


def test_emergency_stop_is_durable_even_when_cancel_raises(tmp_path) -> None:
    class FailingCancelAdapter(FakeGateAdapter):
        def cancel_managed_entry(self, mode: str) -> ExchangeOperationResult:
            raise TimeoutError("simulated cancel timeout")

    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FailingCancelAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        response = client.post("/v1/exchange/testnet/emergency-stop")
        state = client.get("/v1/exchange/testnet/state")

    assert response.status_code == 503
    assert state.json()["emergency_stop"] is True


def test_mock_unmanaged_state_is_read_only_and_blocks_mutation_until_refresh() -> None:
    adapter = MockGateIoAdapter()
    adapter.inject_unmanaged_state(position=True, order_ids=("external-tp",))

    blocked = entry_blocks(adapter.reconcile("testnet"), "testnet", False, False)
    adapter.cancel_managed_entry("testnet")

    assert blocked
    assert adapter.unmanaged_position is True
    assert adapter.unmanaged_order_ids == {"external-tp"}

    adapter.clear_unmanaged_state()

    assert not entry_blocks(adapter.reconcile("testnet"), "testnet", False, False)


def test_mock_account_configuration_and_protection_errors_gate_entries() -> None:
    adapter = MockGateIoAdapter()
    adapter.one_way_confirmed = False
    adapter.cross_margin_confirmed = False
    adapter.leverage_confirmed = None

    configuration_blocks = entry_blocks(
        adapter.reconcile("testnet"), "testnet", False, False
    )
    adapter.one_way_confirmed = True
    adapter.cross_margin_confirmed = True
    adapter.leverage_confirmed = 5
    adapter.position_quantity = Decimal("2")
    adapter.cancel_protection_externally()
    adapter.restore_protection()

    assert len(configuration_blocks) >= 2
    assert adapter.ensure_protection("testnet").accepted is True
    assert adapter.take_profit_quantity == Decimal("2")


def test_mock_daily_risk_baseline_and_active_contract_gate_entry() -> None:
    adapter = MockGateIoAdapter()
    adapter.risk_ready = False
    adapter.daily_baseline_ready = False
    adapter.active_contract = None

    blocked = entry_blocks(adapter.reconcile("testnet"), "testnet", False, False)

    assert len(blocked) >= 2


def test_mock_protection_partial_close_repeats_to_zero_without_reversal() -> None:
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="short",
            quantity="4",
            client_request_id="protected-1",
        ),
    )

    closed = adapter.protection_triggered_close(
        [Decimal("2"), Decimal("0.5"), Decimal("0")]
    )

    assert closed == "closed"
    assert adapter.position_quantity == 0
    assert adapter.closure_reason == "Protection Triggered Closure"


def test_mock_manual_close_cancels_protection_and_repeats_to_zero() -> None:
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="4",
            client_request_id="manual-close-plan",
        ),
    )
    adapter.manual_close_plan = [Decimal("2"), Decimal("0.5"), Decimal("0")]

    result = adapter.close_managed_position("testnet")

    assert result.accepted is True
    assert adapter.position_quantity == 0
    assert adapter.protection_orders() == ()
    assert adapter.cooldown_complete is False


def test_mock_tp_sl_contracts_are_reduce_only_and_sl_uses_mark_price() -> None:
    adapter = MockGateIoAdapter()
    adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="2",
            client_request_id="protected-contract",
        ),
    )

    orders = {order["kind"]: order for order in adapter.protection_orders()}

    assert orders["tp"]["order_type"] == "limit"
    assert orders["tp"]["reduce_only"] is True
    assert orders["sl"]["order_type"] == "stop_market"
    assert orders["sl"]["trigger_source"] == "mark_price"
    assert orders["sl"]["reduce_only"] is True
    assert adapter.reconcile("testnet").liquidation_price == Decimal("80")


def test_mock_automatic_used_signal_requires_cooldown_and_directional_reset() -> None:
    adapter = MockGateIoAdapter()
    adapter.start_automatic("BTC_USDT")
    adapter.consume_automatic_signal("BTC_USDT", "long")

    with pytest.raises(RuntimeError):
        adapter.consume_automatic_signal("BTC_USDT", "long")

    adapter.cooldown_complete = False
    with pytest.raises(RuntimeError):
        adapter.directional_reset("BTC_USDT", "long")

    adapter.cooldown_complete = True
    adapter.directional_reset("BTC_USDT", "long")
    adapter.consume_automatic_signal("BTC_USDT", "long")


def test_mock_restart_persists_intent_and_requires_reconnect_before_resume() -> None:
    adapter = MockGateIoAdapter()
    adapter.start_automatic("BTC_USDT")
    adapter.consume_automatic_signal("BTC_USDT", "short")

    restarted = MockGateIoAdapter.from_state(adapter.export_state())

    assert restarted.automatic_intent is True
    assert ("BTC_USDT", "short") in restarted.used_signals
    assert restarted.may_resume_automatic() is False

    restarted.confirm_reconnect()

    assert restarted.may_resume_automatic() is True


def test_api_restart_restores_mock_state_but_forces_reconnect(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    first_adapter = MockGateIoAdapter()
    first_adapter.start_automatic("BTC_USDT")
    with TestClient(
        create_app(database_url, exchange_adapter=first_adapter)
    ) as first_client:
        first_client.post("/v1/exchange/testnet/reconcile")

    restarted_adapter = MockGateIoAdapter()
    with TestClient(
        create_app(database_url, exchange_adapter=restarted_adapter)
    ) as restarted_client:
        state = restarted_client.get("/v1/exchange/testnet/state")

    assert restarted_adapter.automatic_intent is True
    assert restarted_adapter.active_contract == "BTC_USDT"
    assert restarted_adapter.may_resume_automatic() is False
    assert state.json()["snapshot"] is not None


def test_market_entry_guard_uses_correct_side_vwap_and_rejects_stale_or_slippage() -> (
    None
):
    now = datetime.now(UTC)
    allowed = guard_market_entry(
        MarketEntryGuardRequest(
            direction="long",
            quantity="2",
            last_price="100",
            last_price_observed_at=now,
            asks=[OrderBookLevel(price="100.1", quantity="2", observed_at=now)],
        )
    )
    rejected = guard_market_entry(
        MarketEntryGuardRequest(
            direction="short",
            quantity="1",
            last_price="100",
            last_price_observed_at=now,
            bids=[OrderBookLevel(price="99", quantity="1", observed_at=now)],
        )
    )
    stale = guard_market_entry(
        MarketEntryGuardRequest(
            direction="long",
            quantity="1",
            last_price="100",
            last_price_observed_at=datetime(2020, 1, 1, tzinfo=UTC),
            asks=[OrderBookLevel(price="100", quantity="1", observed_at=now)],
        )
    )

    assert allowed.allowed is True
    assert rejected.allowed is False
    assert stale.allowed is False


def test_mock_quote_endpoint_supplies_guard_used_by_entry_submission(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        quote = client.post(
            "/v1/exchange/testnet/market-guard-quote",
            json={"direction": "long", "quantity": "1"},
        )
        entry = client.post(
            "/v1/exchange/testnet/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": quote.json(),
            },
        )

    assert quote.status_code == 200
    assert entry.status_code == 200
    assert adapter.position_quantity == 1


def test_testnet_verification_is_persistent_separate_and_advisory(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        recorded = client.post(
            "/v1/exchange/testnet/verification",
            json={"evidence": "mock lifecycle complete"},
        )
        live_missing = client.get("/v1/exchange/live/verification")
    with TestClient(
        create_app(database_url, exchange_adapter=MockGateIoAdapter())
    ) as restarted:
        persisted = restarted.get("/v1/exchange/testnet/verification")

    assert recorded.status_code == 200
    assert live_missing.json() is None
    assert persisted.json()["evidence"] == "mock lifecycle complete"
    assert persisted.json()["stale"] is False


def test_live_protection_disable_persists_and_requires_unprotected_confirmation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        client.post("/v1/live/activate", json={"confirmation": "LIVE"})
        tp = client.post(
            "/v1/live/protection",
            json={
                "protection": "tp",
                "enabled": False,
                "confirmation": "DISABLE TP",
            },
        )
        sl = client.post(
            "/v1/live/protection",
            json={
                "protection": "sl",
                "enabled": False,
                "confirmation": "DISABLE SL",
            },
        )
        quote = client.post(
            "/v1/exchange/live/market-guard-quote",
            json={"direction": "long", "quantity": "1"},
        ).json()
        blocked = client.post(
            "/v1/live/entries",
            json={
                "symbol": "BTC_USDT",
                "direction": "long",
                "quantity": "1",
                "market_guard": quote,
            },
        )

    assert tp.status_code == 200
    assert sl.json()["snapshot"]["tp_enabled"] is False
    assert sl.json()["snapshot"]["sl_enabled"] is False
    assert blocked.status_code == 422


def test_database_restore_invalidates_exchange_readiness_until_reconciliation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(
        create_app(database_url, exchange_adapter=MockGateIoAdapter())
    ) as client:
        assert client.post("/v1/exchange/testnet/reconcile").json()["can_enter"]

    with TestClient(
        create_app(
            database_url,
            exchange_adapter=MockGateIoAdapter(),
            restored_state=True,
        )
    ) as restored:
        state = restored.get("/v1/exchange/testnet/state")

    assert state.json()["can_enter"] is False
    assert state.json()["snapshot"] is None


def test_emergency_resume_requires_safe_reconciliation_and_live_stays_locked(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        client.post("/v1/exchange/live/emergency-stop")
        adapter.inject_unmanaged_state(order_ids=("external-order",))
        blocked = client.post("/v1/exchange/live/resume?confirmation=RESUME")
        adapter.clear_unmanaged_state()
        resumed = client.post("/v1/exchange/live/resume?confirmation=RESUME")

    assert blocked.status_code == 409
    assert resumed.status_code == 200
    assert resumed.json()["live_locked"] is True


def test_managed_close_and_protection_operations_have_persistent_identities(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        client.post("/v1/exchange/testnet/protection/check")
        client.post(
            "/v1/exchange/testnet/close",
            json={"confirmation": "CLOSE POSITION"},
        )
        audit = client.get("/v1/exchange/testnet/operations")

    kinds = {item["kind"] for item in audit.json()}
    identities = {item["client_request_id"] for item in audit.json()}
    assert {"ensure_protection", "manual_close"}.issubset(kinds)
    assert len(identities) == len(audit.json())


def test_testnet_automatic_api_persists_intent_and_used_signal_across_restart(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        started = client.post(
            "/v1/exchange/testnet/automatic/start",
            json={"active_contract": "BTC_USDT"},
        )
        accepted = client.post(
            "/v1/exchange/testnet/automatic/signal",
            json={"symbol": "BTC_USDT", "direction": "long"},
        )
        duplicate = client.post(
            "/v1/exchange/testnet/automatic/signal",
            json={"symbol": "BTC_USDT", "direction": "long"},
        )

    restarted_adapter = MockGateIoAdapter()
    with TestClient(create_app(database_url, exchange_adapter=restarted_adapter)):
        pass

    assert started.status_code == 200
    assert accepted.status_code == 200
    assert duplicate.status_code == 409
    assert adapter.position_quantity == Decimal("1")
    assert adapter.protection_confirmed is True
    assert restarted_adapter.automatic_intent is True
    assert ("BTC_USDT", "long") in restarted_adapter.used_signals
    assert restarted_adapter.may_resume_automatic() is False
