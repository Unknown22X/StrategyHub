from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from rangebot.domain.exchange import TradingMode
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.market_data_manager import MarketDataManager


def _market_update(sequence: int = 1) -> MarketPriceUpdate:
    return MarketPriceUpdate(
        symbol="BTC_USDT",
        last_price=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        best_bid=Decimal("99.9"),
        best_ask=Decimal("100.1"),
        volume_24h=Decimal("1000000"),
        observed_at=datetime.now(UTC),
        source="gate_rest",
        sequence=sequence,
    )


def _market() -> MarketDataManager:
    manager = MarketDataManager()
    manager.apply_rest_snapshot(_market_update())
    return manager


def _rules(symbol: str) -> FuturesContractRules:
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("1"),
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


def _manual_payload(environment: str) -> dict[str, object]:
    return {
        "environment": environment,
        "symbol": "BTC_USDT",
        "direction": "long",
        "order_type": "market",
        "size_mode": "quantity",
        "quantity": "2",
        "leverage": 5,
        "time_in_force": "ioc",
    }


def _submit_previewed(client: TestClient, payload: dict[str, object]) -> dict:
    preview = client.post("/v1/manual-orders/preview", json=payload)
    assert preview.status_code == 200, preview.json()
    assert preview.json()["can_submit"] is True, preview.json()
    submitted = client.post(
        "/v1/manual-orders",
        json={
            "request": payload,
            "preview_fingerprint": preview.json()["safety_fingerprint"],
        },
    )
    assert submitted.status_code == 200, submitted.json()
    assert submitted.json()["accepted"] is True
    return submitted.json()


def test_paper_full_lifecycle_verifies_preview_position_tp_sl_and_manual_close(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper.db'}"
    app = create_app(
        database_url,
        initial_environment="paper",
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        runtime = client.get("/v1/runtime/environment")
        initialized = client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "P0.5 lifecycle"},
        )
        submitted = _submit_previewed(client, _manual_payload("paper"))
        position = client.get("/v1/paper/position")
        protection = client.get("/v1/paper/position/protection")
        closed = client.post(
            "/v1/paper/position/close",
            json={"market_price": "101", "confirmation": "CLOSE PAPER POSITION"},
        )
        position_after_close = client.get("/v1/paper/position")

    assert runtime.status_code == 200
    assert runtime.json()["active_engine_environment"] == "paper"
    assert runtime.json()["exchange_adapter_environment"] is None
    assert runtime.json()["public_rest_environment"] == "live"
    assert initialized.status_code == 200
    assert submitted["environment"] == "paper"
    assert submitted["preview"]["uses_real_funds"] is False
    assert position.status_code == 200
    assert Decimal(position.json()["quantity"]) == Decimal("2")
    assert position.json()["managed_by_rangebot"] is True
    assert protection.status_code == 200
    assert Decimal(protection.json()["quantity"]) == Decimal("2")
    assert protection.json()["take_profit_price"] is not None
    assert protection.json()["stop_loss_price"] is not None
    assert Decimal(protection.json()["take_profit_price"]) > Decimal(
        position.json()["entry_price"]
    )
    assert Decimal(protection.json()["stop_loss_price"]) < Decimal(
        position.json()["entry_price"]
    )
    assert closed.status_code == 200
    assert Decimal(closed.json()["account"]["position_quantity"]) == Decimal("0")
    assert position_after_close.status_code == 404


@pytest.mark.parametrize("protection_kind", ("take_profit", "stop_loss"))
def test_paper_tp_and_sl_each_close_the_simulated_position(
    tmp_path,
    protection_kind: str,
) -> None:
    database_url = f"sqlite:///{tmp_path / f'paper-{protection_kind}.db'}"
    app = create_app(
        database_url,
        initial_environment="paper",
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": protection_kind},
        )
        _submit_previewed(client, _manual_payload("paper"))
        protection = client.get("/v1/paper/position/protection")
        level = Decimal(protection.json()[f"{protection_kind}_price"])
        trigger_price = (
            level + Decimal("1")
            if protection_kind == "take_profit"
            else level - Decimal("1")
        )
        triggered = client.post(
            "/v1/paper/position/protection/check",
            json={"market_price": str(trigger_price)},
        )
        position_after = client.get("/v1/paper/position")

    assert protection.status_code == 200
    assert protection.json()[f"{protection_kind}_price"] is not None
    assert triggered.status_code == 200
    assert triggered.json()["triggered"] is True
    assert triggered.json()["reason"] == protection_kind
    assert Decimal(triggered.json()["account"]["position_quantity"]) == Decimal("0")
    assert position_after.status_code == 404


