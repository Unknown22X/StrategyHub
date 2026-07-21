from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager


NOW = datetime(2026, 7, 16, 20, 0, tzinfo=UTC)


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


def test_manual_paper_market_order_uses_central_preview_execution_and_ownership(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        initialized = client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "central order test"},
        )
        preview = client.post("/v1/manual-orders/preview", json=_market_payload())
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": _market_payload(),
                "preview_fingerprint": preview.json()["safety_fingerprint"],
            },
        )
        position = client.get("/v1/paper/position")
        account = client.get("/v1/paper-account")
        ownership = client.get(
            f"/v1/trade-ownership/order/{submitted.json()['order_id']}"
        )
        position_ownership = client.get(
            "/v1/trade-ownership/position/paper:BTC_USDT:long"
        )
        closed = client.post(
            "/v1/paper/position/close",
            json={"market_price": "65010", "confirmation": "CLOSE PAPER POSITION"},
        )
        ownership_after_close = client.get(
            "/v1/trade-ownership/position/paper:BTC_USDT:long"
        )

    assert initialized.status_code == 200
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["can_submit"] is True
    assert Decimal(preview_body["estimated_quantity"]) == Decimal("7")
    assert Decimal(preview_body["estimated_notional"]) == Decimal("455.0035")
    assert Decimal(preview_body["estimated_margin"]) == Decimal("91.0007")
    assert Decimal(preview_body["estimated_fee_rate"]) == Decimal("0.001")
    assert Decimal(preview_body["estimated_opening_fee"]) == Decimal("0.4550035")

    assert submitted.status_code == 200
    submitted_body = submitted.json()
    assert submitted_body["accepted"] is True
    assert submitted_body["origin"] == "manual"
    assert submitted_body["order_id"].startswith("paper-")

    assert position.status_code == 200
    position_body = position.json()
    assert Decimal(position_body["quantity"]) == Decimal("0.007")
    assert Decimal(position_body["entry_price"]) == Decimal("65000.5")
    assert Decimal(position_body["allocated_margin"]) == Decimal("91.0007")
    assert Decimal(position_body["entry_fee"]) == Decimal("0.4550035")
    assert Decimal(position_body["taker_fee_rate"]) == Decimal("0.001")
    assert position_body["symbol"] == "BTC_USDT"
    assert position_body["managed_by_rangebot"] is True
    assert position_body["origin"] == "manual"

    assert account.status_code == 200
    assert Decimal(account.json()["available_futures_balance"]) == Decimal(
        "908.5442965"
    )
    assert Decimal(account.json()["position_quantity"]) == Decimal("0.007")

    assert ownership.status_code == 200
    assert ownership.json()["origin"] == "manual"
    assert ownership.json()["instance_id"] is None
    assert ownership.json()["run_id"] is None
    assert ownership.json()["environment"] == "paper"
    assert ownership.json()["symbol"] == "BTC_USDT"
    assert ownership.json()["direction"] == "long"
    assert position_ownership.status_code == 200
    assert position_ownership.json()["origin"] == "manual"
    assert closed.status_code == 200
    assert ownership_after_close.status_code == 404


def test_central_paper_limit_creates_one_pending_order_without_debit(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )
    payload = {
        "environment": "paper",
        "symbol": "BTC_USDT",
        "direction": "long",
        "order_type": "limit",
        "size_mode": "quantity",
        "quantity": "7",
        "leverage": 5,
        "limit_price": "64990.0",
        "time_in_force": "gtc",
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "central limit test"},
        )
        preview = client.post("/v1/manual-orders/preview", json=payload)
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": payload,
                "preview_fingerprint": preview.json()["safety_fingerprint"],
            },
        )
        position = client.get("/v1/paper/position")
        pending = client.get("/v1/paper/pending-entry")
        pending_state = client.get("/v1/paper/pending-entry-state")
        account = client.get("/v1/paper-account")
        ownership = client.get(
            f"/v1/trade-ownership/order/{submitted.json()['order_id']}"
        )

    assert preview.status_code == 200
    assert preview.json()["can_submit"] is True
    assert submitted.status_code == 200
    assert submitted.json()["accepted"] is True
    assert "Paper Limit" in submitted.json()["message_ar"]
    assert submitted.json()["order_id"].startswith("paper-")
    assert position.status_code == 404
    assert pending.status_code == 200
    assert pending_state.status_code == 200
    assert pending_state.json() == pending.json()
    assert Decimal(pending.json()["quantity"]) == Decimal("0.007")
    assert Decimal(pending.json()["allocated_margin"]) == Decimal("90.986")
    assert Decimal(pending.json()["limit_price"]) == Decimal("64990.0")
    assert pending.json()["leverage"] == 5
    assert Decimal(pending.json()["entry_fee_rate"]) == Decimal("0.001")
    assert pending.json()["symbol"] == "BTC_USDT"
    assert pending.json()["order_id"] == submitted.json()["order_id"]
    assert pending.json()["created_at"] is not None
    assert account.json()["pending_entry"] is True
    assert Decimal(account.json()["available_futures_balance"]) == Decimal("1000")
    assert Decimal(account.json()["position_quantity"]) == Decimal("0")
    assert ownership.status_code == 200
    assert ownership.json()["origin"] == "manual"


