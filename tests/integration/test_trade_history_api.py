from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import FuturesContractRules, ManualOrderPreviewRequest
from rangebot.domain.strategy import TradeOwnershipCreate
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


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
            sequence=10,
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


def _manual_payload() -> dict[str, object]:
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


def test_paper_trade_history_records_open_close_summary_and_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "trade history"},
        )
        preview = client.post("/v1/manual-orders/preview", json=_manual_payload())
        submitted = client.post(
            "/v1/manual-orders",
            json={
                "request": _manual_payload(),
                "preview_fingerprint": preview.json()["safety_fingerprint"],
            },
        )
        opened = client.get("/v1/trades", params={"environment": "paper"})
        closed = client.post(
            "/v1/paper/position/close",
            json={"market_price": "65100", "confirmation": "CLOSE PAPER POSITION"},
        )
        history = client.get(
            "/v1/trades",
            params={"environment": "paper", "contract": "BTC_USDT"},
        )
        summary = client.get(
            "/v1/trades/summary", params={"environment": "paper"}
        )

    assert submitted.status_code == 200
    assert opened.status_code == 200
    assert len(opened.json()) == 1
    assert opened.json()[0]["position_effect"] == "open"
    assert opened.json()[0]["origin"] == "manual"
    assert opened.json()[0]["order_id"] == submitted.json()["order_id"]
    assert closed.status_code == 200
    assert closed.json()["trade_id"] is not None
    assert history.status_code == 200
    assert [row["position_effect"] for row in history.json()] == ["close", "open"]
    assert all(row["origin"] == "manual" for row in history.json())
    assert summary.json()["fills"] == 2
    assert Decimal(summary.json()["closed_quantity"]) > 0
    assert Decimal(summary.json()["fees"]) > 0

    with TestClient(create_app(database_url)) as restarted:
        persisted = restarted.get(
            "/v1/trades", params={"environment": "paper", "limit": 10}
        )

    assert persisted.status_code == 200
    assert len(persisted.json()) == 2


def test_automatic_paper_fill_is_attributed_to_strategy_instance_and_run(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        market_data_manager=_market(),
        contract_rules_provider=_rules,
    )

    with TestClient(app) as client:
        client.post(
            "/v1/paper-account/initialize",
            json={"starting_balance": "1000", "reason": "strategy history"},
        )
        created = client.post(
            "/v1/strategies",
            json={
                "type_id": "range",
                "name": "BTC Range",
                "environment": "paper",
                "symbol": "BTC_USDT",
                "timeframe_minutes": 15,
                "direction": "both",
                "requested_margin": "50",
                "requested_leverage": 3,
                "configuration": {"proximity_percentage": "3"},
            },
        ).json()
        authorize_existing_strategy_instance(client.app, created["instance_id"])
        client.post(f"/v1/strategies/{created['instance_id']}/start")
        run = app.state.strategy_instance_repository.runs(created["instance_id"])[0]
        result = app.state.order_manager.submit_automatic(
            ManualOrderPreviewRequest(
                environment="paper",
                symbol="BTC_USDT",
                direction="long",
                order_type="market",
                size_mode="margin",
                margin_amount=Decimal("50"),
                leverage=3,
                time_in_force="ioc",
            ),
            origin="automatic_strategy",
            instance_id=created["instance_id"],
            run_id=run.run_id,
            take_profit_price=Decimal("66000"),
            stop_loss_price=Decimal("64000"),
        )
        filtered = client.get(
            "/v1/trades",
            params={"instance_id": created["instance_id"]},
        )
        summary = client.get(
            "/v1/trades/summary",
            params={"instance_id": created["instance_id"]},
        )

    assert result.accepted is True
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1
    row = filtered.json()[0]
    assert row["origin"] == "automatic_strategy"
    assert row["instance_id"] == created["instance_id"]
    assert row["run_id"] == run.run_id
    assert row["strategy_name_snapshot"] == "BTC Range"
    assert summary.json()["fills"] == 1


class _GateTradeHistoryAdapter:
    def reconcile(self, mode: str) -> ExchangeSnapshot:
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=NOW,
            available_futures_balance=Decimal("1000"),
            one_way_confirmed=True,
            cross_margin_confirmed=True,
            market_ready=True,
            history_ready=True,
            risk_ready=True,
            active_contract_ready=True,
            daily_baseline_ready=True,
            subscription_confirmed=True,
            rest_snapshot_confirmed=True,
        )

    def recent_trade_fills(self, mode: str) -> tuple[TradeFillCreate, ...]:
        return (
            TradeFillCreate(
                environment=mode,
                external_trade_id="gate-trade-1",
                order_id="gate-order-1",
                contract="BTC_USDT",
                side="buy",
                position_effect="open",
                quantity=Decimal("1"),
                price=Decimal("65000"),
                fee=Decimal("0.5"),
                role="taker",
                close_quantity=Decimal("0"),
                trade_value=Decimal("65000"),
                occurred_at=NOW,
                source="gate_rest",
            ),
        )


def test_gate_reconciliation_imports_fills_idempotently_with_order_ownership(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    adapter = _GateTradeHistoryAdapter()
    app = create_app(
        database_url,
        exchange_adapter=adapter,
        exchange_adapter_mode="testnet",
    )
    with TestClient(app) as client:
        app.state.strategy_instance_repository.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity="gate-order-1",
                origin="manual",
                environment="testnet",
                symbol="BTC_USDT",
                direction="long",
            )
        )
        first = client.post("/v1/exchange/testnet/reconcile")
        second = client.post("/v1/exchange/testnet/reconcile")
        history = client.get(
            "/v1/trades", params={"environment": "testnet"}
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["external_trade_id"] == "gate-trade-1"
    assert history.json()[0]["origin"] == "manual"
    assert history.json()[0]["source"] == "gate_rest"
    assert history.json()[0]["realized_pnl"] is None
