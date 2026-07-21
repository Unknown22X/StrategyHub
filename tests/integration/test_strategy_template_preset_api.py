from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def _preset_payload(
    *, type_id: str = "adaptive_trend", name: str = "Trend Preset"
) -> dict:
    return {
        "type_id": type_id,
        "name": name,
        "description": "Editable user defaults layered over an immutable Template.",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {},
        "status": "active",
    }


def test_registered_strategies_are_immutable_templates_and_presets_keep_legacy_ids(
    tmp_path,
) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        catalog = client.get("/v1/strategy-catalog/templates")
        assert catalog.status_code == 200
        templates = catalog.json()
        adaptive = next(
            item for item in templates if item["type_id"] == "adaptive_trend"
        )
        assert adaptive["template_id"] == "builtin:adaptive_trend"
        assert adaptive["immutable"] is True
        assert adaptive["name"]
        assert adaptive["version"]

        immutable_write = client.put(
            f"/v1/strategy-catalog/templates/{adaptive['template_id']}",
            json={"name": "Mutated"},
        )
        assert immutable_write.status_code == 405

        created = client.post("/v1/strategy-presets", json=_preset_payload())
        assert created.status_code == 201, created.json()
        preset = created.json()
        assert preset["preset_id"] == preset["legacy_template_id"]
        assert preset["current_revision"] == 1

        legacy = client.get(f"/v1/strategy-templates/{preset['preset_id']}")
        assert legacy.status_code == 200
        assert legacy.json()["template_id"] == preset["preset_id"]
        assert legacy.json()["name"] == preset["name"]

        updated = client.put(
            f"/v1/strategy-presets/{preset['preset_id']}",
            json={"name": "Trend Preset v2", "timeframe_minutes": 30},
        )
        versions = client.get(f"/v1/strategy-presets/{preset['preset_id']}/versions")
        assert updated.status_code == 200
        assert updated.json()["current_revision"] == 2
        assert versions.status_code == 200
        assert [version["revision"] for version in versions.json()] == [1, 2]

        instance = client.post(
            "/v1/strategy-instances",
            json={
                "template_id": adaptive["template_id"],
                "preset_id": preset["preset_id"],
                "name": "BTC Trend Instance",
                "environment": "paper",
                "symbol": "BTC_USDT",
                "configuration_overrides": {},
            },
        )
        assert instance.status_code == 201, instance.json()
        body = instance.json()
        assert body["template_id"] == adaptive["template_id"]
        assert body["template_version"] == adaptive["version"]
        assert body["preset_id"] == preset["preset_id"]
        assert body["preset_revision"] == 2
        assert body["timeframe_minutes"] == 30
        assert body["direction"] == "both"
        assert Decimal(body["requested_margin"]) == Decimal("20")
        assert body["requested_leverage"] == 3

        duplicate = client.post(
            f"/v1/strategies/{body['instance_id']}/duplicate",
            json={"name": "BTC Trend Copy"},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["template_id"] == body["template_id"]
        assert duplicate.json()["template_version"] == body["template_version"]
        assert duplicate.json()["preset_id"] == body["preset_id"]
        assert duplicate.json()["preset_revision"] == body["preset_revision"]

        legacy_instance = client.post(
            "/v1/strategies",
            json={
                "type_id": "adaptive_trend",
                "name": "Legacy Compatible Instance",
                "environment": "paper",
                "symbol": "ETH_USDT",
                "timeframe_minutes": 15,
                "direction": "both",
                "requested_margin": "20",
                "requested_leverage": 3,
                "configuration": {},
            },
        )
        assert legacy_instance.status_code == 201
        assert legacy_instance.json()["template_id"] == "builtin:adaptive_trend"
        assert legacy_instance.json()["preset_id"] is None

        archived = client.post(f"/v1/strategy-presets/{preset['preset_id']}/archive")
        blocked_archived = client.post(
            "/v1/strategy-instances",
            json={
                "template_id": adaptive["template_id"],
                "preset_id": preset["preset_id"],
                "name": "Archived preset instance",
                "environment": "paper",
                "symbol": "SOL_USDT",
            },
        )
        assert archived.status_code == 200
        assert blocked_archived.status_code == 422
        assert "Archived Strategy Presets" in str(blocked_archived.json())


def test_instance_creation_rejects_incompatible_preset_and_template(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")

    with TestClient(app) as client:
        preset = client.post(
            "/v1/strategy-presets",
            json=_preset_payload(type_id="adaptive_trend"),
        ).json()
        incompatible = client.post(
            "/v1/strategy-instances",
            json={
                "template_id": "builtin:fixed_price_ladder",
                "preset_id": preset["preset_id"],
                "name": "Invalid lineage",
                "environment": "paper",
                "symbol": "BTC_USDT",
            },
        )

    assert incompatible.status_code == 422
    assert "not compatible" in str(incompatible.json())