class _PublicPaperMarket:
    def eligible_contracts(self) -> list[PublicContract]:
        return [
            PublicContract(
                symbol="BTC_USDT",
                quantity_step=Decimal("0.001"),
                minimum_quantity=Decimal("0.001"),
            )
        ]

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        return PublicMarketSnapshot(
            symbol=symbol,
            last_price=Decimal("100"),
            observed_at=datetime.now(UTC),
        )


def _legacy_preview_request() -> dict[str, object]:
    return {
        "available_futures_balance": "1000",
        "allocation_percentage": "25",
        "safety_reserve_percentage": "10",
        "leverage": 5,
        "expected_entry_price": "100",
        "quantity_step": "0.001",
        "minimum_quantity": "0.001",
        "taker_fee_rate": "0.001",
        "direction": "long",
        "quote_revision": "central-auto-1",
    }


def _start_paper_automatic(client: TestClient) -> None:
    client.put(
        "/v1/paper/risk/settings",
        json={
            "daily_loss_limit": "100",
            "losing_trade_limit": 3,
            "automatic_fill_limit": 10,
            "cooldown_seconds": 0,
        },
    )
    client.post("/v1/paper/watchlist/BTC_USDT")
    client.post("/v1/paper/watchlist/BTC_USDT/active")
    client.post("/v1/paper/automatic-trading/start")


def test_legacy_automatic_paper_market_records_central_origin_and_risk(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=_PublicPaperMarket())
    request = _legacy_preview_request()

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "central automatic test"},
        )
        _start_paper_automatic(client)
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        submitted = client.post(
            "/v1/paper/automatic-market-entry",
            json={
                "symbol": "BTC_USDT",
                "trigger_zone": "99-100",
                "direction": "long",
                "preview": preview,
                "current_request": request,
            },
        )
        risk = client.get("/v1/paper/risk")
        ownership = client.get(
            f"/v1/trade-ownership/order/{submitted.json()['order_id']}"
        )

    assert submitted.status_code == 200
    assert submitted.json()["origin"] == "legacy_automatic"
    assert submitted.json()["order_id"].startswith("paper-")
    assert risk.status_code == 200
    assert risk.json()["automatic_fills"] == 1
    assert ownership.status_code == 200
    assert ownership.json()["origin"] == "legacy_automatic"
    assert ownership.json()["instance_id"] is None
    assert ownership.json()["run_id"] is None


def test_failed_automatic_paper_validation_releases_only_current_reservation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=_PublicPaperMarket())
    request = _legacy_preview_request()

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "10", "reason": "central rejection test"},
        )
        _start_paper_automatic(client)
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        rejected = client.post(
            "/v1/paper/automatic-market-entry",
            json={
                "symbol": "BTC_USDT",
                "trigger_zone": "99-100",
                "direction": "long",
                "preview": preview,
                "current_request": request,
            },
        )
        signals = client.get("/v1/paper/used-signals")
        risk = client.get("/v1/paper/risk")
        position = client.get("/v1/paper/position")

    assert rejected.status_code == 409
    assert signals.status_code == 200
    assert signals.json() == []
    assert risk.json()["automatic_fills"] == 0
    assert position.status_code == 404


def test_automatic_paper_limit_consumes_signal_and_risk_only_on_fill(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=_PublicPaperMarket())
    request = _legacy_preview_request()
    request["direction"] = "short"

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "central automatic limit"},
        )
        _start_paper_automatic(client)
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        placed = client.post(
            "/v1/paper/automatic-limit-entry",
            json={
                "symbol": "BTC_USDT",
                "trigger_zone": "100-101",
                "preview": preview,
                "current_request": request,
                "placement_price": "100",
                "offset_percentage": "2",
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
        )
        signals_before = client.get("/v1/paper/used-signals")
        risk_before = client.get("/v1/paper/risk")
        ownership = client.get(
            f"/v1/trade-ownership/order/{placed.json()['order_id']}"
        )
        filled = client.post(
            "/v1/paper/limit-entry/check",
            json={
                "market_price": "102",
                "observed_at": datetime.now(UTC).isoformat(),
            },
        )
        signals_after = client.get("/v1/paper/used-signals")
        risk_after = client.get("/v1/paper/risk")
        position = client.get("/v1/paper/position")
        position_ownership = client.get(
            "/v1/trade-ownership/position/paper:BTC_USDT:short"
        )

    assert placed.status_code == 200
    assert placed.json()["origin"] == "legacy_automatic"
    assert placed.json()["order_id"].startswith("paper-")
    assert Decimal(placed.json()["pending_entry"]["limit_price"]) == Decimal("102")
    assert signals_before.json() == []
    assert risk_before.json()["automatic_fills"] == 0
    assert ownership.status_code == 200
    assert ownership.json()["origin"] == "legacy_automatic"

    assert filled.status_code == 200
    assert filled.json()["filled"] is True
    assert filled.json()["order_id"] == placed.json()["order_id"]
    assert filled.json()["position"]["managed_by_rangebot"] is True
    assert filled.json()["position"]["origin"] == "legacy_automatic"
    assert position.status_code == 200
    assert position.json()["symbol"] == "BTC_USDT"
    assert position.json()["managed_by_rangebot"] is True
    assert position.json()["origin"] == "legacy_automatic"
    assert position_ownership.status_code == 200
    assert position_ownership.json()["origin"] == "legacy_automatic"
    assert signals_after.json()[0]["symbol"] == "BTC_USDT"
    assert signals_after.json()[0]["trigger_zone"] == "100-101"
    assert risk_after.json()["automatic_fills"] == 1
