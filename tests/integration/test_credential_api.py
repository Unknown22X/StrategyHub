import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.engine.api import create_app
from rangebot.engine.gate_private_websocket import PrivateStreamStateStore


class ReadOnlyCredentialTestAdapter:
    def reconcile(self, mode):
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
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


class ReconnectAwarePrivateStream:
    def __init__(self) -> None:
        self.reconnect_requests = 0

    def request_reconnect(self) -> None:
        self.reconnect_requests += 1

    async def run(self, stop_event: asyncio.Event) -> None:
        await stop_event.wait()


def test_status_remove_and_read_only_validation_operations(
    tmp_path, monkeypatch
) -> None:
    removed: list[str] = []
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object(),
    )
    monkeypatch.setattr(
        "rangebot.engine.api.remove_gate_credentials",
        lambda mode: removed.append(mode) or True,
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    adapter = ReadOnlyCredentialTestAdapter()
    with TestClient(
        create_app(
            database_url,
            exchange_adapter=adapter,
            credential_test_adapter_factory=lambda mode: adapter,
        )
    ) as client:
        runtime_before = client.get("/v1/runtime/environment")
        status = client.get("/v1/exchange/testnet/credentials")
        tested = client.post("/v1/exchange/testnet/credentials/test")
        deleted = client.delete("/v1/exchange/testnet/credentials")
        runtime_after = client.get("/v1/runtime/environment")

    assert status.json() == {"mode": "testnet", "configured": True}
    assert tested.status_code == 200
    assert tested.json()["valid"] is True
    assert deleted.json() == {"mode": "testnet", "configured": False}
    assert removed == ["testnet"]
    assert runtime_before.json()["active_engine_environment"] == "paper"
    assert runtime_after.json()["active_engine_environment"] == "paper"
    assert runtime_after.json()["requested_environment"] == "paper"


def test_validation_requires_saved_credential_material(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: None,
    )
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.post("/v1/exchange/live/credentials/test")

    assert response.status_code == 409


def test_credential_changes_invalidate_snapshot_and_reconnect_private_stream(
    tmp_path, monkeypatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    saved: list[str] = []
    removed: list[str] = []
    monkeypatch.setattr(
        "rangebot.engine.api.save_gate_credentials",
        lambda mode, _key, _secret: saved.append(mode),
    )
    monkeypatch.setattr(
        "rangebot.engine.api.remove_gate_credentials",
        lambda mode: removed.append(mode) or True,
    )
    status = PrivateStreamStateStore("live")
    private_stream = ReconnectAwarePrivateStream()
    adapter = ReadOnlyCredentialTestAdapter()
    key_value = "".join(("account", "-", "key"))
    secret_value = "".join(("account", "-", "credential"))

    with TestClient(
        create_app(
            database_url,
            exchange_adapter=adapter,
            exchange_adapter_mode="live",
            private_stream_state_store=status,
            private_websocket_service=private_stream,
        )
    ) as client:
        reconciled = client.post("/v1/exchange/live/reconcile")
        assert reconciled.status_code == 200
        assert reconciled.json()["snapshot"] is not None

        stored = client.post(
            "/v1/exchange/credentials",
            json={
                "mode": "live",
                "api_key": key_value,
                "api_secret": secret_value,
            },
        )
        invalidated_after_store = client.get("/v1/exchange/live/state")

        assert stored.status_code == 200
        assert invalidated_after_store.json()["snapshot"] is None
        assert invalidated_after_store.json()["can_enter"] is False
        assert private_stream.reconnect_requests == 1

        client.post("/v1/exchange/live/reconcile")
        deleted = client.delete("/v1/exchange/live/credentials")
        invalidated_after_delete = client.get("/v1/exchange/live/state")

    assert deleted.status_code == 200
    assert invalidated_after_delete.json()["snapshot"] is None
    assert invalidated_after_delete.json()["can_enter"] is False
    assert private_stream.reconnect_requests == 2
    assert saved == ["live"]
    assert removed == ["live"]
