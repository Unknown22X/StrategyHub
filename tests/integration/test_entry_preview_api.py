from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


def _payload(quote_revision: str = "quote-1") -> dict[str, str | int]:
    return {
        "available_futures_balance": "1000",
        "allocation_percentage": "50",
        "safety_reserve_percentage": "0",
        "leverage": 5,
        "expected_entry_price": "100",
        "quantity_step": "0.001",
        "minimum_quantity": "0.001",
        "direction": "long",
        "quote_revision": quote_revision,
    }


def test_entry_preview_contract_rejects_stale_safety_state(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        preview = client.post("/v1/paper/entry-preview", json=_payload()).json()
        stale = client.post(
            "/v1/paper/entry-preview/validate",
            json={"preview": preview, "current_request": _payload("quote-2")},
        )
        current = client.post(
            "/v1/paper/entry-preview/validate",
            json={"preview": preview, "current_request": _payload()},
        )

    assert preview["can_submit"] is True
    assert stale.status_code == 409
    assert current.status_code == 200
