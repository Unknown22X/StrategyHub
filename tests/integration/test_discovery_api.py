from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from rangebot.domain.discovery import (
    DiscoveryMarketContract,
    StrategyScanCandidate,
)
from rangebot.domain.strategy import StrategyFieldMetadata, StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.engine.api import create_app
from rangebot.engine.strategy_registry import StrategyRegistry


class _Configuration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_close: Decimal = Decimal("100")
    direction: Literal["long_only", "short_only", "both"] = "both"


class _Evaluator:
    type_id = "api_research"
    configuration_model = _Configuration

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult:
        parsed = self.configuration_model.model_validate(configuration)
        eligible = context.last_price == parsed.signal_close
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal="long" if eligible else "none",
            eligible=eligible,
            reason_codes=("api_research",),
            explanation_ar="إشارة اختبار خلفي.",
            used_closed_candles=len(context.completed_candles()),
            trade_request=StrategyTradeRequest(
                symbol=context.symbol,
                direction="long",
                reference_price=context.last_price,
                take_profit_price=Decimal("105"),
                stop_loss_price=Decimal("95"),
                reason_code="api_research",
            )
            if eligible
            else None,
        )


class _Scanner:
    type_id = "api_research"

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate:
        del configuration
        return StrategyScanCandidate(
            symbol=context.symbol,
            score=91,
            signal="long",
            eligible_now=True,
            evaluated_at=context.evaluated_at,
            market_data_state="fresh",
            explanation_ar="مرشح صالح للاختبار الخلفي.",
            metrics={"quality": Decimal("0.91")},
            completed_candles=len(context.candles),
            backtest_ready=len(context.candles) >= minimum_backtest_candles,
        )


class _MarketData:
    def __init__(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        self.candle_rows = (
            NormalizedCandle(
                opened_at=base,
                closed_at=base + timedelta(minutes=1),
                open=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("1000"),
            ),
            NormalizedCandle(
                opened_at=base + timedelta(minutes=1),
                closed_at=base + timedelta(minutes=2),
                open=Decimal("100"),
                high=Decimal("106"),
                low=Decimal("99"),
                close=Decimal("104"),
                volume=Decimal("1000"),
            ),
        )

    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]:
        del minimum_quote_volume, maximum_contracts
        return (
            DiscoveryMarketContract(
                symbol="BTC_USDT",
                last_price=Decimal("100"),
                mark_price=Decimal("100"),
                best_bid=Decimal("99.9"),
                best_ask=Decimal("100.1"),
                volume_24h_quote=Decimal("1000000"),
            ),
        )

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]:
        del symbol, timeframe_minutes
        return self.candle_rows[-limit:]

    def candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedCandle, ...]:
        del symbol, timeframe_minutes
        return tuple(
            candle
            for candle in self.candle_rows
            if start <= candle.opened_at < end
        )


def _registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        StrategyTypeMetadata(
            type_id="api_research",
            display_name_ar="بحث API",
            display_name_en="API Research",
            description_ar="استراتيجية اختبار API.",
            description_en="API test strategy.",
            version="4.0.0",
            supported_timeframes=(1,),
            supports_scanning=True,
            supports_backtesting=True,
            minimum_backtest_candles=2,
            configuration_schema=_Configuration.model_json_schema(),
            candidate_metrics=(
                StrategyFieldMetadata(
                    key="quality",
                    label_ar="الجودة",
                    label_en="Quality",
                    value_type="decimal",
                ),
            ),
        ),
        _Evaluator,
        _Scanner,
    )
    return registry


def test_discovery_backtest_and_stopped_strategy_api_flow(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(
        database_url,
        strategy_registry=_registry(),
        historical_market_data_provider=_MarketData(),
    )
    configuration = {"signal_close": "100", "direction": "both"}

    with TestClient(app) as client:
        scan_response = client.post(
            "/v1/discovery/scans",
            json={
                "strategy_type_id": "api_research",
                "timeframe_minutes": 1,
                "configuration": configuration,
                "maximum_symbols": 5,
                "maximum_candidates": 5,
            },
        )
        assert scan_response.status_code == 200
        scan = scan_response.json()
        assert scan["strategy_version"] == "4.0.0"
        assert scan["result"]["candidates"][0]["symbol"] == "BTC_USDT"

        backtest_response = client.post(
            "/v1/backtests",
            json={
                "scan_id": scan["scan_id"],
                "strategy_type_id": "api_research",
                "symbol": "BTC_USDT",
                "timeframe_minutes": 1,
                "configuration": configuration,
                "start": _MarketData().candle_rows[0].opened_at.isoformat(),
                "end": _MarketData().candle_rows[-1].closed_at.isoformat(),
                "settings": {
                    "initial_balance": "1000",
                    "margin_per_trade": "100",
                    "leverage": 1,
                    "taker_fee_rate": "0",
                    "minimum_trades_for_assessment": 1,
                },
            },
        )
        assert backtest_response.status_code == 200
        backtest = backtest_response.json()
        assert backtest["result"]["metrics"]["total_trades"] == 1

        trades = client.get(
            f"/v1/backtests/{backtest['backtest_id']}/trades"
        )
        equity = client.get(
            f"/v1/backtests/{backtest['backtest_id']}/equity"
        )
        assert trades.status_code == 200
        assert len(trades.json()) == 1
        assert equity.status_code == 200
        assert len(equity.json()) == 2

        strategy_response = client.post(
            f"/v1/backtests/{backtest['backtest_id']}/create-strategy",
            json={
                "name": "BTC Backtest Review",
                "environment": "paper",
                "direction": "both",
            },
        )
        assert strategy_response.status_code == 200
        strategy = strategy_response.json()
        assert strategy["status"] == "stopped"
        assert strategy["symbol"] == "BTC_USDT"

        stored = client.get(f"/v1/backtests/{backtest['backtest_id']}").json()
        assert stored["applied_instance_id"] == strategy["instance_id"]


def test_research_api_returns_not_found_for_unknown_records(tmp_path) -> None:
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        strategy_registry=_registry(),
        historical_market_data_provider=_MarketData(),
    )

    with TestClient(app) as client:
        assert client.get("/v1/discovery/scans/missing").status_code == 404
        assert client.get("/v1/backtests/missing").status_code == 404
        assert client.get("/v1/backtests/missing/trades").status_code == 404
