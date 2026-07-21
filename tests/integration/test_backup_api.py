from fastapi.testclient import TestClient

from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


def _strategy_payload() -> dict[str, object]:
    return {
        "type_id": "range",
        "name": "Restore Safety Strategy",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {
            "mode": "rolling_window",
            "minimum_range_percentage": "20",
            "maximum_range_percentage": "25",
        },
    }


def test_backup_api_creates_lists_restores_and_deletes_safely(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()

    with TestClient(
        create_app(
            database_url,
            exchange_adapter=adapter,
            exchange_adapter_mode="live",
        )
    ) as client:
        saved = client.put(
            "/v1/settings",
            json={"environment": "paper", "ui_language": "en"},
        )
        strategy = client.post("/v1/strategies", json=_strategy_payload()).json()
        authorize_existing_strategy_instance(client.app, strategy["instance_id"])
        client.post(f"/v1/strategies/{strategy['instance_id']}/start")
        created = client.post("/v1/backups")
        backup_name = created.json()["name"]
        client.put(
            "/v1/settings",
            json={"environment": "paper", "ui_language": "ar"},
        )

        wrong_confirmation = client.post(
            f"/v1/backups/{backup_name}/restore",
            json={"confirmation": "restore"},
        )
        restored = client.post(
            f"/v1/backups/{backup_name}/restore",
            json={"confirmation": "RESTORE RANGEBOT"},
        )
        settings = client.get("/v1/settings")
        strategies = client.get("/v1/strategies")
        live_state = client.get("/v1/exchange/live/state")
        backups = client.get("/v1/backups")
        deleted = client.delete(f"/v1/backups/{backup_name}")

    assert saved.status_code == 200
    assert created.status_code == 200
    assert created.json()["kind"] == "manual"
    assert wrong_confirmation.status_code == 422
    assert restored.status_code == 200
    assert restored.json()["restored"]["name"] == backup_name
    assert restored.json()["safety_backup"]["kind"] == "pre_restore"
    assert restored.json()["reconciled_mode"] == "live"
    assert restored.json()["reconciliation_succeeded"] is True
    assert restored.json()["emergency_stop_active"] is True
    assert settings.json()["environment"] == "paper"
    assert settings.json()["ui_language"] == "en"
    assert strategies.json()[0]["status"] == "stopped"
    assert live_state.json()["emergency_stop"] is True
    assert any(item["kind"] == "pre_restore" for item in backups.json())
    assert deleted.json()["deleted"] is True


def test_invalid_restore_does_not_change_strategy_or_emergency_state(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        strategy = client.post("/v1/strategies", json=_strategy_payload()).json()
        authorize_existing_strategy_instance(client.app, strategy["instance_id"])
        client.post(f"/v1/strategies/{strategy['instance_id']}/start")
        invalid = client.post(
            "/v1/backups/rangebot-manual-missing.db/restore",
            json={"confirmation": "RESTORE RANGEBOT"},
        )
        current_strategy = client.get(f"/v1/strategies/{strategy['instance_id']}")
        live_state = client.get("/v1/exchange/live/state")

    assert invalid.status_code == 404
    assert current_strategy.json()["status"] == "running"
    assert live_state.json()["emergency_stop"] is False
