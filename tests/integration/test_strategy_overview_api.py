from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from rangebot.domain.strategy import StrategyDecisionCreate
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.api import create_app
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


def _strategy_payload() -> dict[str, object]:
    return {
        "type_id": "range",
        "name": "BTC Range Overview",
        "environment": "paper",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {
            "mode": "rolling_window",
            "minimum_range_percentage": "20",
            "maximum_range_percentage": "25",
        },
    }


def _fill(
    *,
    trade_id: str,
    occurred_at: datetime,
    realized_pnl: str,
    instance_id: str,
    run_id: str,
) -> TradeFillCreate:
    return TradeFillCreate(
        environment="paper",
        external_trade_id=trade_id,
        order_id=f"order-{trade_id}",
        contract="BTC_USDT",
        side="sell",
        position_effect="close",
        quantity=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("0.10"),
        role="taker",
        close_quantity=Decimal("1"),
        trade_value=Decimal("100"),
        realized_pnl=Decimal(realized_pnl),
        occurred_at=occurred_at,
        source="paper_engine",
        origin="automatic_strategy",
        instance_id=instance_id,
        run_id=run_id,
        strategy_name_snapshot="BTC Range Overview",
    )


def test_strategy_overview_uses_engine_owned_today_and_lifetime_metrics(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    now = datetime.now(UTC)
    local_now = now.astimezone(ZoneInfo("Asia/Riyadh"))
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    app = create_app(database_url)
    with TestClient(app) as client:
        strategy = client.post("/v1/strategies", json=_strategy_payload()).json()
        instance_id = strategy["instance_id"]
        authorize_existing_strategy_instance(client.app, instance_id)
        started = client.post(f"/v1/strategies/{instance_id}/start")
        assert started.status_code == 200

        strategy_repository = app.state.strategy_instance_repository
        trade_repository = app.state.trade_history_repository
        run = strategy_repository.active_run(instance_id)
        strategy_repository.record_decision(
            instance_id,
            StrategyDecisionCreate(
                signal="none",
                eligible=False,
                reason_codes=("spread_too_wide",),
                analysis={"spread_percentage": "0.25"},
                occurred_at=now - timedelta(seconds=1),
            ),
        )
        trade_repository.record(
            _fill(
                trade_id="old-win",
                occurred_at=today_start - timedelta(minutes=1),
                realized_pnl="5",
                instance_id=instance_id,
                run_id=run.run_id,
            )
        )
        trade_repository.record(
            _fill(
                trade_id="today-loss",
                occurred_at=now - timedelta(minutes=2),
                realized_pnl="-4",
                instance_id=instance_id,
                run_id=run.run_id,
            )
        )
        trade_repository.record(
            _fill(
                trade_id="today-win",
                occurred_at=now - timedelta(minutes=1),
                realized_pnl="10",
                instance_id=instance_id,
                run_id=run.run_id,
            )
        )

        response = client.get("/v1/strategies/overview")

    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    overview = rows[0]
    assert overview["instance_id"] == instance_id
    assert overview["current_signal"] == "none"
    assert overview["latest_decision_eligible"] is False
    assert overview["latest_reason_codes"] == ["spread_too_wide"]
    assert overview["warning_codes"] == ["spread_too_wide"]
    assert Decimal(overview["today_realized_pnl"]) == Decimal("6")
    assert Decimal(overview["total_realized_pnl"]) == Decimal("11")
    assert Decimal(overview["win_rate_percentage"]) == Decimal(2) / Decimal(3) * Decimal(100)
    assert overview["total_fills"] == 3
    assert overview["last_trade_at"] is not None

    with TestClient(create_app(database_url)) as restarted:
        restored = restarted.get("/v1/strategies/overview")

    assert restored.status_code == 200
    assert restored.json()[0]["total_fills"] == 3
    assert Decimal(restored.json()[0]["total_realized_pnl"]) == Decimal("11")
