from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def test_range_analysis_api_returns_all_condition_details(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    opened_at = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)
    candles = [
        {
            "opened_at": (opened_at + timedelta(minutes=index)).isoformat(),
            "open": "100",
            "high": "120",
            "low": "100",
            "close": "110",
        }
        for index in range(5)
    ]

    with TestClient(create_app(database_url)) as client:
        response = client.post(
            "/v1/paper/range-analysis/evaluate",
            json={
                "config": {"timeframe_minutes": 5},
                "candles": candles,
                "last_price": "100",
                "evaluated_at": "2026-07-12T12:04:00Z",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["history_status"] == "ready"
    assert {condition["name"] for condition in payload["conditions"]} >= {
        "history",
        "range",
        "long_proximity",
        "short_proximity",
    }
    assert any(
        "جاهز" in condition["arabic_explanation"] for condition in payload["conditions"]
    )
