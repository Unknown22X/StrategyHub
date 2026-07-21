from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.backtesting import (
    BacktestAssessment,
    BacktestMetrics,
    BacktestResult,
    StoredBacktestRun,
)
from rangebot.domain.discovery import (
    StoredStrategyScan,
    StrategyScanCandidate,
    StrategyScanRequest,
    StrategyScanResult,
)
from rangebot.domain.strategy_workflow import SetupBacktestRequest
from rangebot.engine.api import create_app


# Keep the opportunity inside its 24-hour validity window when the suite runs.
NOW = datetime.now(UTC) - timedelta(hours=1)


def _record_promising_backtest(app, setup_id: str) -> StoredBacktestRun:
    workflow = app.state.strategy_workflow_repository
    request = workflow.build_backtest_request(
        setup_id,
        SetupBacktestRequest(
            start=NOW - timedelta(days=30),
            end=NOW,
        ),
    )
    metrics = BacktestMetrics(
        starting_balance=Decimal("1000"),
        ending_balance=Decimal("1100"),
        net_profit=Decimal("100"),
        return_percentage=Decimal("10"),
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate_percentage=Decimal("70"),
        gross_profit=Decimal("160"),
        gross_loss=Decimal("-60"),
        fees=Decimal("8"),
        funding=Decimal("0"),
        average_win=Decimal("22.8571428571"),
        average_loss=Decimal("-20"),
        profit_factor=Decimal("2.6666666667"),
        maximum_drawdown_percentage=Decimal("9"),
        maximum_losing_streak=2,
        long_net_pnl=Decimal("100"),
        short_net_pnl=Decimal("0"),
        largest_winner_share_percentage=Decimal("22"),
    )
    stored = StoredBacktestRun(
        backtest_id="api-promising-backtest",
        strategy_version="1",
        created_at=NOW,
        request=request,
        result=BacktestResult(
            spec=request.spec(),
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            candle_count=500,
            trades=(),
            equity_curve=(),
            metrics=metrics,
            assessment=BacktestAssessment(
                label="promising",
                score=88,
                summary_ar="نتيجة واعدة.",
                reasons=("عائد موجب",),
            ),
        ),
    )
    workflow.record_backtest(setup_id, stored)
    return stored


