from __future__ import annotations

from fastapi.testclient import TestClient

from rangebot.domain.exchange import TradingMode
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter, UnavailableGateIoAdapter


def test_dynamic_environment_switch_updates_authoritative_runtime_and_settings(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapters: dict[TradingMode, MockGateIoAdapter] = {}

    def adapter_factory(mode: TradingMode) -> MockGateIoAdapter:
        adapter = MockGateIoAdapter()
        adapters[mode] = adapter
        return adapter

    app = create_app(
        database_url,
        initial_environment="paper",
        exchange_adapter_factory=adapter_factory,
    )

    with TestClient(app) as client:
        initial = client.get("/v1/runtime/environment")
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        health = client.get("/health")
        settings = client.get("/v1/settings")

    assert initial.status_code == 200
    assert initial.json()["active_engine_environment"] == "paper"
    assert initial.json()["public_rest_environment"] == "live"
    assert initial.json()["configured_environment"] == "paper"
    assert initial.json()["transition_state"] == "ready"
    assert initial.json()["activated"] is True

    assert switched.status_code == 200
    body = switched.json()
    assert body["configured_environment"] == "testnet"
    assert body["active_engine_environment"] == "testnet"
    assert body["exchange_adapter_environment"] == "testnet"
    assert body["public_rest_environment"] == "testnet"
    assert body["credential_profile"] == "testnet"
    assert body["transition_state"] == "ready"
    assert body["activated"] is True
    assert settings.json()["environment"] == "testnet"
    assert health.json()["environment"] == body
    assert set(adapters) == {"testnet"}


def test_confirmed_environment_is_restored_authoritatively_after_restart(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(
        create_app(
            database_url,
            initial_environment="paper",
            exchange_adapter_factory=lambda mode: MockGateIoAdapter(),
        )
    ) as client:
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        assert switched.status_code == 200

    restored_modes: list[TradingMode] = []

    def restored_factory(mode: TradingMode) -> MockGateIoAdapter:
        restored_modes.append(mode)
        return MockGateIoAdapter()

    with TestClient(
        create_app(
            database_url,
            initial_environment="paper",
            exchange_adapter_factory=restored_factory,
        )
    ) as restarted_client:
        runtime = restarted_client.get("/v1/runtime/environment")

    assert runtime.status_code == 200
    assert runtime.json()["configured_environment"] == "testnet"
    assert runtime.json()["active_engine_environment"] == "testnet"
    assert runtime.json()["exchange_adapter_environment"] == "testnet"
    assert runtime.json()["activated"] is True
    assert restored_modes == ["testnet"]


def test_testnet_and_live_snapshots_do_not_leak_across_dynamic_switches(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    modes_created: list[TradingMode] = []

    def adapter_factory(mode: TradingMode) -> MockGateIoAdapter:
        modes_created.append(mode)
        return MockGateIoAdapter()

    app = create_app(
        database_url,
        initial_environment="paper",
        exchange_adapter_factory=adapter_factory,
    )

    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/runtime/environment/switch",
                json={"environment": "testnet"},
            ).status_code
            == 200
        )
        testnet_before = client.get("/v1/exchange/testnet/state")
        switched_live = client.post(
            "/v1/runtime/environment/switch",
            json={
                "environment": "live",
                "confirmation": "SWITCH TO LIVE",
            },
        )
        testnet_after = client.get("/v1/exchange/testnet/state")
        live_after = client.get("/v1/exchange/live/state")

    assert testnet_before.json()["snapshot"]["mode"] == "testnet"
    assert switched_live.status_code == 200
    assert switched_live.json()["active_engine_environment"] == "live"
    assert testnet_after.json()["snapshot"] is None
    assert live_after.json()["snapshot"]["mode"] == "live"
    assert modes_created == ["testnet", "live"]


def test_live_transition_requires_real_funds_confirmation(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    app = create_app(
        database_url,
        initial_environment="paper",
        exchange_adapter_factory=lambda mode: MockGateIoAdapter(),
    )

    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/runtime/environment/switch",
                json={"environment": "testnet"},
            ).status_code
            == 200
        )
        rejected = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "live"},
        )
        still_testnet = client.get("/v1/runtime/environment")
        accepted = client.post(
            "/v1/runtime/environment/switch",
            json={
                "environment": "live",
                "confirmation": "SWITCH TO LIVE",
            },
        )

    assert rejected.status_code == 409
    assert rejected.json()["failure_code"] == "live_confirmation_required"
    assert rejected.json()["activated"] is False
    assert still_testnet.json()["active_engine_environment"] == "testnet"
    assert accepted.status_code == 200
    assert accepted.json()["active_engine_environment"] == "live"
    assert accepted.json()["exchange_adapter_environment"] == "live"
    assert accepted.json()["activated"] is True


def test_failed_transition_keeps_previous_environment_active(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        initial_environment="paper",
        exchange_adapter_factory=lambda mode: UnavailableGateIoAdapter(),
    )

    with TestClient(app) as client:
        failed = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        runtime = client.get("/v1/runtime/environment")
        settings = client.get("/v1/settings")

    assert failed.status_code == 409
    assert failed.json()["failure_code"] == "reconciliation_failed"
    assert failed.json()["activated"] is False
    assert runtime.json()["active_engine_environment"] == "paper"
    assert runtime.json()["exchange_adapter_environment"] is None
    assert runtime.json()["transition_state"] == "failed"
    assert settings.json()["environment"] == "paper"


def test_static_adapter_reports_restart_required_instead_of_claiming_switch(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        initial_environment="live",
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
    )

    with TestClient(app) as client:
        assert client.post("/v1/exchange/live/reconcile").status_code == 200
        response = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        runtime = client.get("/v1/runtime/environment")
        settings = client.get("/v1/settings")

    assert response.status_code == 409
    assert response.json()["failure_code"] == "restart_required"
    assert response.json()["restart_required"] is True
    assert response.json()["active_engine_environment"] == "live"
    assert response.json()["requested_environment"] == "testnet"
    assert runtime.json()["transition_state"] == "restart_required"
    assert runtime.json()["activated"] is False
    assert settings.json()["environment"] == "paper"


def test_environment_switch_is_blocked_while_exchange_position_exists(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    adapter.position_quantity = 1
    app = create_app(
        database_url,
        initial_environment="live",
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
    )

    with TestClient(app) as client:
        assert client.post("/v1/exchange/live/reconcile").status_code == 200
        blocked = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "paper"},
        )
        runtime = client.get("/v1/runtime/environment")

    assert blocked.status_code == 409
    assert blocked.json()["failure_code"] == "exchange_exposure_present"
    assert runtime.json()["active_engine_environment"] == "live"
    assert runtime.json()["exchange_adapter_environment"] == "live"


def test_switch_to_paper_invalidates_previous_exchange_snapshot(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        initial_environment="live",
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
    )

    with TestClient(app) as client:
        reconciled = client.post("/v1/exchange/live/reconcile")
        before = client.get("/v1/exchange/live/state")
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "paper"},
        )
        after = client.get("/v1/exchange/live/state")

    assert reconciled.status_code == 200
    assert before.json()["snapshot"] is not None
    assert switched.status_code == 200
    assert switched.json()["active_engine_environment"] == "paper"
    assert switched.json()["exchange_adapter_environment"] is None
    assert after.json()["snapshot"] is None
