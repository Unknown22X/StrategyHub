from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager


class _PublicMarket:
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


def _market_data() -> MarketDataManager:
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
            sequence=1,
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
        taker_fee_rate=Decimal("0.001"),
    )


def _app(database_url: str, public_market_provider=None):
    return create_app(
        database_url,
        public_market_provider=public_market_provider,
        market_data_manager=_market_data(),
        contract_rules_provider=_rules,
    )


def _manual_payload(
    direction: str = "long",
    *,
    order_type: str = "market",
    expires_at: datetime | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "environment": "paper",
        "symbol": "BTC_USDT",
        "direction": direction,
        "order_type": order_type,
        "size_mode": "quantity",
        "quantity": "7",
        "leverage": 5,
        "time_in_force": "ioc" if order_type == "market" else "gtc",
    }
    if order_type == "limit":
        payload["limit_price"] = "99"
        payload["expires_at"] = (
            expires_at or datetime.now(UTC) + timedelta(minutes=1)
        ).isoformat()
    return payload


def _submit_market(client: TestClient, direction: str = "long"):
    payload = _manual_payload(direction)
    preview = client.post("/v1/manual-orders/preview", json=payload)
    assert preview.status_code == 200
    return client.post(
        "/v1/manual-orders",
        json={
            "request": payload,
            "preview_fingerprint": preview.json()["safety_fingerprint"],
        },
    )


def _open_market(client: TestClient, direction: str = "long") -> dict:
    submitted = _submit_market(client, direction)
    assert submitted.status_code == 200
    position = client.get("/v1/paper/position")
    assert position.status_code == 200
    return position.json()


def _preview_request(direction: str = "long") -> dict:
    return {
        "available_futures_balance": "1000",
        "allocation_percentage": "25",
        "safety_reserve_percentage": "10",
        "leverage": 5,
        "expected_entry_price": "100",
        "quantity_step": "0.001",
        "minimum_quantity": "0.001",
        "taker_fee_rate": "0.001",
        "direction": direction,
        "quote_revision": "quote-1",
    }


def _create_limit(client: TestClient, expires_at: datetime | None = None) -> dict:
    payload = _manual_payload(order_type="limit", expires_at=expires_at)
    preview = client.post("/v1/manual-orders/preview", json=payload)
    assert preview.status_code == 200
    response = client.post(
        "/v1/manual-orders",
        json={
            "request": payload,
            "preview_fingerprint": preview.json()["safety_fingerprint"],
        },
    )
    assert response.status_code == 200
    return payload


