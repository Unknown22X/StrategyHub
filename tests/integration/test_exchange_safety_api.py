from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.engine.api import create_app


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
    }


class FakeGateAdapter:
    def __init__(self, values: dict[str, object]) -> None:
        self.values = values

    def reconcile(self, mode: str) -> ExchangeSnapshot:
        return ExchangeSnapshot(mode=mode, reconciled_at=datetime.now(UTC), **self.values)  # type: ignore[arg-type]


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


def test_live_high_risk_confirmations_and_entry_never_submit_without_adapter(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        client.post("/v1/live/activate", json={"confirmation": "LIVE"})
        rejected = client.post("/v1/live/protection", json={"protection": "sl", "enabled": False, "confirmation": "no"})
        unprotected = client.post("/v1/live/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "protections_enabled": False})
        adapter_missing = client.post("/v1/live/entries", json={"symbol": "BTC_USDT", "direction": "long", "quantity": "1", "protections_enabled": False, "confirmation": "UNPROTECTED POSITION"})

    assert rejected.status_code == 422
    assert unprotected.status_code == 422
    assert adapter_missing.status_code == 503


def test_live_relocks_on_engine_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = FakeGateAdapter(_ready_snapshot())
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/live/reconcile")
        assert client.post("/v1/live/activate", json={"confirmation": "LIVE"}).json()["live_locked"] is False
    with TestClient(create_app(database_url, exchange_adapter=adapter)) as restarted:
        assert restarted.get("/v1/exchange/live/state").json()["live_locked"] is True
