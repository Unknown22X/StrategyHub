from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.backtesting import (
    BacktestAssessment,
    BacktestMetrics,
    BacktestResult,
    BacktestRunRequest,
    BacktestSettings,
)
from rangebot.domain.exchange import TradingMode
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.engine.api import create_app
from rangebot.engine.exchange import MockGateIoAdapter
from rangebot.engine.market_data_manager import MarketDataManager


RANGE_CONFIGURATION = {
    "mode": "rolling_window",
    "minimum_range_percentage": "20",
    "maximum_range_percentage": "25",
}


def _market_update(sequence: int = 1) -> MarketPriceUpdate:
    return MarketPriceUpdate(
        symbol="BTC_USDT",
        last_price=Decimal("100"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        best_bid=Decimal("99.9"),
        best_ask=Decimal("100.1"),
        volume_24h=Decimal("1000000"),
        observed_at=datetime.now(UTC),
        source="gate_rest",
        sequence=sequence,
    )


def _market() -> MarketDataManager:
    manager = MarketDataManager()
    manager.apply_rest_snapshot(_market_update())
    return manager


def _strategy_payload(environment: str = "paper") -> dict[str, object]:
    return {
        "type_id": "range",
        "name": f"BTC Range {environment}",
        "environment": environment,
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "requested_margin": "20",
        "requested_leverage": 3,
        "configuration": RANGE_CONFIGURATION,
    }


def _backtest_result(request: BacktestRunRequest, label: str) -> BacktestResult:
    now = datetime.now(UTC)
    return BacktestResult(
        spec=request.spec(),
        started_at=now,
        ended_at=now + timedelta(seconds=1),
        candle_count=500,
        trades=(),
        equity_curve=(),
        metrics=BacktestMetrics(
            starting_balance=Decimal("1000"),
            ending_balance=Decimal("1100" if label == "promising" else "980"),
            net_profit=Decimal("100" if label == "promising" else "-20"),
            return_percentage=Decimal("10" if label == "promising" else "-2"),
            total_trades=10,
            winning_trades=7 if label == "promising" else 3,
            losing_trades=3 if label == "promising" else 7,
            win_rate_percentage=Decimal("70" if label == "promising" else "30"),
            gross_profit=Decimal("160" if label == "promising" else "60"),
            gross_loss=Decimal("-60" if label == "promising" else "-80"),
            fees=Decimal("8"),
            funding=Decimal("0"),
            average_win=Decimal("20"),
            average_loss=Decimal("-10"),
            maximum_drawdown_percentage=Decimal("9"),
            maximum_losing_streak=2,
            long_net_pnl=Decimal("100" if label == "promising" else "-20"),
            short_net_pnl=Decimal("0"),
        ),
        assessment=BacktestAssessment(
            label=label,
            score=88 if label == "promising" else 30,
            summary_ar="نتيجة محفوظة للاختبار.",
        ),
    )


def _create_backtested_strategy(
    app, client: TestClient, label: str = "promising"
) -> dict:
    now = datetime.now(UTC)
    request = BacktestRunRequest(
        strategy_type_id="range",
        symbol="BTC_USDT",
        timeframe_minutes=15,
        configuration=RANGE_CONFIGURATION,
        start=now - timedelta(days=30),
        end=now,
        settings=BacktestSettings(
            margin_per_trade=Decimal("20"),
            leverage=3,
        ),
    )
    stored = app.state.discovery_research_repository.save_backtest(
        request,
        _backtest_result(request, label),
        strategy_version="test",
    )
    response = client.post(
        f"/v1/backtests/{stored.backtest_id}/create-strategy",
        json={
            "name": f"Backtested {label}",
            "environment": "paper",
            "direction": "both",
        },
    )
    assert response.status_code == 200, response.json()
    return response.json()


def test_direct_paper_start_allows_never_backtested_warning_and_persists_snapshot(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper.db'}"
    app = create_app(
        database_url, initial_environment="paper", market_data_manager=_market()
    )

    with TestClient(app) as client:
        instance = client.post("/v1/strategies", json=_strategy_payload()).json()
        readiness = client.get(
            f"/v1/strategies/{instance['instance_id']}/start-readiness"
        )
        started = client.post(f"/v1/strategies/{instance['instance_id']}/start")
        runs = client.get(f"/v1/strategies/{instance['instance_id']}/runs")

    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True
    assert readiness.json()["backtest_state"] == "never_backtested"
    assert "never_backtested" in readiness.json()["warning_codes"]
    assert "never_backtested" not in readiness.json()["blocker_codes"]
    assert started.status_code == 200
    snapshot = runs.json()[0]["configuration_snapshot"]
    assert snapshot["instance"]["configuration"] == RANGE_CONFIGURATION
    assert snapshot["instance"]["requested_margin"].startswith("20")
    assert snapshot["start_readiness"]["backtest_state"] == "never_backtested"


def test_testnet_start_is_blocked_until_authoritative_readiness_then_succeeds(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object() if mode == "testnet" else None,
    )
    adapters: dict[TradingMode, MockGateIoAdapter] = {}

    def adapter_factory(mode: TradingMode) -> MockGateIoAdapter:
        adapter = MockGateIoAdapter()
        adapters[mode] = adapter
        return adapter

    app = create_app(
        f"sqlite:///{tmp_path / 'testnet.db'}",
        initial_environment="paper",
        exchange_adapter_factory=adapter_factory,
        market_data_manager=_market(),
    )
    with TestClient(app) as client:
        instance = client.post(
            "/v1/strategies", json=_strategy_payload("testnet")
        ).json()
        blocked = client.get(
            f"/v1/strategies/{instance['instance_id']}/start-readiness"
        )
        blocked_start = client.post(f"/v1/strategies/{instance['instance_id']}/start")
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "testnet"},
        )
        app.state.market_data_manager.apply_rest_snapshot(_market_update(sequence=2))
        reconciled = client.post("/v1/exchange/testnet/reconcile")
        ready = client.get(f"/v1/strategies/{instance['instance_id']}/start-readiness")
        started = client.post(f"/v1/strategies/{instance['instance_id']}/start")

    assert blocked.status_code == 200
    assert blocked.json()["ready"] is False
    assert "environment_mismatch" in blocked.json()["blocker_codes"]
    assert blocked_start.status_code == 409
    assert switched.status_code == 200
    assert reconciled.status_code == 200
    assert ready.json()["ready"] is True, ready.json()
    assert ready.json()["checks"]["credentials_configured"] is True
    assert ready.json()["checks"]["reconciliation_ready"] is True
    assert ready.json()["checks"]["market_data_fresh"] is True
    assert started.status_code == 200, started.json()
    assert set(adapters) == {"testnet"}


