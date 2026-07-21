from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter


def _fill(
    *,
    trade_id: str,
    order_id: str,
    occurred_at: datetime,
    position_effect: str,
    realized_pnl: str | None,
    origin: str,
) -> TradeFillCreate:
    return TradeFillCreate(
        environment="live",
        external_trade_id=trade_id,
        order_id=order_id,
        contract="BTC_USDT",
        side="sell" if position_effect == "close" else "buy",
        position_effect=position_effect,
        quantity=Decimal("0.5"),
        price=Decimal("100"),
        fee=Decimal("0.05"),
        role="taker",
        close_quantity=Decimal("0.5") if position_effect == "close" else Decimal("0"),
        trade_value=Decimal("50"),
        realized_pnl=Decimal(realized_pnl) if realized_pnl is not None else None,
        occurred_at=occurred_at,
        source="gate_rest",
        origin=origin,
    )


def test_account_risk_policy_and_daily_status_persist_and_count_distinct_orders(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = MockGateIoAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
    )

    with TestClient(app) as client:
        assert client.post("/v1/exchange/live/reconcile").status_code == 200
        now = datetime.now(UTC) + timedelta(seconds=1)
        app.state.account_risk_baseline_repository.capture_if_missing(
            environment="live",
            day=now.astimezone(ZoneInfo("Asia/Riyadh")).date(),
            baseline_equity=Decimal("1000"),
            captured_at=now - timedelta(minutes=5),
        )
        policy = client.put(
            "/v1/account-risk/policy",
            json={
                "daily_loss_limit": "100",
                "losing_trade_limit": 3,
                "automatic_trade_limit": 1,
            },
        )
        assert policy.status_code == 200

        performance = app.state.performance_repository
        trades = app.state.trade_history_repository
        performance.record(
            ExchangeSnapshot(
                mode="live",
                reconciled_at=now - timedelta(minutes=5),
                total_futures_equity=Decimal("1000"),
                available_futures_balance=Decimal("1000"),
            )
        )
        performance.record(
            ExchangeSnapshot(
                mode="live",
                reconciled_at=now,
                total_futures_equity=Decimal("940"),
                available_futures_balance=Decimal("940"),
            )
        )
        for trade_id in ("loss-part-1", "loss-part-2"):
            trades.record(
                _fill(
                    trade_id=trade_id,
                    order_id="one-losing-order",
                    occurred_at=now - timedelta(minutes=3),
                    position_effect="close",
                    realized_pnl="-5",
                    origin="manual",
                )
            )
        for trade_id in ("auto-part-1", "auto-part-2"):
            trades.record(
                _fill(
                    trade_id=trade_id,
                    order_id="one-automatic-order",
                    occurred_at=now - timedelta(minutes=2),
                    position_effect="open",
                    realized_pnl=None,
                    origin="automatic_strategy",
                )
            )

        status = client.get("/v1/account-risk/live")

    assert status.status_code == 200
    payload = status.json()
    assert payload["baseline_ready"] is True
    assert Decimal(payload["baseline_equity"]) == Decimal("1000")
    assert Decimal(payload["current_equity"]) == Decimal("940")
    assert Decimal(payload["equity_loss_used"]) == Decimal("60")
    assert Decimal(payload["remaining_loss_allowance"]) == Decimal("40")
    assert payload["losing_trades"] == 1
    assert payload["automatic_trades"] == 1
    assert payload["manual_entries_blocked"] is False
    assert payload["automatic_entries_blocked"] is True
    assert payload["blocked_reason_codes"] == ["automatic_trade_limit_reached"]

    with TestClient(create_app(database_url)) as restarted:
        restored_policy = restarted.get("/v1/account-risk/policy")
        restored_status = restarted.get("/v1/account-risk/live")

    assert restored_policy.status_code == 200
    assert restored_policy.json()["automatic_trade_limit"] == 1
    assert restored_status.json()["automatic_trades"] == 1


def test_account_risk_is_fail_closed_without_daily_equity_baseline(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(create_app(database_url)) as client:
        response = client.get("/v1/account-risk/testnet")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline_ready"] is False
    assert payload["synchronization_complete"] is False
    assert payload["risk_data_state"] == "synchronizing"
    assert payload["manual_entries_blocked"] is True
    assert payload["automatic_entries_blocked"] is True
    assert payload["blocked_reason_codes"] == ["synchronization_incomplete"]
    assert all(limit["state"] == "synchronizing" for limit in payload["limits"])
    assert "daily_loss_limit_reached" not in payload["blocked_reason_codes"]
