from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import (
    ExchangeOpenOrderSnapshot,
    ExchangePositionSnapshot,
)
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules, ManualOrderPreviewRequest
from rangebot.domain.strategy import StrategyInstanceCreate, TradeOwnershipCreate
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.market_data_manager import MarketDataManager
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


class PositionAwareMockGateAdapter(MockGateIoAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.position_symbol = "BTC_USDT"
        self.position_direction = "long"

    def submit_entry(self, mode, request):
        result = super().submit_entry(mode, request)
        if result.accepted:
            self.position_symbol = request.symbol
            self.position_direction = request.direction
        return result

    def fill_pending(self, quantity: Decimal = Decimal("2")) -> None:
        if self.pending_request_id is None:
            raise RuntimeError("No pending order to fill.")
        self.position_quantity = quantity
        self.position_symbol = self.pending_symbol or "BTC_USDT"
        self.position_direction = self.pending_direction or "long"
        self.pending_request_id = None
        self.pending_limit_price = None
        self.pending_symbol = None
        self.pending_direction = None

    def reconcile(self, mode):
        snapshot = super().reconcile(mode)
        positions = ()
        if self.position_quantity != 0:
            positions = (
                ExchangePositionSnapshot(
                    contract=self.position_symbol,
                    side=self.position_direction,
                    quantity=self.position_quantity,
                    entry_price=Decimal("100"),
                    mark_price=Decimal("101"),
                    value=abs(self.position_quantity) * Decimal("101"),
                    margin=Decimal("20"),
                    unrealized_pnl=Decimal("2"),
                    leverage=Decimal("5"),
                    opened_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            )
        orders = ()
        if self.pending_request_id is not None:
            orders = (
                ExchangeOpenOrderSnapshot(
                    order_id=f"mock-{self.pending_request_id}",
                    contract=self.pending_symbol or "BTC_USDT",
                    side=self.pending_direction or "long",
                    order_type="limit",
                    price=self.pending_limit_price,
                    quantity=Decimal("2"),
                    status="open",
                    managed_by_rangebot=True,
                    created_at=datetime.now(UTC),
                ),
            )
        return snapshot.model_copy(
            update={
                "positions": positions,
                "open_orders": orders,
                "position_quantity": self.position_quantity,
            }
        )


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


def _market() -> MarketDataManager:
    manager = MarketDataManager()
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("100"),
            mark_price=Decimal("100"),
            index_price=Decimal("100"),
            best_bid=Decimal("99.9"),
            best_ask=Decimal("100.1"),
            volume_24h=Decimal("10000000"),
            observed_at=datetime.now(UTC),
            source="gate_rest",
        )
    )
    return manager


def _running_strategy(client: TestClient) -> tuple[str, str]:
    created = client.post(
        "/v1/strategies",
        json=StrategyInstanceCreate(
            type_id="range",
            name="BTC ownership strategy",
            environment="live",
            symbol="BTC_USDT",
            timeframe_minutes=15,
            direction="long",
            configuration={"timeframe_minutes": 15, "direction": "long"},
        ).model_dump(mode="json"),
    )
    assert created.status_code == 201
    instance_id = created.json()["instance_id"]
    authorize_existing_strategy_instance(client.app, instance_id)
    started = client.post(f"/v1/strategies/{instance_id}/start")
    assert started.status_code == 200
    runs = client.get(f"/v1/strategies/{instance_id}/runs").json()
    run_id = next(run["run_id"] for run in runs if run["status"] == "active")
    return instance_id, run_id


def test_market_fill_records_and_exposes_position_ownership(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'position-market.db'}"
    adapter = PositionAwareMockGateAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )
    with TestClient(app) as client:
        instance_id, run_id = _running_strategy(client)
        result = app.state.order_manager.submit_automatic(
            ManualOrderPreviewRequest(
                environment="live",
                symbol="BTC_USDT",
                direction="long",
                order_type="market",
                size_mode="quantity",
                quantity=Decimal("2"),
                leverage=5,
                time_in_force="ioc",
            ),
            origin="automatic_strategy",
            instance_id=instance_id,
            run_id=run_id,
        )
        assert result.accepted is True

        state = client.get("/v1/exchange/live/state").json()
        position = state["snapshot"]["positions"][0]
        assert position["managed_by_rangebot"] is True
        assert position["origin"] == "automatic_strategy"
        assert position["instance_id"] == instance_id
        assert position["run_id"] == run_id
        assert position["strategy_name"] == "BTC ownership strategy"


def test_limit_ownership_moves_to_position_only_after_observed_fill_and_clears(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'position-limit.db'}"
    adapter = PositionAwareMockGateAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        exchange_adapter_mode="live",
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )
    with TestClient(app) as client:
        instance_id, run_id = _running_strategy(client)
        result = app.state.order_manager.submit_automatic(
            ManualOrderPreviewRequest(
                environment="live",
                symbol="BTC_USDT",
                direction="long",
                order_type="limit",
                size_mode="quantity",
                quantity=Decimal("2"),
                leverage=5,
                limit_price=Decimal("99"),
                time_in_force="gtc",
            ),
            origin="automatic_strategy",
            instance_id=instance_id,
            run_id=run_id,
        )
        assert result.accepted is True
        position_identity = "live:BTC_USDT:long"
        assert client.get(f"/v1/trade-ownership/position/{position_identity}").status_code == 404

        adapter.fill_pending()
        reconciled = client.post("/v1/exchange/live/reconcile")
        assert reconciled.status_code == 200
        position = reconciled.json()["snapshot"]["positions"][0]
        assert position["strategy_name"] == "BTC ownership strategy"
        assert position["origin"] == "automatic_strategy"

        adapter.position_quantity = Decimal("0")
        closed = client.post("/v1/exchange/live/reconcile")
        assert closed.status_code == 200
        assert closed.json()["snapshot"]["positions"] == []
        assert client.get(f"/v1/trade-ownership/position/{position_identity}").status_code == 404


def test_trade_ownership_context_survives_engine_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'ownership-restart.db'}"
    with TestClient(create_app(database_url)) as client:
        instance_id, run_id = _running_strategy(client)
        repository = client.app.state.strategy_instance_repository
        repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity="restart-owned-order",
                origin="automatic_strategy",
                environment="live",
                symbol="BTC_USDT",
                direction="long",
                instance_id=instance_id,
                run_id=run_id,
            )
        )

    with TestClient(create_app(database_url)) as restarted:
        response = restarted.get(
            "/v1/trade-ownership/order/restart-owned-order"
        )

    assert response.status_code == 200
    ownership = response.json()
    assert ownership["environment"] == "live"
    assert ownership["symbol"] == "BTC_USDT"
    assert ownership["direction"] == "long"
    assert ownership["instance_id"] == instance_id
    assert ownership["run_id"] == run_id


def test_unmanaged_exchange_position_is_not_falsely_attributed(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'unmanaged-position.db'}"
    adapter = PositionAwareMockGateAdapter()
    adapter.position_quantity = Decimal("3")
    with TestClient(
        create_app(
            database_url,
            exchange_adapter=adapter,
            exchange_adapter_mode="live",
            market_data_manager=_market(),
            contract_rules_provider=_rules,
        )
    ) as client:
        reconciled = client.post("/v1/exchange/live/reconcile")

    assert reconciled.status_code == 200
    position = reconciled.json()["snapshot"]["positions"][0]
    assert position["managed_by_rangebot"] is False
    assert position["origin"] is None
    assert position["strategy_name"] is None
