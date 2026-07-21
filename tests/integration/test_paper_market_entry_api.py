from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_deprecated_paper_market_entry_is_gone_without_side_effects(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "legacy route test"},
        )
        response = client.post("/v1/paper/market-entry", json={"ignored": True})
        position = client.get("/v1/paper/position")
        account = client.get("/v1/paper-account")

    assert response.status_code == 410
    assert response.json()["code"] == "deprecated_endpoint"
    assert "/v1/manual-orders" in response.json()["detail"]
    assert position.status_code == 404
    assert account.json()["position_quantity"] == "0E-8"


def test_deprecated_paper_limit_entry_is_gone_without_pending_order(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "legacy route test"},
        )
        response = client.post("/v1/paper/limit-entry", json={"ignored": True})
        pending = client.get("/v1/paper/pending-entry-state")
        account = client.get("/v1/paper-account")

    assert response.status_code == 410
    assert response.json()["code"] == "deprecated_endpoint"
    assert "/v1/manual-orders" in response.json()["detail"]
    assert pending.status_code == 200
    assert pending.json() is None
    assert account.json()["pending_entry"] is False