def test_public_strategy_workflow_routes_enforce_approval_before_start(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    with TestClient(app) as client:
        template_response = client.post(
            "/v1/strategy-templates",
            json={
                "type_id": "adaptive_trend",
                "name": "اتجاه API",
                "description": "قواعد قابلة لإعادة الاستخدام.",
                "timeframe_minutes": 5,
                "direction": "both",
                "configuration": {},
                "setup_defaults": {
                    "execution_plan": {
                        "entry": {
                            "order_type": "market",
                            "limit_price": None,
                            "limit_price_formula": None,
                            "time_in_force": "gtc",
                            "expires_after_minutes": None,
                            "cancellation_policy": "cancel_on_signal_reset",
                            "partial_fill_behavior": "accept_partial",
                        },
                        **{
                            key: {
                                "order_type": "market",
                                "limit_offset_percentage": None,
                                "time_in_force": "ioc",
                                "maximum_wait_seconds": 30,
                                "fallback_to_market": True,
                            }
                            for key in (
                                "take_profit",
                                "stop_loss",
                                "strategy_exit",
                                "manual_exit",
                            )
                        },
                    },
                    "dca": {
                        "enabled": False,
                        "maximum_entries": 1,
                        "spacing_percentage": "1",
                        "allocation_method": "equal",
                        "custom_allocations": [],
                    },
                    "risk": {
                        "requested_margin": "20",
                        "requested_leverage": 3,
                        "maximum_positions": 1,
                        "maximum_exposure_percentage": "25",
                    },
                },
                "status": "active",
            },
        )
        assert template_response.status_code == 201
        template = template_response.json()

        setup_response = client.post(
            "/v1/strategy-setups",
            json={
                "template_id": template["template_id"],
                "symbol": "BTC_USDT",
            },
        )
        assert setup_response.status_code == 201
        setup = setup_response.json()
        assert setup["status"] == "ready_for_backtest"
        assert setup["price_state"] == "unavailable"

        premature_deployment = client.post(
            f"/v1/strategy-setups/{setup['setup_id']}/deployments",
            json={"environment": "paper"},
        )
        assert premature_deployment.status_code == 409

        _record_promising_backtest(app, setup["setup_id"])
        approval = client.post(
            f"/v1/strategy-setups/{setup['setup_id']}/approve",
            json={"mode": "paper", "note": "مراجعة API"},
        )
        assert approval.status_code == 200
        assert approval.json()["setup_revision"] == 1

        deployment_response = client.post(
            f"/v1/strategy-setups/{setup['setup_id']}/deployments",
            json={"environment": "paper"},
        )
        assert deployment_response.status_code == 201
        deployment = deployment_response.json()
        assert deployment["status"] == "not_started"
        assert deployment["configuration_snapshot"]["setup_revision"] == 1

        started = client.post(
            f"/v1/bot-deployments/{deployment['deployment_id']}/start"
        )
        assert started.status_code == 200
        assert started.json()["status"] == "running"
        stopped = client.post(
            f"/v1/bot-deployments/{deployment['deployment_id']}/stop"
        )
        assert stopped.status_code == 200
        assert stopped.json()["status"] == "stopped"

        summary = client.get("/v1/workflow/summary").json()
        assert summary["templates"] == 1
        assert summary["setups"] == 1
        assert client.get("/v1/strategy-templates").status_code == 200
        assert client.get("/v1/strategy-setups").status_code == 200
        assert client.get("/v1/bot-deployments").status_code == 200


def test_opportunity_routes_preserve_price_time_status_and_conversion(tmp_path) -> None:
    app = create_app(f"sqlite:///{tmp_path / 'rangebot.db'}")
    workflow = app.state.strategy_workflow_repository
    scan = StoredStrategyScan(
        scan_id="scan-api-1",
        strategy_version="1",
        created_at=NOW,
        request=StrategyScanRequest(
            strategy_type_id="adaptive_trend",
            timeframe_minutes=5,
            configuration={},
            minimum_quote_volume=Decimal("1000000"),
            maximum_symbols=10,
            maximum_candidates=5,
            minimum_score=50,
        ),
        result=StrategyScanResult(
            strategy_type_id="adaptive_trend",
            timeframe_minutes=5,
            scanned_at=NOW,
            universe_symbols=1,
            scanned_symbols=1,
            candidates=(
                StrategyScanCandidate(
                    symbol="ETH_USDT",
                    exchange="gateio",
                    market_type="usdt_perpetual",
                    quote_currency="USDT",
                    current_price=Decimal("3500"),
                    price_observed_at=NOW,
                    score=82,
                    signal="long",
                    eligible_now=True,
                    evaluated_at=NOW,
                    market_data_state="fresh",
                    explanation_ar="اتجاه وسيولة مناسبان.",
                    reason_codes=("trend_aligned", "liquidity_ok"),
                    metrics={},
                    completed_candles=500,
                    backtest_ready=True,
                ),
            ),
        ),
    )

    with TestClient(app) as client:
        workflow.ingest_scan(scan)
        template = client.post(
            "/v1/strategy-templates",
            json={
                "type_id": "adaptive_trend",
                "name": "اتجاه الفرص",
                "description": "قالب متوافق.",
                "timeframe_minutes": 5,
                "direction": "both",
                "configuration": {},
                "status": "active",
            },
        ).json()
        opportunities = client.get("/v1/opportunities").json()
        assert len(opportunities) == 1
        opportunity = opportunities[0]
        assert opportunity["current_price"] == "3500.000000000000"
        assert opportunity["price_observed_at"].startswith(NOW.date().isoformat())
        assert opportunity["price_state"] == "fresh"

        approved = client.put(
            f"/v1/opportunities/{opportunity['opportunity_id']}",
            json={"status": "approved"},
        )
        assert approved.status_code == 200
        converted = client.post(
            f"/v1/opportunities/{opportunity['opportunity_id']}/convert",
            json={
                "template_id": template["template_id"],
                "configuration_overrides": {},
            },
        )
        assert converted.status_code == 201
        setup = converted.json()
        assert setup["symbol"] == "ETH_USDT"
        assert setup["current_price"] == "3500.000000000000"
        assert setup["source_opportunity_id"] == opportunity["opportunity_id"]
        assert client.get("/v1/opportunities").json()[0]["status"] == "converted"
