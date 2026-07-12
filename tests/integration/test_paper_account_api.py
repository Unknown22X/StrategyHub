from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_paper_account_initializes_without_exchange_credentials(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1250", "reason": "Paper setup"},
        )
        account = client.get("/v1/paper-account")

    assert response.status_code == 200
    assert account.status_code == 200
    assert account.json()["mode"] == "paper"
    assert Decimal(account.json()["starting_balance"]) == Decimal("1250")
    assert Decimal(account.json()["available_futures_balance"]) == Decimal("1250")
    assert "credential" not in account.text.lower()


def test_paper_account_reset_requires_confirmation_and_safe_state(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        missing_confirmation = client.post(
            "/v1/paper-account/reset",
            json={"starting_balance": "900", "reason": "reconfigure"},
        )
        reset = client.post(
            "/v1/paper-account/reset",
            json={
                "starting_balance": "900",
                "reason": "reconfigure",
                "confirmation": "RESET PAPER ACCOUNT",
            },
        )
        audit = client.get("/v1/paper-account/audit")

    assert missing_confirmation.status_code == 422
    assert reset.status_code == 200
    assert Decimal(reset.json()["starting_balance"]) == Decimal("900")
    assert [entry["action"] for entry in audit.json()] == ["initialized", "reset"]


def test_paper_account_persists_after_restart_and_rejects_unsafe_reset(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)

    with TestClient(app) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        app.state.paper_repository.set_position_quantity(Decimal("1"))
        rejected = client.post(
            "/v1/paper-account/reset",
            json={
                "starting_balance": "900",
                "reason": "unsafe reset",
                "confirmation": "RESET PAPER ACCOUNT",
            },
        )

    with TestClient(create_app(database_url)) as client:
        account = client.get("/v1/paper-account")
        audit = client.get("/v1/paper-account/audit")

    assert rejected.status_code == 409
    assert Decimal(account.json()["position_quantity"]) == Decimal("1")
    assert audit.json()[-1]["action"] == "reset_rejected"