def test_live_start_requires_real_funds_confirmation_and_all_safety_readiness(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "rangebot.engine.api.load_gate_credentials",
        lambda mode: object() if mode == "live" else None,
    )
    adapters: dict[TradingMode, MockGateIoAdapter] = {}

    def adapter_factory(mode: TradingMode) -> MockGateIoAdapter:
        adapter = MockGateIoAdapter()
        adapters[mode] = adapter
        return adapter

    app = create_app(
        f"sqlite:///{tmp_path / 'live.db'}",
        initial_environment="paper",
        exchange_adapter_factory=adapter_factory,
        market_data_manager=_market(),
    )
    with TestClient(app) as client:
        instance = client.post("/v1/strategies", json=_strategy_payload("live")).json()
        switched = client.post(
            "/v1/runtime/environment/switch",
            json={"environment": "live", "confirmation": "SWITCH TO LIVE"},
        )
        app.state.market_data_manager.apply_rest_snapshot(_market_update(sequence=2))
        reconciled = client.post("/v1/exchange/live/reconcile")
        blocked = client.post(f"/v1/strategies/{instance['instance_id']}/start")
        started = client.post(
            f"/v1/strategies/{instance['instance_id']}/start",
            json={"confirmation": "START LIVE STRATEGY"},
        )

    assert switched.status_code == 200
    assert reconciled.status_code == 200
    assert blocked.status_code == 409
    readiness = blocked.json()["detail"]["readiness"]
    assert "live_confirmation_required" in readiness["blocker_codes"]
    assert started.status_code == 200, started.json()
    assert set(adapters) == {"live"}


def test_backtest_states_distinguish_success_failure_and_stale_configuration(
    tmp_path,
) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'backtests.db'}")
    with TestClient(app) as client:
        successful = _create_backtested_strategy(app, client, "promising")
        current = client.get(
            f"/v1/strategies/{successful['instance_id']}/start-readiness"
        )
        changed = client.put(
            f"/v1/strategies/{successful['instance_id']}",
            json={"requested_margin": "25"},
        )
        stale = client.get(
            f"/v1/strategies/{successful['instance_id']}/start-readiness"
        )
        failed = _create_backtested_strategy(app, client, "weak")
        failed_state = client.get(
            f"/v1/strategies/{failed['instance_id']}/start-readiness"
        )

    assert current.json()["backtest_state"] == "current_successful"
    assert current.json()["warning_codes"] == ["market_data_not_ready"]
    assert changed.status_code == 200
    assert stale.json()["backtest_state"] == "stale"
    assert "backtest_stale" in stale.json()["warning_codes"]
    assert failed_state.json()["backtest_state"] == "current_failed"
    assert "backtest_failed" in failed_state.json()["warning_codes"]


def test_run_snapshot_survives_instance_changes_and_process_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'restart.db'}"
    app = create_app(
        database_url, initial_environment="paper", market_data_manager=_market()
    )
    with TestClient(app) as client:
        instance = client.post("/v1/strategies", json=_strategy_payload()).json()
        client.post(f"/v1/strategies/{instance['instance_id']}/start")
        first_run = client.get(f"/v1/strategies/{instance['instance_id']}/runs").json()[
            0
        ]
        client.post(f"/v1/strategies/{instance['instance_id']}/pause")
        client.put(
            f"/v1/strategies/{instance['instance_id']}",
            json={"requested_margin": "35", "requested_leverage": 5},
        )
        client.post(f"/v1/strategies/{instance['instance_id']}/start")
        runs_before_restart = client.get(
            f"/v1/strategies/{instance['instance_id']}/runs"
        ).json()

    restarted = create_app(
        database_url,
        initial_environment="paper",
        market_data_manager=_market(),
    )
    with TestClient(restarted) as client:
        restored_instance = client.get(f"/v1/strategies/{instance['instance_id']}")
        restored_runs = client.get(f"/v1/strategies/{instance['instance_id']}/runs")

    assert Decimal(
        first_run["configuration_snapshot"]["instance"]["requested_margin"]
    ) == Decimal("20")
    assert Decimal(
        runs_before_restart[0]["configuration_snapshot"]["instance"]["requested_margin"]
    ) == Decimal("35")
    assert Decimal(
        runs_before_restart[1]["configuration_snapshot"]["instance"]["requested_margin"]
    ) == Decimal("20")
    assert restored_instance.json()["status"] == "running"
    assert restored_runs.json()[0]["status"] == "active"
    assert (
        restored_runs.json()[0]["configuration_snapshot"]
        == runs_before_restart[0]["configuration_snapshot"]
    )
