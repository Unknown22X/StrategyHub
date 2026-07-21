from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.engine.api import create_app
from rangebot.engine.database import create_database_engine
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.performance import AccountPerformanceRepository


def _snapshot(occurred_at: datetime, equity: str) -> ExchangeSnapshot:
    value = Decimal(equity)
    return ExchangeSnapshot(
        mode="live",
        reconciled_at=occurred_at,
        total_futures_equity=value,
        total_futures_balance=value,
        available_futures_balance=value,
        realized_pnl_total=value - Decimal("100"),
        net_pnl_total=value - Decimal("100"),
        one_way_confirmed=True,
        cross_margin_confirmed=True,
        risk_ready=True,
        daily_baseline_ready=True,
        subscription_confirmed=True,
        rest_snapshot_confirmed=True,
    )


def test_account_performance_api_survives_restart_and_filters_period(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'performance-api.db'}"
    now = datetime.now(UTC)
    with TestClient(create_app(database_url)):
        repository = AccountPerformanceRepository(create_database_engine(database_url))
        repository.record(_snapshot(now - timedelta(days=10), "80"))
        repository.record(_snapshot(now - timedelta(days=2), "100"))
        repository.record(_snapshot(now, "110"))

    with TestClient(create_app(database_url)) as client:
        all_response = client.get("/v1/performance/account/live?period=all")
        week_response = client.get("/v1/performance/account/live?period=7d")
        invalid = client.get("/v1/performance/account/live?maximum_points=1")

    assert all_response.status_code == 200
    assert len(all_response.json()["points"]) == 3
    assert all_response.json()["equity_change"] == "30.000000000000"
    assert week_response.status_code == 200
    assert len(week_response.json()["points"]) == 2
    assert week_response.json()["equity_change"] == "10.000000000000"
    assert invalid.status_code == 422


def test_authoritative_reconciliation_appends_performance_point(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'reconcile-performance.db'}"
    with TestClient(
        create_app(database_url, exchange_adapter=MockGateIoAdapter())
    ) as client:
        reconciliation = client.post("/v1/exchange/live/reconcile")
        performance = client.get("/v1/performance/account/live?period=all")

    assert reconciliation.status_code == 200
    assert performance.status_code == 200
    points = performance.json()["points"]
    assert len(points) == 1
    assert points[0]["available_balance"] == "1000.000000000000"
