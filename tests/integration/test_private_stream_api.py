import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app
from rangebot.engine.gate_private_websocket import PrivateStreamStateStore


class _LifecyclePrivateStream:
    def __init__(self, status: PrivateStreamStateStore) -> None:
        self.status = status
        self.started = False
        self.stopped = False

    async def run(self, stop_event: asyncio.Event) -> None:
        self.started = True
        self.status.update(
            status="connected",
            connected=True,
            channels=("futures.balances", "futures.orders"),
            event_at=datetime(2026, 7, 17, 1, 0, tzinfo=UTC),
            reconciled_at=datetime(2026, 7, 17, 1, 0, 1, tzinfo=UTC),
        )
        await stop_event.wait()
        self.stopped = True


def test_private_stream_lifecycle_and_sanitized_status_endpoint(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    status = PrivateStreamStateStore("live")
    service = _LifecyclePrivateStream(status)

    with TestClient(
        create_app(
            database_url,
            exchange_adapter_mode="live",
            private_stream_state_store=status,
            private_websocket_service=service,
        )
    ) as client:
        response = client.get("/v1/exchange/private-stream")

        assert service.started is True
        assert response.status_code == 200
        assert response.json() == {
            "mode": "live",
            "status": "connected",
            "connected": True,
            "subscribed_channels": ["futures.balances", "futures.orders"],
            "last_event_at": "2026-07-17T01:00:00Z",
            "last_reconciled_at": "2026-07-17T01:00:01Z",
            "last_error": None,
            "revision": 2,
        }

    assert service.stopped is True


def test_private_stream_is_explicitly_disabled_when_not_configured(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.get("/v1/exchange/private-stream")

    assert response.status_code == 200
    assert response.json()["status"] == "disabled"
    assert response.json()["connected"] is False
    assert response.json()["mode"] is None
