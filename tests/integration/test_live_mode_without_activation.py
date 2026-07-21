from fastapi.testclient import TestClient

from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter


def test_live_requires_reconciliation_but_has_no_activation_gate(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()

    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        initial = client.get("/v1/exchange/live/state")
        removed_activation = client.post(
            "/v1/live/activate", json={"confirmation": "LIVE"}
        )
        reconciled = client.post("/v1/exchange/live/reconcile")

    assert initial.status_code == 200
    assert initial.json()["can_enter"] is False
    assert "live_locked" not in initial.json()
    assert removed_activation.status_code == 404
    assert reconciled.status_code == 200
    assert reconciled.json()["can_enter"] is True
    assert "live_locked" not in reconciled.json()


def test_live_reconciliation_state_survives_engine_restart_without_reactivation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    first_adapter = MockGateIoAdapter()

    with TestClient(create_app(database_url, exchange_adapter=first_adapter)) as client:
        reconciled = client.post("/v1/exchange/live/reconcile")
        assert reconciled.json()["can_enter"] is True

    with TestClient(
        create_app(database_url, exchange_adapter=MockGateIoAdapter())
    ) as restarted:
        state = restarted.get("/v1/exchange/live/state")

    assert state.status_code == 200
    assert state.json()["can_enter"] is True
    assert state.json()["emergency_stop"] is False
    assert "live_locked" not in state.json()


def test_emergency_stop_persists_and_safe_resume_does_not_require_live_activation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()

    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        stopped = client.post("/v1/exchange/live/emergency-stop")
        resumed = client.post("/v1/exchange/live/resume?confirmation=RESUME")

    assert stopped.status_code == 200
    assert stopped.json()["emergency_stop"] is True
    assert stopped.json()["can_enter"] is False
    assert resumed.status_code == 200
    assert resumed.json()["emergency_stop"] is False
    assert resumed.json()["can_enter"] is True
    assert "live_locked" not in resumed.json()
