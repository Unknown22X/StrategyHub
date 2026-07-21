from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, Lock
import time

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot, TradingMode
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.market_data_manager import MarketDataManager


NOW = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)


class SlowReconciliationAdapter:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.calls = 0
        self._lock = Lock()

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        with self._lock:
            self.calls += 1
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise TimeoutError("slow reconciliation test timed out")
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=Decimal("1000"),
            one_way_confirmed=True,
            cross_margin_confirmed=True,
            market_ready=True,
            history_ready=True,
            risk_ready=True,
            active_contract_ready=True,
            daily_baseline_ready=True,
            protection_ready=True,
            subscription_confirmed=True,
            rest_snapshot_confirmed=True,
        )


def _rules(symbol: str = "BTC_USDT") -> FuturesContractRules:
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("0.001"),
        quantity_step=Decimal("1"),
        minimum_quantity=Decimal("1"),
        maximum_quantity=Decimal("1000"),
        maximum_market_quantity=Decimal("500"),
        price_step=Decimal("0.1"),
        maximum_leverage=20,
        maintenance_rate=Decimal("0.005"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0005"),
    )


def _market() -> MarketDataManager:
    manager = MarketDataManager(clock=lambda: NOW)
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("65000"),
            mark_price=Decimal("64995"),
            best_bid=Decimal("64999.5"),
            best_ask=Decimal("65000.5"),
            observed_at=NOW,
            source="gate_rest",
            sequence=50,
        )
    )
    return manager


def _manual_live_payload() -> dict[str, object]:
    return {
        "environment": "live",
        "symbol": "BTC_USDT",
        "direction": "long",
        "order_type": "market",
        "size_mode": "margin",
        "margin_amount": "100",
        "leverage": 5,
        "time_in_force": "ioc",
    }


def test_manual_live_order_uses_central_manager_without_old_live_arming(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object(),
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        market_data_manager=_market(),
        contract_rules_provider=lambda symbol: _rules(symbol),
    )

    with TestClient(app) as client:
        rules = client.get("/v1/futures/contracts/BTC_USDT/rules")
        preview = client.post("/v1/manual-orders/preview", json=_manual_live_payload())

        assert rules.status_code == 200
        assert rules.json()["maximum_leverage"] == 20
        assert preview.status_code == 200
        assert preview.json()["can_submit"] is True
        assert preview.json()["uses_real_funds"] is True
        assert preview.json()["live_warning_ar"]

        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": _manual_live_payload(),
                "preview_fingerprint": preview.json()["safety_fingerprint"],
            },
        )

        assert submitted.status_code == 200
        assert submitted.json()["accepted"] is True
        assert submitted.json()["origin"] == "manual"
        assert submitted.json()["order_id"].startswith("mock-")
        ownership = client.get(
            f"/v1/trade-ownership/order/{submitted.json()['order_id']}"
        )
        assert ownership.status_code == 200
        assert ownership.json()["origin"] == "manual"
        assert ownership.json()["instance_id"] is None

    assert adapter.position_quantity == Decimal("7")
    assert adapter.protection_confirmed is True


def test_manual_preview_returns_structured_risk_errors_and_never_submits(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: None,
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    adapter.risk_ready = False
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        market_data_manager=_market(),
        contract_rules_provider=lambda symbol: _rules(symbol),
    )

    with TestClient(app) as client:
        preview = client.post("/v1/manual-orders/preview", json=_manual_live_payload())
        body = preview.json()
        codes = {issue["code"] for issue in body["validation_issues"]}
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": _manual_live_payload(),
                "preview_fingerprint": body["safety_fingerprint"],
            },
        )

    assert preview.status_code == 200
    assert body["can_submit"] is False
    assert "credentials_missing" in codes
    assert "daily_risk_limit" in codes
    assert "reconciliation_not_ready" in codes
    assert submitted.status_code == 409
    assert adapter.position_quantity == 0
    assert adapter.submissions == {}


def test_preview_uses_background_single_flight_reconciliation(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object(),
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = SlowReconciliationAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        market_data_manager=_market(),
        contract_rules_provider=lambda symbol: _rules(symbol),
    )

    with TestClient(app) as client:
        started = time.perf_counter()
        first = client.post("/v1/manual-orders/preview", json=_manual_live_payload())
        second = client.post("/v1/manual-orders/preview", json=_manual_live_payload())
        elapsed = time.perf_counter() - started

        assert first.status_code == 200
        assert second.status_code == 200
        assert elapsed < 0.5
        assert adapter.entered.wait(timeout=1)
        assert adapter.calls == 1
        first_codes = {issue["code"] for issue in first.json()["validation_issues"]}
        assert first.json()["can_submit"] is False
        assert "reconciliation_snapshot_missing" in first_codes
        assert "reconciliation_refreshing" in first_codes
        assert "reconciliation_not_ready" in first_codes

        adapter.release.set()
        deadline = time.monotonic() + 1
        readiness = client.get("/v1/exchange/live/reconciliation")
        while readiness.json()["refresh_in_progress"] and time.monotonic() < deadline:
            time.sleep(0.01)
            readiness = client.get("/v1/exchange/live/reconciliation")
        ready_preview = client.post(
            "/v1/manual-orders/preview", json=_manual_live_payload()
        )

    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True
    assert ready_preview.status_code == 200
    assert ready_preview.json()["can_submit"] is True
    assert adapter.calls == 1


def test_zero_quantity_preview_returns_guidance_and_never_calls_adapter(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object(),
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        market_data_manager=_market(),
        contract_rules_provider=lambda symbol: _rules(symbol),
    )
    request = {
        **_manual_live_payload(),
        "margin_amount": "0.01",
        "leverage": 1,
    }

    with TestClient(app) as client:
        preview = client.post("/v1/manual-orders/preview", json=request)
        body = preview.json()
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": request,
                "preview_fingerprint": body["safety_fingerprint"],
            },
        )

    codes = {issue["code"] for issue in body["validation_issues"]}
    assert preview.status_code == 200
    assert body["can_submit"] is False
    assert Decimal(body["estimated_quantity"]) == 0
    assert body["estimated_take_profit_price"] is None
    assert body["estimated_stop_loss_price"] is None
    assert Decimal(body["minimum_quantity"]) == Decimal("1")
    assert Decimal(body["minimum_notional"]) == Decimal("65.0005")
    assert Decimal(body["approximate_minimum_margin"]) == Decimal("65.0005")
    assert {"quantity_zero", "minimum_quantity", "notional_zero"} <= codes
    assert submitted.status_code == 409
    assert adapter.position_quantity == 0
    assert adapter.submissions == {}


def test_manual_order_rejects_environment_that_does_not_match_signed_adapter(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object(),
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
        market_data_manager=_market(),
        contract_rules_provider=lambda symbol: _rules(symbol),
    )

    with TestClient(app) as client:
        preview = client.post("/v1/manual-orders/preview", json=_manual_live_payload())
        body = preview.json()
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": _manual_live_payload(),
                "preview_fingerprint": body["safety_fingerprint"],
            },
        )

    codes = {issue["code"] for issue in body["validation_issues"]}
    assert preview.status_code == 200
    assert body["can_submit"] is False
    assert "adapter_mode_mismatch" in codes
    assert submitted.status_code == 409
    assert adapter.submissions == {}


def test_manual_order_request_shape_rejects_invalid_market_tif(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.post(
            "/v1/manual-orders/preview",
            json={**_manual_live_payload(), "time_in_force": "gtc"},
        )

    assert response.status_code == 422
