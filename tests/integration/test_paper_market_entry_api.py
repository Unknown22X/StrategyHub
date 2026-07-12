from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from rangebot.engine.api import create_app


MONEY_SCALE = Decimal("0.00000001")


def _preview_payload(direction: str = "long", quote_revision: str = "quote-1") -> dict:
    return {
        "available_futures_balance": "1000",
        "allocation_percentage": "50",
        "safety_reserve_percentage": "10",
        "leverage": 5,
        "expected_entry_price": "100",
        "quantity_step": "0.001",
        "minimum_quantity": "0.001",
        "taker_fee_rate": "0.001",
        "direction": direction,
        "quote_revision": quote_revision,
    }


@pytest.mark.parametrize(
    ("direction", "expected_fill"),
    [("long", Decimal("100.100")), ("short", Decimal("99.900"))],
)
def test_confirmed_paper_market_entry_persists_slippage_fee_and_arabic_activity(
    tmp_path, direction: str, expected_fill: Decimal
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        preview_request = _preview_payload(direction)
        preview = client.post("/v1/paper/entry-preview", json=preview_request).json()
        response = client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": preview_request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        )
        position = client.get("/v1/paper/position")
        protection = client.get("/v1/paper/position/protection")
        audit = client.get("/v1/paper-account/audit")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["position"]["entry_price"]) == expected_fill
    assert Decimal(body["position"]["entry_fee"]) > 0
    assert Decimal(body["account"]["position_quantity"]) > 0
    assert Decimal(body["account"]["available_futures_balance"]) < Decimal("1000")
    assert "مركز ورقي" in body["activity"]
    assert position.json()["direction"] == direction
    assert protection.status_code == 200
    assert protection.json()["state"] == "protected"
    assert Decimal(protection.json()["quantity"]) == Decimal(
        position.json()["quantity"]
    )
    if direction == "long":
        assert Decimal(protection.json()["take_profit_price"]) > Decimal(
            position.json()["entry_price"]
        )
        assert Decimal(protection.json()["stop_loss_price"]) < Decimal(
            position.json()["entry_price"]
        )
    else:
        assert Decimal(protection.json()["take_profit_price"]) < Decimal(
            position.json()["entry_price"]
        )
        assert Decimal(protection.json()["stop_loss_price"]) > Decimal(
            position.json()["entry_price"]
        )
    assert audit.json()[-1]["action"] == "manual_market_entry"


def test_market_entry_rejects_missing_confirmation_stale_or_unsafe_data(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        request = _preview_payload()
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        missing_confirmation = client.post(
            "/v1/paper/market-entry",
            json={"preview": preview, "current_request": request, "confirmation": "no"},
        )
        stale_request = _preview_payload(quote_revision="quote-2")
        stale = client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": stale_request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        )
        unsafe_market = client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
                "market_ready": False,
            },
        )

    assert missing_confirmation.status_code == 422
    assert stale.status_code == 422
    assert unsafe_market.status_code == 422


def test_market_entry_rejects_duplicate_and_position_survives_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    request = _preview_payload()

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        payload = {
            "preview": preview,
            "current_request": request,
            "confirmation": "CONFIRM PAPER MARKET ENTRY",
        }
        accepted = client.post("/v1/paper/market-entry", json=payload)
        duplicate = client.post("/v1/paper/market-entry", json=payload)

    with TestClient(create_app(database_url)) as restarted_client:
        account = restarted_client.get("/v1/paper-account")
        position = restarted_client.get("/v1/paper/position")

    assert accepted.status_code == 200
    assert duplicate.status_code == 409
    assert Decimal(account.json()["position_quantity"]) == Decimal(
        position.json()["quantity"]
    )


def test_take_profit_trigger_closes_the_paper_position(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    request = _preview_payload()

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        )
        protection = client.get("/v1/paper/position/protection").json()
        triggered = client.post(
            "/v1/paper/position/protection/check",
            json={"market_price": protection["take_profit_price"]},
        )
        position = client.get("/v1/paper/position")

    assert triggered.status_code == 200
    assert triggered.json()["reason"] == "take_profit"
    assert Decimal(triggered.json()["account"]["position_quantity"]) == Decimal("0")
    assert position.status_code == 404


@pytest.mark.parametrize(
    ("trigger", "fee_key"),
    [("take_profit", "maker_fee_rate"), ("stop_loss", "taker_fee_rate")],
)
def test_protection_trigger_uses_stored_fee_rate_with_decimal_accounting(
    tmp_path, trigger: str, fee_key: str
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    request = _preview_payload()
    request["taker_fee_rate"] = "0.003"

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        client.put(
            "/v1/paper/fee-schedule",
            json={"maker_fee_rate": "0.002", "taker_fee_rate": "0.003"},
        )
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        opened = client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        ).json()
        protection = client.get("/v1/paper/position/protection").json()
        exit_price = protection[
            "take_profit_price" if trigger == "take_profit" else "stop_loss_price"
        ]
        closed = client.post(
            "/v1/paper/position/protection/check", json={"market_price": exit_price}
        ).json()

    position = opened["position"]
    exit_fee = (
        Decimal(position["quantity"]) * Decimal(exit_price) * Decimal(position[fee_key])
    )
    pnl = Decimal(position["quantity"]) * (
        Decimal(exit_price) - Decimal(position["entry_price"])
    )
    expected_balance = (
        Decimal(opened["account"]["available_futures_balance"])
        + Decimal(position["allocated_margin"])
        + pnl
        - exit_fee
    ).quantize(MONEY_SCALE)
    assert closed["reason"] == trigger
    assert Decimal(closed["account"]["available_futures_balance"]) == expected_balance


def test_later_fee_schedule_change_does_not_change_open_position_rates(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    request = _preview_payload()
    request["taker_fee_rate"] = "0.003"

    with TestClient(create_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        client.put(
            "/v1/paper/fee-schedule",
            json={"maker_fee_rate": "0.002", "taker_fee_rate": "0.003"},
        )
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        client.post(
            "/v1/paper/market-entry",
            json={
                "preview": preview,
                "current_request": request,
                "confirmation": "CONFIRM PAPER MARKET ENTRY",
            },
        )
        before = client.get("/v1/paper/position").json()
        client.put(
            "/v1/paper/fee-schedule",
            json={"maker_fee_rate": "0.006", "taker_fee_rate": "0.007"},
        )
        after = client.get("/v1/paper/position").json()

    assert before["maker_fee_rate"] == after["maker_fee_rate"] == "0.00200000"
    assert before["taker_fee_rate"] == after["taker_fee_rate"] == "0.00300000"
