from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_frontend_event_stream_publishes_successful_mutations(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        with client.websocket_connect("/v1/events") as websocket:
            connected = websocket.receive_json()
            initialized = client.post(
                "/v1/paper-account/initialize",
                json={"starting_balance": "1000", "reason": "event test"},
            )
            changed = websocket.receive_json()
            status = client.get("/v1/events/status")

    assert connected["category"] == "engine"
    assert connected["action"] == "frontend_connected"
    assert initialized.status_code == 200
    assert changed["category"] == "account"
    assert changed["action"] == "post"
    assert changed["resource"] == "/v1/paper-account/initialize"
    assert changed["sequence"] > connected["sequence"]
    assert status.status_code == 200
    assert status.json()["sequence"] >= changed["sequence"]


def test_structured_errors_keep_detail_and_add_machine_code(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        missing = client.get("/v1/paper/position")
        invalid = client.put("/v1/settings", json={"environment": "invalid"})

    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert isinstance(missing.json()["detail"], str)
    assert missing.json()["context"]["path"] == "/v1/paper/position"
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "request_validation_error"
    assert isinstance(invalid.json()["detail"], list)
