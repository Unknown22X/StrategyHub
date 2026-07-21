from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager


NOW = datetime(2026, 7, 17, 9, 0, tzinfo=UTC)


def _market() -> MarketDataManager:
    manager = MarketDataManager(clock=lambda: NOW)
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("65000"),
            mark_price=Decimal("64995"),
            best_bid=Decimal("64999.5"),
            best_ask=Decimal("65000.5"),
            observed_at=NOW,
            source="gate_rest",
            sequence=50,
        )
    )
    return manager


def _rules(symbol: str) -> FuturesContractRules:
    return FuturesContractRules(
        symbol=symbol,
        contract_multiplier=Decimal("0.001"),
        quantity_step=Decimal("1"),
        minimum_quantity=Decimal("1"),
        maximum_quantity=Decimal("1000"),
        maximum_market_quantity=Decimal("500"),
        price_step=Decimal("0.1"),
        maximum_leverage=20,
        maintenance_rate=Decimal("0.005"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0005"),
    )


def _market_payload() -> dict[str, object]:
    return {
        "environment": "paper",
        "symbol": "BTC_USDT",
        "direction": "long",
        "order_type": "market",
        "size_mode": "margin",
        "margin_amount": "100",
        "leverage": 5,
        "time_in_force": "ioc",
    }


def _open_market_position(client: TestClient) -> None:
    preview = client.post("/v1/manual-orders/preview", json=_market_payload())
    assert preview.status_code == 200
    submitted = client.post(
        "/v1/manual-orders",
        json={
            "request": _market_payload(),
            "preview_fingerprint": preview.json()["safety_fingerprint"],
        },
    )
    assert submitted.status_code == 200


def test_paper_performance_tracks_entry_mark_and_close(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper-performance.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        initialized = client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "performance test"},
        )
        _open_market_position(client)
        marked = client.post(
            "/v1/paper/position/protection/check",
            json={"market_price": "65100"},
        )
        closed = client.post(
            "/v1/paper/position/close",
            json={"market_price": "65100", "confirmation": "CLOSE PAPER POSITION"},
        )
        account = client.get("/v1/paper-account")
        performance = client.get("/v1/performance/account/paper?period=all")

    assert initialized.status_code == 200
    assert marked.status_code == 200
    assert marked.json()["triggered"] is False
    assert closed.status_code == 200
    assert account.status_code == 200
    account_body = account.json()
    assert Decimal(account_body["realized_pnl_total"]) == Decimal("0.6965")
    assert Decimal(account_body["fees_total"]) == Decimal("0.9107035")
    assert Decimal(account_body["funding_total"]) == Decimal("0")
    assert Decimal(account_body["net_pnl_total"]) == Decimal("-0.2142035")

    assert performance.status_code == 200
    body = performance.json()
    assert body["mode"] == "paper"
    assert len(body["points"]) >= 3
    assert Decimal(body["baseline_equity"]) == Decimal("1000")
    assert Decimal(body["ending_equity"]) == Decimal("999.7857965")
    assert Decimal(body["equity_change"]) == Decimal("-0.2142035")
    assert Decimal(body["realized_pnl_total"]) == Decimal("0.6965")
    assert Decimal(body["fees_total"]) == Decimal("0.9107035")
    assert Decimal(body["funding_total"]) == Decimal("0")
    assert Decimal(body["net_pnl_total"]) == Decimal("-0.2142035")
    assert Decimal(body["open_exposure"]) == Decimal("0")
    marked_points = [
        point
        for point in body["points"]
        if Decimal(point["unrealized_pnl"]) == Decimal("0.6965")
    ]
    assert marked_points


def test_paper_performance_survives_restart_and_reset_starts_new_history(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper-performance-restart.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )
    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "restart test"},
        )
        _open_market_position(client)
        client.post(
            "/v1/paper/position/close",
            json={"market_price": "65100", "confirmation": "CLOSE PAPER POSITION"},
        )

    with TestClient(create_app(database_url)) as client:
        persisted = client.get("/v1/performance/account/paper?period=all")
        reset = client.post(
            "/v1/paper-account/reset",
            json={
                "starting_balance": "500",
                "reason": "start a new Paper history",
                "confirmation": "RESET PAPER ACCOUNT",
            },
        )
        after_reset = client.get("/v1/performance/account/paper?period=all")

    assert persisted.status_code == 200
    assert len(persisted.json()["points"]) >= 3
    assert reset.status_code == 200
    assert Decimal(reset.json()["starting_balance"]) == Decimal("500")
    assert after_reset.status_code == 200
    reset_body = after_reset.json()
    assert len(reset_body["points"]) == 1
    assert Decimal(reset_body["baseline_equity"]) == Decimal("500")
    assert Decimal(reset_body["ending_equity"]) == Decimal("500")
    assert Decimal(reset_body["realized_pnl_total"]) == Decimal("0")
    assert Decimal(reset_body["fees_total"]) == Decimal("0")
