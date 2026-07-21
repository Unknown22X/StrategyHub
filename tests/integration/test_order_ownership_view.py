from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeOpenOrderSnapshot, ExchangeSnapshot
from rangebot.domain.strategy import TradeOwnershipCreate
from rangebot.engine.api import create_app
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


def test_exchange_state_enriches_open_orders_with_recorded_strategy_ownership(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)

    with TestClient(app) as client:
        created = client.post(
            "/v1/strategies",
            json={
                "type_id": "range",
                "name": "BTC 15m Range",
                "symbol": "BTC_USDT",
                "timeframe_minutes": 15,
                "direction": "both",
                "configuration": {
                    "mode": "rolling_window",
                    "minimum_range_percentage": "20",
                    "maximum_range_percentage": "25",
                },
            },
        ).json()
        authorize_existing_strategy_instance(client.app, created["instance_id"])
        started = client.post(
            f"/v1/strategies/{created['instance_id']}/start"
        )
        assert started.status_code == 200
        run = app.state.strategy_instance_repository.runs(created["instance_id"])[0]
        app.state.strategy_instance_repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity="gate-order-1",
                origin="automatic_strategy",
                instance_id=created["instance_id"],
                run_id=run.run_id,
            )
        )
        app.state.exchange_repository.save_snapshot(
            ExchangeSnapshot(
                mode="live",
                reconciled_at=datetime.now(UTC),
                available_futures_balance=Decimal("1000"),
                open_orders=(
                    ExchangeOpenOrderSnapshot(
                        order_id="gate-order-1",
                        contract="BTC_USDT",
                        side="long",
                        order_type="limit",
                        price=Decimal("65000"),
                        quantity=Decimal("2"),
                        status="open",
                    ),
                ),
            )
        )

        state = client.get("/v1/exchange/live/state")

    assert state.status_code == 200
    order = state.json()["snapshot"]["open_orders"][0]
    assert order["managed_by_rangebot"] is True
    assert order["origin"] == "automatic_strategy"
    assert order["instance_id"] == created["instance_id"]
    assert order["run_id"] == run.run_id
    assert order["strategy_name"] == "BTC 15m Range"

    persisted = app.state.exchange_repository.get_snapshot("live")
    assert persisted is not None
    assert persisted.open_orders[0].origin is None
    assert persisted.open_orders[0].strategy_name is None
