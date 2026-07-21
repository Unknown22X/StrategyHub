from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def _strategy_payload(name: str, symbol: str = "BTC_USDT") -> dict[str, object]:
    return {
        "type_id": "range",
        "name": name,
        "environment": "paper",
        "symbol": symbol,
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {
            "mode": "rolling_window",
            "minimum_range_percentage": "20",
            "maximum_range_percentage": "25",
        },
    }


def test_strategy_instances_persist_and_enforce_lifecycle_conflicts(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        first_response = client.post(
            "/v1/strategies", json=_strategy_payload("BTC Range")
        )
        second_response = client.post(
            "/v1/strategies", json=_strategy_payload("ETH Range", "ETH_USDT")
        )
        unknown = client.post(
            "/v1/strategies",
            json={**_strategy_payload("Unknown"), "type_id": "not_registered"},
        )

        assert first_response.status_code == 201
        assert second_response.status_code == 201
        assert unknown.status_code == 422
        first = first_response.json()
        second = second_response.json()
        assert first["environment"] == "paper"
        assert first["status"] == "stopped"

        started = client.post(f"/v1/strategies/{first['instance_id']}/start")
        conflicting_start = client.post(f"/v1/strategies/{second['instance_id']}/start")
        monitoring = client.post(f"/v1/strategies/{second['instance_id']}/monitor")
        edit_running = client.put(
            f"/v1/strategies/{first['instance_id']}",
            json={"name": "Must not change"},
        )
        delete_monitoring = client.delete(f"/v1/strategies/{second['instance_id']}")

        assert started.status_code == 200
        assert started.json()["status"] == "running"
        assert conflicting_start.status_code == 409
        assert monitoring.status_code == 200
        assert monitoring.json()["status"] == "monitoring"
        assert edit_running.status_code == 409
        assert delete_monitoring.status_code == 409

        paused = client.post(f"/v1/strategies/{first['instance_id']}/pause")
        updated = client.put(
            f"/v1/strategies/{first['instance_id']}",
            json={"name": "BTC Range Updated", "timeframe_minutes": 60},
        )
        stopped_second = client.post(f"/v1/strategies/{second['instance_id']}/stop")
        deleted_second = client.delete(f"/v1/strategies/{second['instance_id']}")
        archived_second = client.post(f"/v1/strategies/{second['instance_id']}/archive")

        assert paused.json()["status"] == "paused"
        assert updated.status_code == 200
        assert updated.json()["name"] == "BTC Range Updated"
        assert updated.json()["timeframe_minutes"] == 60
        assert stopped_second.json()["status"] == "stopped"
        assert deleted_second.status_code == 409
        assert archived_second.status_code == 200
        assert archived_second.json()["archived_at"] is not None

    with TestClient(create_app(database_url)) as restarted_client:
        restored = restarted_client.get("/v1/strategies")

    assert restored.status_code == 200
    assert len(restored.json()) == 1
    assert restored.json()[0]["instance_id"] == first["instance_id"]
    assert restored.json()[0]["status"] == "paused"
    assert restored.json()[0]["name"] == "BTC Range Updated"


def test_strategy_configuration_is_validated_on_create_and_update(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    trend_payload = {
        "type_id": "adaptive_trend",
        "name": "Invalid Trend",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {"fast_ema_period": 20, "slow_ema_period": 10},
    }

    with TestClient(create_app(database_url)) as client:
        invalid_create = client.post("/v1/strategies", json=trend_payload)
        valid = client.post(
            "/v1/strategies",
            json={
                **trend_payload,
                "name": "Valid Trend",
                "configuration": {
                    "fast_ema_period": 3,
                    "slow_ema_period": 5,
                    "adx_period": 3,
                    "atr_period": 3,
                },
            },
        )
        invalid_update = client.put(
            f"/v1/strategies/{valid.json()['instance_id']}",
            json={"configuration": {"fast_ema_period": 9, "slow_ema_period": 4}},
        )

    assert invalid_create.status_code == 422
    assert valid.status_code == 201
    assert invalid_update.status_code == 422


def test_strategy_instance_missing_resources_return_not_found(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        fetched = client.get("/v1/strategies/missing")
        started = client.post("/v1/strategies/missing/start")
        deleted = client.delete("/v1/strategies/missing")

    assert fetched.status_code == 404
    assert started.status_code == 404
    assert deleted.status_code == 404


def test_strategy_instance_can_be_duplicated_without_copying_runtime_state(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        original = client.post(
            "/v1/strategies", json=_strategy_payload("BTC Range Original")
        ).json()
        started = client.post(f"/v1/strategies/{original['instance_id']}/start")
        duplicated = client.post(
            f"/v1/strategies/{original['instance_id']}/duplicate",
            json={"name": "BTC Range Copy"},
        )
        default_named = client.post(
            f"/v1/strategies/{original['instance_id']}/duplicate",
            json={},
        )
        missing = client.post("/v1/strategies/missing/duplicate", json={})

    assert started.status_code == 200
    assert duplicated.status_code == 201
    assert duplicated.json()["instance_id"] != original["instance_id"]
    assert duplicated.json()["name"] == "BTC Range Copy"
    assert duplicated.json()["status"] == "stopped"
    assert duplicated.json()["revision"] == 1
    assert duplicated.json()["configuration"] == original["configuration"]
    assert default_named.status_code == 201
    assert default_named.json()["name"].endswith("نسخة")
    assert missing.status_code == 404
