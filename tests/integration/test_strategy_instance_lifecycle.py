from __future__ import annotations

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


CONFIGURATION = {
    "mode": "rolling_window",
    "minimum_range_percentage": "20",
    "maximum_range_percentage": "25",
}


def _payload(name: str) -> dict[str, object]:
    return {
        "type_id": "range",
        "name": name,
        "environment": "paper",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "requested_margin": "20",
        "requested_leverage": 3,
        "configuration": CONFIGURATION,
    }


def test_pin_archive_restore_and_archived_listing_persist(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)
    with TestClient(app) as client:
        first = client.post("/v1/strategies", json=_payload("First")).json()
        second = client.post("/v1/strategies", json=_payload("Second")).json()
        pinned = client.post(f"/v1/strategies/{second['instance_id']}/pin")
        listed = client.get("/v1/strategies")
        archived = client.post(
            f"/v1/strategies/{second['instance_id']}/archive",
            json={"reason": "Not needed now"},
        )
        active_after_archive = client.get("/v1/strategies")
        archived_list = client.get("/v1/strategies/archived")

    assert pinned.status_code == 200
    assert pinned.json()["is_pinned"] is True
    assert [item["instance_id"] for item in listed.json()] == [
        second["instance_id"],
        first["instance_id"],
    ]
    assert archived.status_code == 200
    assert archived.json()["is_pinned"] is False
    assert archived.json()["archived_at"] is not None
    assert archived.json()["archive_reason"] == "Not needed now"
    assert [item["instance_id"] for item in active_after_archive.json()] == [
        first["instance_id"]
    ]
    assert archived_list.json()[0]["instance_id"] == second["instance_id"]

    restarted = create_app(database_url)
    with TestClient(restarted) as client:
        persisted = client.get("/v1/strategies/archived")
        restored = client.post(f"/v1/strategies/{second['instance_id']}/restore")
        listed_after_restore = client.get("/v1/strategies")

    assert persisted.json()[0]["archive_reason"] == "Not needed now"
    assert restored.status_code == 200
    assert restored.json()["status"] == "stopped"
    assert restored.json()["archived_at"] is None
    assert second["instance_id"] in {
        item["instance_id"] for item in listed_after_restore.json()
    }


def test_only_unused_strategy_is_permanently_deleted_and_used_strategy_archives(
    tmp_path,
) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    with TestClient(app) as client:
        unused = client.post("/v1/strategies", json=_payload("Unused")).json()
        unused_ready = client.get(
            f"/v1/strategies/{unused['instance_id']}/deletion-readiness"
        )
        deleted = client.delete(f"/v1/strategies/{unused['instance_id']}")
        missing = client.get(f"/v1/strategies/{unused['instance_id']}")

        used = client.post("/v1/strategies", json=_payload("Used")).json()
        client.post(f"/v1/strategies/{used['instance_id']}/start")
        client.post(f"/v1/strategies/{used['instance_id']}/stop")
        used_ready = client.get(
            f"/v1/strategies/{used['instance_id']}/deletion-readiness"
        )
        blocked_delete = client.delete(f"/v1/strategies/{used['instance_id']}")
        archived = client.post(f"/v1/strategies/{used['instance_id']}/archive")

    assert unused_ready.json()["can_delete"] is True
    assert unused_ready.json()["must_archive"] is False
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert used_ready.json()["can_delete"] is False
    assert used_ready.json()["must_archive"] is True
    assert "run_history_present" in used_ready.json()["reason_codes"]
    assert blocked_delete.status_code == 409
    assert "Archive it instead" in str(blocked_delete.json())
    assert archived.status_code == 200


def test_running_strategy_cannot_be_archived_and_archived_strategy_cannot_start(
    tmp_path,
) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    with TestClient(app) as client:
        strategy = client.post("/v1/strategies", json=_payload("Lifecycle")).json()
        client.post(f"/v1/strategies/{strategy['instance_id']}/start")
        blocked_archive = client.post(
            f"/v1/strategies/{strategy['instance_id']}/archive"
        )
        client.post(f"/v1/strategies/{strategy['instance_id']}/stop")
        archived = client.post(f"/v1/strategies/{strategy['instance_id']}/archive")
        blocked_start = client.post(f"/v1/strategies/{strategy['instance_id']}/start")
        blocked_pin = client.post(f"/v1/strategies/{strategy['instance_id']}/pin")

    assert blocked_archive.status_code == 409
    assert archived.status_code == 200
    assert blocked_start.status_code == 409
    assert blocked_pin.status_code == 409