def test_testnet_full_lifecycle_uses_only_testnet_adapter_and_no_live_funds(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object() if mode == "testnet" else None,
    )
    database_url = f"sqlite:///{tmp_path / 'testnet.db'}"
    adapters: dict[TradingMode, MockGateIoAdapter] = {}
    credential_test_modes: list[TradingMode] = []

    def adapter_factory(mode: TradingMode) -> MockGateIoAdapter:
        adapter = MockGateIoAdapter()
        adapters[mode] = adapter
        return adapter

    def credential_test_factory(mode: TradingMode) -> MockGateIoAdapter:
        credential_test_modes.append(mode)
        return MockGateIoAdapter()

    app = create_app(
        database_url,
        initial_environment="paper",
        exchange_adapter_factory=adapter_factory,
        credential_test_adapter_factory=credential_test_factory,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        initial = client.get("/v1/runtime/environment")
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        # Environment switching intentionally invalidates the previous feed state;
        # this update represents the first Testnet REST/WebSocket snapshot.
        app.state.market_data_manager.apply_rest_snapshot(_market_update(sequence=2))
        credentials = client.get("/v1/exchange/testnet/credentials")
        credential_test = client.post("/v1/exchange/testnet/credentials/test")
        reconciled = client.post("/v1/exchange/testnet/reconcile")
        readiness = client.get("/v1/exchange/testnet/reconciliation")
        submitted = _submit_previewed(client, _manual_payload("testnet"))
        state = client.get("/v1/exchange/testnet/state")
        protection_orders = adapters["testnet"].protection_orders()
        protection_check = client.post("/v1/exchange/testnet/protection/check")
        closed = client.post(
            "/v1/exchange/testnet/close",
            json={"confirmation": "CLOSE POSITION"},
        )
        final_state = client.get("/v1/exchange/testnet/state")
        live_state = client.get("/v1/exchange/live/state")

    assert initial.json()["active_engine_environment"] == "paper"
    assert switched.status_code == 200
    assert switched.json()["active_engine_environment"] == "testnet"
    assert switched.json()["exchange_adapter_environment"] == "testnet"
    assert switched.json()["public_rest_environment"] == "testnet"
    assert switched.json()["credential_profile"] == "testnet"
    assert credentials.json() == {"mode": "testnet", "configured": True}
    assert credential_test.status_code == 200
    assert credential_test.json()["valid"] is True
    assert credential_test_modes == ["testnet"]
    assert reconciled.status_code == 200
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True
    assert submitted["environment"] == "testnet"
    assert submitted["preview"]["uses_real_funds"] is False
    assert state.status_code == 200
    assert Decimal(state.json()["snapshot"]["position_quantity"]) == Decimal("2")
    assert state.json()["snapshot"]["protection_ready"] is True
    assert state.json()["snapshot"]["tp_enabled"] is True
    assert state.json()["snapshot"]["sl_enabled"] is True
    assert {order["kind"] for order in protection_orders} == {"tp", "sl"}
    assert all(order["reduce_only"] is True for order in protection_orders)
    assert all(
        Decimal(order["quantity"]) == Decimal("2") for order in protection_orders
    )
    assert protection_check.status_code == 200
    assert protection_check.json()["accepted"] is True
    assert closed.status_code == 200
    assert final_state.status_code == 200
    assert Decimal(final_state.json()["snapshot"]["position_quantity"]) == Decimal("0")
    assert set(adapters) == {"testnet"}
    assert live_state.status_code == 200
    assert live_state.json()["snapshot"] is None
