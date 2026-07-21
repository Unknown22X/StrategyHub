from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.backtesting import (
    BacktestAssessment,
    BacktestEquityPoint,
    BacktestMetrics,
    BacktestResult,
    BacktestRunRequest,
    BacktestSettings,
    BacktestTrade,
)
from rangebot.domain.discovery import (
    StrategyScanCandidate,
    StrategyScanRequest,
    StrategyScanResult,
)
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.discovery_repository import DiscoveryResearchRepository


def _database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'rangebot.db'}"


def _scan() -> tuple[StrategyScanRequest, StrategyScanResult]:
    scanned_at = datetime(2026, 1, 1, tzinfo=UTC)
    request = StrategyScanRequest(
        strategy_type_id="range",
        timeframe_minutes=5,
        configuration={"timeframe_minutes": 5},
        maximum_symbols=10,
        maximum_candidates=5,
    )
    result = StrategyScanResult(
        strategy_type_id="range",
        timeframe_minutes=5,
        scanned_at=scanned_at,
        universe_symbols=2,
        scanned_symbols=2,
        candidates=(
            StrategyScanCandidate(
                symbol="BTC_USDT",
                score=84,
                signal="long",
                eligible_now=True,
                evaluated_at=scanned_at,
                market_data_state="fresh",
                explanation_ar="مرشح واضح للاختبار.",
                metrics={"range_percentage": Decimal("20")},
                completed_candles=300,
                backtest_ready=True,
            ),
        ),
    )
    return request, result


def _backtest(scan_id: str) -> tuple[BacktestRunRequest, BacktestResult]:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    ended = started + timedelta(days=30)
    settings = BacktestSettings(
        initial_balance=Decimal("1000"),
        margin_per_trade=Decimal("100"),
        leverage=2,
        taker_fee_rate=Decimal("0.0005"),
        minimum_trades_for_assessment=1,
    )
    request = BacktestRunRequest(
        scan_id=scan_id,
        strategy_type_id="range",
        symbol="BTC_USDT",
        timeframe_minutes=5,
        configuration={"timeframe_minutes": 5},
        start=started,
        end=ended,
        settings=settings,
    )
    trade = BacktestTrade(
        trade_number=1,
        direction="long",
        signal_at=started,
        entered_at=started + timedelta(minutes=5),
        exited_at=started + timedelta(hours=1),
        entry_price=Decimal("100"),
        exit_price=Decimal("105"),
        quantity=Decimal("2"),
        allocated_margin=Decimal("100"),
        leverage=2,
        gross_pnl=Decimal("10"),
        fees=Decimal("0.205"),
        funding=Decimal("0"),
        net_pnl=Decimal("9.795"),
        return_on_margin_percentage=Decimal("9.795"),
        exit_reason="take_profit",
        bars_held=11,
    )
    metrics = BacktestMetrics(
        starting_balance=Decimal("1000"),
        ending_balance=Decimal("1009.795"),
        net_profit=Decimal("9.795"),
        return_percentage=Decimal("0.9795"),
        total_trades=1,
        winning_trades=1,
        losing_trades=0,
        win_rate_percentage=Decimal("100"),
        gross_profit=Decimal("9.795"),
        gross_loss=Decimal("0"),
        fees=Decimal("0.205"),
        funding=Decimal("0"),
        average_win=Decimal("9.795"),
        average_loss=Decimal("0"),
        profit_factor=None,
        maximum_drawdown_percentage=Decimal("0.1"),
        maximum_losing_streak=0,
        long_net_pnl=Decimal("9.795"),
        short_net_pnl=Decimal("0"),
        largest_winner_share_percentage=Decimal("100"),
    )
    result = BacktestResult(
        spec=request.spec(),
        started_at=started,
        ended_at=ended,
        candle_count=500,
        trades=(trade,),
        equity_curve=(
            BacktestEquityPoint(
                occurred_at=started,
                equity=Decimal("1000"),
                drawdown_percentage=Decimal("0"),
            ),
            BacktestEquityPoint(
                occurred_at=ended,
                equity=Decimal("1009.795"),
                drawdown_percentage=Decimal("0"),
            ),
        ),
        metrics=metrics,
        assessment=BacktestAssessment(
            label="mixed",
            score=65,
            summary_ar="نتيجة مختلطة تحتاج إلى عينات إضافية.",
            warnings=("عدد الصفقات قليل.",),
        ),
    )
    return request, result


def test_scan_and_backtest_survive_repository_restart(tmp_path) -> None:
    database_url = _database_url(tmp_path)
    apply_migrations(database_url)
    engine = create_database_engine(database_url)
    repository = DiscoveryResearchRepository(engine)
    scan_request, scan_result = _scan()

    stored_scan = repository.save_scan(
        scan_request,
        scan_result,
        strategy_version="2.0.0",
    )
    backtest_request, backtest_result = _backtest(stored_scan.scan_id)
    stored_backtest = repository.save_backtest(
        backtest_request,
        backtest_result,
        strategy_version="2.0.0",
    )
    engine.dispose()

    reopened_engine = create_database_engine(database_url)
    reopened = DiscoveryResearchRepository(reopened_engine)
    restored_scan = reopened.get_scan(stored_scan.scan_id)
    restored_backtest = reopened.get_backtest(stored_backtest.backtest_id)

    assert restored_scan.request == scan_request
    assert restored_scan.result.candidates[0].score == 84
    assert restored_backtest.request == backtest_request
    assert restored_backtest.result.metrics.net_profit == Decimal("9.795")
    assert reopened.backtest_trades(stored_backtest.backtest_id) == list(
        backtest_result.trades
    )
    assert reopened.backtest_equity(stored_backtest.backtest_id) == list(
        backtest_result.equity_curve
    )
    reopened_engine.dispose()


def test_backtest_cannot_reference_unknown_scan(tmp_path) -> None:
    database_url = _database_url(tmp_path)
    apply_migrations(database_url)
    engine = create_database_engine(database_url)
    repository = DiscoveryResearchRepository(engine)
    request, result = _backtest("missing-scan")

    try:
        repository.save_backtest(request, result, strategy_version="2.0.0")
    except LookupError as error:
        assert "Unknown discovery scan" in str(error)
    else:
        raise AssertionError("Unknown scan reference should be rejected.")
    engine.dispose()
