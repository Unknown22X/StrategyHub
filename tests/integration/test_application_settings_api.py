from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_application_settings_persist_after_engine_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    payload = {
        "environment": "testnet",
        "ui_language": "ar",
        "dashboard_layout": {
            "order": ["summary", "orders", "activity"],
            "hidden": ["performance"],
            "density": "comfortable",
        },
        "dashboard_filters": {
            "environment": "current",
            "strategy_id": "strategy-1",
            "period": "7d",
            "symbol": "BTC_USDT",
            "event_type": "decision",
        },
        "sidebar_preferences": {"collapsed": True},
        "application_preferences": {"compact_mode": True},
    }

    with TestClient(create_app(database_url)) as client:
        initial = client.get("/v1/settings")
        saved = client.put("/v1/settings", json=payload)

    assert initial.status_code == 200
    assert initial.json()["environment"] == "live"
    assert saved.status_code == 200
    assert saved.json()["environment"] == "testnet"
    assert saved.json()["dashboard_layout"] == payload["dashboard_layout"]
    assert saved.json()["revision"] == 1

    with TestClient(create_app(database_url)) as restarted_client:
        restored = restarted_client.get("/v1/settings")

    assert restored.status_code == 200
    assert restored.json()["environment"] == "testnet"
    assert restored.json()["dashboard_filters"] == payload["dashboard_filters"]
    assert restored.json()["sidebar_preferences"] == payload["sidebar_preferences"]
    assert restored.json()["application_preferences"] == payload[
        "application_preferences"
    ]
    assert restored.json()["revision"] == 1


def test_application_settings_reject_credential_material(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    payload = {
        "environment": "live",
        "ui_language": "ar",
        "dashboard_layout": {},
        "dashboard_filters": {},
        "sidebar_preferences": {},
        "application_preferences": {
            "credential_reference": "sensitive-value"
        },
    }

    with TestClient(create_app(database_url)) as client:
        response = client.put("/v1/settings", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_error"


def test_settings_overview_is_available_before_paper_initialization(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        overview = client.get("/v1/settings/overview")

    assert overview.status_code == 200
    assert overview.json()["paper_risk"] is None
    assert overview.json()["paper_emergency_stop"] is None


def test_settings_overview_keeps_safety_state_typed_and_separate(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "settings overview"},
        )
        client.post(
            "/v1/paper/emergency-stop",
            json={"confirmation": "EMERGENCY STOP", "reason": "overview test"},
        )
        overview = client.get("/v1/settings/overview")

    assert overview.status_code == 200
    body = overview.json()
    assert body["application"]["environment"] == "live"
    assert body["paper_emergency_stop"]["active"] is True
    assert body["paper_risk"]["settings"]["daily_loss_limit"] == "100.00000000"
    assert Decimal(body["account_risk_policy"]["daily_loss_limit"]) == Decimal("100")
    assert body["testnet_emergency_stop"] is False
    assert body["live_emergency_stop"] is False
