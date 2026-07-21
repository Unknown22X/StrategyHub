from datetime import UTC, datetime, timedelta
from decimal import Decimal

from rangebot.domain.backtesting import BacktestPortfolioRequest, BacktestSettings
from rangebot.domain.discovery import DiscoveryMarketContract
from rangebot.domain.strategy import StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.backtest_repository import PortfolioBacktestRepository
from rangebot.engine.api import create_app
from rangebot.engine.database import apply_migrations, create_database_engine
from rangebot.engine.historical_backtesting import HistoricalBacktestService
from rangebot.engine.strategy_registry import StrategyRegistry
from fastapi.testclient import TestClient


class _Config:
    @staticmethod
    def model_validate(value):
        return value


class _Evaluator:
    type_id = "persisted_test"
    configuration_model = _Config

    def evaluate(self, context: StrategyEvaluationContext, configuration):
        eligible = context.last_price == Decimal("100")
        return StrategyEvaluationResult(
            type_id=self.type_id, symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal="long" if eligible else "none", eligible=eligible,
            reason_codes=("fixture",), explanation_ar="قرار محفوظ",
            used_closed_candles=len(context.completed_candles()),
            trade_request=StrategyTradeRequest(
                symbol=context.symbol, direction="long", reference_price=context.last_price,
                take_profit_price=Decimal("110"), stop_loss_price=Decimal("90"),
                reason_code="fixture",
            ) if eligible else None,
        )


class _MarketData:
    def __init__(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        self.values = tuple(
            NormalizedCandle(
                opened_at=start + timedelta(hours=index),
                closed_at=start + timedelta(hours=index + 1),
                open=Decimal(open_), high=Decimal(high), low=Decimal(low),
                close=Decimal(close), volume=Decimal("1000"), closed=True,
            )
            for index, (open_, high, low, close) in enumerate(
                (("99", "101", "98", "100"), ("100", "111", "99", "110"))
            )
        )

    def candles(self, symbol, timeframe_minutes, *, start, end):
        return self.values

    def latest_candles(self, symbol, timeframe_minutes, *, limit):
        return self.values[-limit:]

    def contracts(self, **kwargs):
        return (DiscoveryMarketContract(symbol="BTC_USDT", last_price=Decimal("100")),)


def _registry():
    registry = StrategyRegistry()
    registry.register(
        StrategyTypeMetadata(
            type_id="persisted_test", display_name_ar="اختبار",
            display_name_en="Test", description_ar="اختبار",
            description_en="Test", version="1", supported_timeframes=(60,),
            supports_backtesting=True, configuration_schema={},
        ),
        _Evaluator,
    )
    return registry


def test_completed_run_persists_snapshot_logs_and_editable_post_note(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'rangebot.db').as_posix()}"
    apply_migrations(database_url)
    repository = PortfolioBacktestRepository(create_database_engine(database_url))
    service = HistoricalBacktestService(_registry(), _MarketData(), repository)
    request = BacktestPortfolioRequest(
        mode="manual_symbols", strategy_type_id="persisted_test",
        strategy_version="1", symbols=("BTC_USDT",), timeframe_minutes=60,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        settings=BacktestSettings(
            initial_balance=Decimal("1000"), margin_per_trade=Decimal("100"),
            leverage=1, maker_fee_rate=Decimal("0"), taker_fee_rate=Decimal("0"),
            minimum_trades_for_assessment=1,
        ),
        pre_test_hypothesis="فرضية قبل الاختبار",
    )

    stored = service.run(request)
    updated = service.update_notes(stored.backtest_id, "ملاحظة بعد النتيجة")
    reloaded = service.get(stored.backtest_id)

    assert stored.status == "completed"
    assert stored.progress_percentage == 100
    assert stored.result is not None
    assert stored.result.trades[0].symbol == "BTC_USDT"
    assert stored.configuration_hash == reloaded.configuration_hash
    assert stored.input_data_hash is not None
    assert stored.request.code_version is not None
    assert updated.post_test_observations == "ملاحظة بعد النتيجة"
    assert reloaded.request.pre_test_hypothesis == "فرضية قبل الاختبار"


def test_portfolio_api_isolated_from_execution_routes(tmp_path) -> None:
    request = BacktestPortfolioRequest(
        mode="manual_symbols", strategy_type_id="persisted_test",
        strategy_version="1", symbols=("BTC_USDT",), timeframe_minutes=60,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        settings=BacktestSettings(
            initial_balance=Decimal("1000"), margin_per_trade=Decimal("100"),
            leverage=1, maker_fee_rate=Decimal("0"), taker_fee_rate=Decimal("0"),
            minimum_trades_for_assessment=1,
        ),
    )
    app = create_app(
        f"sqlite:///{tmp_path / 'api.db'}",
        strategy_registry=_registry(),
        historical_market_data_provider=_MarketData(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/backtests/portfolio", json=request.model_dump(mode="json")
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "queued"
        completed = client.get(
            f"/v1/backtests/portfolio/{payload['backtest_id']}"
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["result"]["orders"][0]["status"] == "filled"

    # Simulated orders exist only in the portfolio result and never in runtime order state.
    assert app.state.strategy_instance_repository.list() == []