def test_manual_close_cancels_protection_and_keeps_stale_controls_available(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        _open_market(client)
        closed = client.post(
            "/v1/paper/position/close",
            json={"market_price": "101", "confirmation": "CLOSE PAPER POSITION"},
        )

    assert closed.status_code == 200
    assert Decimal(closed.json()["account"]["position_quantity"]) == Decimal("0")


def test_partial_close_preserves_remaining_protection_and_rejects_reversal(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        opened = _open_market(client)
        quantity = Decimal(opened["quantity"])
        partial = client.post(
            "/v1/paper/position/close",
            json={
                "market_price": "101",
                "quantity": str(quantity / 2),
                "confirmation": "CLOSE PAPER POSITION",
            },
        )
        position = client.get("/v1/paper/position")
        protection = client.get("/v1/paper/position/protection")
        account = client.get("/v1/paper-account")
        oversized = client.post(
            "/v1/paper/position/close",
            json={
                "market_price": "101",
                "quantity": str(quantity),
                "confirmation": "CLOSE PAPER POSITION",
            },
        )

    assert partial.status_code == 200
    assert Decimal(position.json()["quantity"]) == quantity / 2
    assert Decimal(protection.json()["quantity"]) == quantity / 2
    assert account.json()["cooldown_until"] is None
    assert oversized.status_code == 422


def test_risk_cooldown_persists_after_full_close_and_blocks_new_entries(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        client.put(
            "/v1/paper/risk/settings",
            json={
                "daily_loss_limit": "100",
                "losing_trade_limit": 3,
                "automatic_fill_limit": 10,
                "cooldown_seconds": 300,
            },
        )
        _open_market(client)
        client.post(
            "/v1/paper/position/close",
            json={"market_price": "100", "confirmation": "CLOSE PAPER POSITION"},
        )
    with TestClient(_app(database_url)) as restarted:
        risk = restarted.get("/v1/paper/risk")
        blocked = _submit_market(restarted)

    assert risk.json()["cooldown_until"] is not None
    assert blocked.status_code == 503, blocked.json()
    assert blocked.json()["code"] == "service_unavailable"


def test_limit_lifecycle_and_risk_block_keep_cancel_available(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        _create_limit(client)
        waiting = client.post(
            "/v1/paper/limit-entry/check",
            json={"market_price": "100", "observed_at": datetime.now(UTC).isoformat()},
        )
        filled = client.post(
            "/v1/paper/limit-entry/check",
            json={"market_price": "99", "observed_at": datetime.now(UTC).isoformat()},
        )

    assert waiting.json()["filled"] is False
    assert filled.json()["filled"] is True
    assert Decimal(filled.json()["position"]["entry_price"]) == Decimal("99")


def test_expired_limit_marks_signal_used_and_emergency_stop_cancels_pending(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        expires_at = datetime.now(UTC) + timedelta(seconds=1)
        _create_limit(client, expires_at)
        expired = client.post(
            "/v1/paper/limit-entry/check",
            json={
                "market_price": "100",
                "observed_at": (expires_at + timedelta(seconds=1)).isoformat(),
            },
        )
        _create_limit(client)
        stopped = client.post(
            "/v1/paper/emergency-stop",
            json={"confirmation": "EMERGENCY STOP", "reason": "operator request"},
        )
        pending = client.get("/v1/paper/pending-entry")
        resume = client.post(
            "/v1/paper/emergency-stop/resume",
            json={"confirmation": "RESUME"},
        )

    assert expired.json()["expired"] is True
    assert stopped.json()["active"] is True
    assert pending.status_code == 404
    assert resume.json()["active"] is False


def test_daily_risk_blocks_entry_but_not_pending_cancellation(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        _create_limit(client)
        client.put(
            "/v1/paper/risk/settings",
            json={
                "daily_loss_limit": "1",
                "losing_trade_limit": 3,
                "automatic_fill_limit": 10,
                "cooldown_seconds": 60,
            },
        )
        client.post(
            "/v1/paper/risk/adjust",
            json={"realized_pnl": "-2", "fees": "0", "funding": "0"},
        )
        blocked = _submit_market(client)
        cancelled = client.delete("/v1/paper/pending-entry")

    assert blocked.status_code == 409, blocked.json()
    assert cancelled.status_code == 200


def test_profile_help_and_verification_are_isolated_and_advisory(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    with TestClient(_app(database_url)) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        rejected = client.post(
            "/v1/paper/profiles",
            json={"name": "unsafe", "settings": {"api_key": "secret"}},
        )
        profile = client.post(
            "/v1/paper/profiles",
            json={"name": "conservative", "settings": {"theme": "dark", "leverage": 5}},
        )
        applied = client.post(
            f"/v1/paper/profiles/{profile.json()['id']}/apply",
            json={"name": "ignored", "confirmation": "APPLY PAPER PROFILE"},
        )
        help_topics = client.get("/v1/paper/help")
        missing = client.get("/v1/paper/verification")
        recorded = client.post(
            "/v1/paper/verification",
            json={"evidence": "manual Paper checks"},
        )
        client.put(
            f"/v1/paper/profiles/{profile.json()['id']}",
            json={"name": "conservative", "settings": {"leverage": 10}},
        )
        client.post(
            f"/v1/paper/profiles/{profile.json()['id']}/apply",
            json={"name": "ignored", "confirmation": "APPLY PAPER PROFILE"},
        )
        stale = client.get("/v1/paper/verification")

    assert rejected.status_code == 422
    assert applied.status_code == 200
    assert help_topics.status_code == 200
    assert all(topic["title_ar"] for topic in help_topics.json())
    assert missing.json()["stale"] is True
    assert recorded.json()["stale"] is False
    assert stale.json()["stale"] is True


def test_automatic_entry_requires_active_contract_and_consumes_signal(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=_PublicMarket())
    request = _preview_request()
    with TestClient(app) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
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
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        payload = {
            "symbol": "BTC_USDT",
            "trigger_zone": "99-100",
            "direction": "long",
            "preview": preview,
            "current_request": request,
        }
        accepted = client.post("/v1/paper/automatic-market-entry", json=payload)
        client.post(
            "/v1/paper/position/close",
            json={"market_price": "100", "confirmation": "CLOSE PAPER POSITION"},
        )
        duplicate = client.post("/v1/paper/automatic-market-entry", json=payload)
        signals = client.get("/v1/paper/used-signals")

    assert accepted.status_code == 200, accepted.json()
    assert duplicate.status_code == 409
    assert signals.json()[0]["trigger_zone"] == "99-100"

    with TestClient(
        create_app(database_url, public_market_provider=_PublicMarket())
    ) as reset_client:
        inside = reset_client.post(
            "/v1/paper/used-signals/BTC_USDT/long/reset",
            json={"market_price": "99.5", "reset_distance_percentage": "1"},
        )
        outside = reset_client.post(
            "/v1/paper/used-signals/BTC_USDT/long/reset",
            json={"market_price": "97", "reset_distance_percentage": "1"},
        )

    assert inside.json()[0]["reset_seen"] is False
    assert outside.json()[0]["reset_seen"] is True


def test_automatic_limit_derives_side_aware_price(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=_PublicMarket())
    request = _preview_request("short")
    with TestClient(app) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        client.post("/v1/paper/watchlist/BTC_USDT")
        client.post("/v1/paper/watchlist/BTC_USDT/active")
        client.post("/v1/paper/automatic-trading/start")
        preview = client.post("/v1/paper/entry-preview", json=request).json()
        created = client.post(
            "/v1/paper/automatic-limit-entry",
            json={
                "symbol": "BTC_USDT",
                "trigger_zone": "100-101",
                "preview": preview,
                "current_request": request,
                "placement_price": "100",
                "offset_percentage": "2",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            },
        )

    assert created.status_code == 200, created.json()
    assert Decimal(created.json()["pending_entry"]["limit_price"]) == Decimal("102")
