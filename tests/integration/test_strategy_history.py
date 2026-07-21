import pytest
from fastapi.testclient import TestClient

from rangebot.domain.strategy import StrategyDecisionCreate, TradeOwnershipCreate
from rangebot.engine.api import create_app
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


def _payload() -> dict[str, object]:
    return {
        "type_id": "range",
        "name": "Audited Range",
        "environment": "paper",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {"proximity_percentage": "3"},
    }


def test_strategy_history_decisions_and_trade_ownership_are_auditable(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)

    with TestClient(app) as client:
        created = client.post("/v1/strategies", json=_payload()).json()
        instance_id = created["instance_id"]
        initial_versions = client.get(
            f"/v1/strategies/{instance_id}/configuration-versions"
        )
        updated = client.put(
            f"/v1/strategies/{instance_id}",
            json={"configuration": {"proximity_percentage": "2.5"}},
        )
        versions = client.get(
            f"/v1/strategies/{instance_id}/configuration-versions"
        )
        authorize_existing_strategy_instance(client.app, instance_id)
        started = client.post(f"/v1/strategies/{instance_id}/start")
        runs = client.get(f"/v1/strategies/{instance_id}/runs")

        assert initial_versions.status_code == 200
        assert [item["revision"] for item in initial_versions.json()] == [1]
        assert updated.status_code == 200
        assert [item["revision"] for item in versions.json()] == [1, 2]
        assert versions.json()[-1]["configuration"]["proximity_percentage"] == "2.5"
        assert versions.json()[-1]["requested_margin"] == "20.000000000000"
        assert versions.json()[-1]["requested_leverage"] == 3
        assert started.json()["status"] == "running"
        assert runs.json()[0]["mode"] == "automatic"
        assert runs.json()[0]["status"] == "active"
        assert runs.json()[0]["configuration_revision"] == 2
        run_id = runs.json()[0]["run_id"]

        repository = app.state.strategy_instance_repository
        decision = repository.record_decision(
            instance_id,
            StrategyDecisionCreate(
                signal="eligible_long",
                eligible=True,
                reason_codes=("range_valid", "near_low"),
                analysis={"range_percentage": "22.4", "distance_from_low": "1.2"},
            ),
        )
        ownership = repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity="order-123",
                origin="automatic_strategy",
                instance_id=instance_id,
                run_id=run_id,
            )
        )

        decisions = client.get(f"/v1/strategies/{instance_id}/decisions")
        ownership_response = client.get("/v1/trade-ownership/order/order-123")
        stopped = client.post(f"/v1/strategies/{instance_id}/stop")
        completed_runs = client.get(f"/v1/strategies/{instance_id}/runs")
        unsafe_delete = client.delete(f"/v1/strategies/{instance_id}")

        assert decision.run_id == run_id
        assert decisions.status_code == 200
        assert decisions.json()[0]["signal"] == "eligible_long"
        assert decisions.json()[0]["reason_codes"] == ["range_valid", "near_low"]
        assert ownership.origin == "automatic_strategy"
        assert ownership_response.status_code == 200
        assert ownership_response.json()["instance_id"] == instance_id
        assert stopped.json()["status"] == "stopped"
        assert completed_runs.json()[0]["status"] == "completed"
        assert completed_runs.json()[0]["end_reason"] == "stopped"
        assert completed_runs.json()[0]["ended_at"] is not None
        assert unsafe_delete.status_code == 409


def test_decisions_require_active_run_and_trade_identity_is_unique(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)

    with TestClient(app) as client:
        instance_id = client.post("/v1/strategies", json=_payload()).json()[
            "instance_id"
        ]
        repository = app.state.strategy_instance_repository

        with pytest.raises(RuntimeError, match="active strategy run"):
            repository.record_decision(
                instance_id,
                StrategyDecisionCreate(signal="waiting", eligible=False),
            )

        manual = TradeOwnershipCreate(
            identity_kind="position",
            external_identity="position-abc",
            origin="manual",
        )
        first = repository.record_trade_ownership(manual)
        with pytest.raises(ValueError, match="already recorded"):
            repository.record_trade_ownership(manual)

        assert first.origin == "manual"
        assert first.instance_id is None
        assert client.get("/v1/trade-ownership/position/missing").status_code == 404


def test_strategy_runs_reference_the_latest_actual_configuration_version(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        created = client.post(
            "/v1/strategies",
            json={
                **_payload(),
                "requested_margin": "25",
                "requested_leverage": 4,
            },
        ).json()
        instance_id = created["instance_id"]
        authorize_existing_strategy_instance(client.app, instance_id)

        first_start = client.post(f"/v1/strategies/{instance_id}/start")
        first_runs = client.get(f"/v1/strategies/{instance_id}/runs").json()
        paused = client.post(f"/v1/strategies/{instance_id}/pause")
        second_start = client.post(f"/v1/strategies/{instance_id}/start")
        second_runs = client.get(f"/v1/strategies/{instance_id}/runs").json()
        paused_again = client.post(f"/v1/strategies/{instance_id}/pause")
        updated = client.put(
            f"/v1/strategies/{instance_id}",
            json={"requested_margin": "40", "requested_leverage": 6},
        )
        versions = client.get(
            f"/v1/strategies/{instance_id}/configuration-versions"
        ).json()
        third_start = client.post(f"/v1/strategies/{instance_id}/start")
        third_runs = client.get(f"/v1/strategies/{instance_id}/runs").json()

    assert first_start.status_code == 200
    assert paused.status_code == 200
    assert second_start.status_code == 200
    assert paused_again.status_code == 200
    assert updated.status_code == 200
    assert third_start.status_code == 200
    assert first_runs[0]["configuration_revision"] == 1
    assert second_runs[0]["configuration_revision"] == 1
    assert [item["requested_margin"] for item in versions] == [
        "25.000000000000",
        "40.000000000000",
    ]
    assert [item["requested_leverage"] for item in versions] == [4, 6]
    assert third_runs[0]["configuration_revision"] == versions[-1]["revision"]
