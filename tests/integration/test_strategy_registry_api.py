from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_strategy_type_api_exposes_dynamic_range_metadata(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        listed = client.get("/v1/strategy-types")
        detail = client.get("/v1/strategy-types/range")
        missing = client.get("/v1/strategy-types/unknown")

    assert listed.status_code == 200
    assert [item["type_id"] for item in listed.json()] == [
        "adaptive_trend",
        "fixed_price_ladder",
        "range",
        "range_breakout",
    ]
    assert detail.status_code == 200
    assert detail.json()["display_name_en"] == "Range Strategy"
    assert "timeframe_minutes" in detail.json()["configuration_schema"]["properties"]
    assert detail.json()["recommended_widgets"]
    assert detail.json()["live_analysis_fields"]
    assert missing.status_code == 404
