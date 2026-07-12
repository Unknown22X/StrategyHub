from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_runtime_state_is_persisted_through_migrations(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        health = client.get("/health")
        snapshot = client.get("/v1/runtime-state")

    assert health.status_code == 200
    assert snapshot.status_code == 200
    assert snapshot.json()["lifecycle"] == "running"
    assert snapshot.json()["last_heartbeat_at"]
    assert snapshot.json()["state_revision"] == 1

    with TestClient(create_app(database_url)) as client:
        restarted_snapshot = client.get("/v1/runtime-state")

    assert restarted_snapshot.json()["state_revision"] == 2
