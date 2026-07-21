from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter


def test_automatic_signal_uses_central_order_manager(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()

    with TestClient(create_app(database_url, exchange_adapter=adapter)) as client:
        client.post("/v1/exchange/testnet/reconcile")
        client.post(
            "/v1/exchange/testnet/automatic/start",
            json={"active_contract": "BTC_USDT"},
        )
        response = client.post(
            "/v1/exchange/testnet/automatic/signal",
            json={"symbol": "BTC_USDT", "direction": "long"},
        )

    assert response.status_code == 200, response.json()
    assert adapter.position_quantity == Decimal("1")


def test_automatic_signal_is_blocked_by_account_wide_automatic_trade_limit(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(database_url, exchange_adapter=adapter)

    with TestClient(app) as client:
        client.put(
            "/v1/account-risk/policy",
            json={
                "daily_loss_limit": "100",
                "losing_trade_limit": 3,
                "automatic_trade_limit": 1,
            },
        )
        client.post("/v1/exchange/testnet/reconcile")
        app.state.trade_history_repository.record(
            TradeFillCreate(
                environment="testnet",
                external_trade_id="existing-automatic-fill",
                order_id="existing-automatic-order",
                contract="BTC_USDT",
                side="buy",
                position_effect="open",
                quantity=Decimal("1"),
                price=Decimal("100"),
                fee=Decimal("0.05"),
                role="taker",
                close_quantity=Decimal("0"),
                trade_value=Decimal("100"),
                realized_pnl=None,
                occurred_at=datetime.now(UTC),
                source="gate_rest",
                origin="automatic_strategy",
            )
        )
        client.post(
            "/v1/exchange/testnet/automatic/start",
            json={"active_contract": "BTC_USDT"},
        )
        status = client.get("/v1/account-risk/testnet")
        response = client.post(
            "/v1/exchange/testnet/automatic/signal",
            json={"symbol": "BTC_USDT", "direction": "long"},
        )

    assert status.status_code == 200
    assert status.json()["manual_entries_blocked"] is False
    assert status.json()["automatic_entries_blocked"] is True
    assert response.status_code == 409
    assert adapter.position_quantity == Decimal("0")
    assert adapter.submissions == {}
