from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager


def _market() -> MarketDataManager:
    manager = MarketDataManager()
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("100"),
            mark_price=Decimal("100"),
            best_bid=Decimal("99.9"),
            best_ask=Decimal("100.1"),
            observed_at=datetime.now(UTC),
            source="gate_rest",
        )
    )
    return manager


def _rules(symbol: str) -> FuturesContractRules:
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("1"),
        quantity_step=Decimal("1"),
        minimum_quantity=Decimal("1"),
        maximum_quantity=Decimal("1000"),
        maximum_market_quantity=Decimal("1000"),
        price_step=Decimal("0.1"),
        maximum_leverage=20,
        maintenance_rate=Decimal("0.005"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0005"),
    )


def test_expired_central_paper_limit_releases_order_ownership(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper-expiry.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=1)
    payload = {
        "environment": "paper",
        "symbol": "BTC_USDT",
        "direction": "long",
        "order_type": "limit",
        "size_mode": "quantity",
        "quantity": "2",
        "leverage": 5,
        "limit_price": "90",
        "time_in_force": "gtc",
        "expires_at": expires_at.isoformat(),
    }

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "expiry ownership test"},
        )
        preview = client.post("/v1/manual-orders/preview", json=payload)
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": payload,
                "preview_fingerprint": preview.json()["safety_fingerprint"],
            },
        )
        order_id = submitted.json()["order_id"]
        before = client.get(f"/v1/trade-ownership/order/{order_id}")
        expired = client.post(
            "/v1/paper/limit-entry/check",
            json={
                "market_price": "100",
                "observed_at": (expires_at + timedelta(seconds=1)).isoformat(),
            },
        )
        after = client.get(f"/v1/trade-ownership/order/{order_id}")
        position = client.get("/v1/paper/position")

    assert preview.status_code == 200
    assert submitted.status_code == 200
    assert before.status_code == 200
    assert expired.status_code == 200
    assert expired.json()["expired"] is True
    assert expired.json()["order_id"] == order_id
    assert after.status_code == 404
    assert position.status_code == 404
