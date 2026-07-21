from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from rangebot.domain.strategy_runtime import NormalizedCandle, StrategyEvaluationContext
from rangebot.engine.api import create_app
from tests.integration.workflow_test_helpers import authorize_existing_strategy_instance


def _trend_context(symbol: str = "BTC_USDT") -> StrategyEvaluationContext:
    base = datetime(2026, 2, 1, tzinfo=UTC)
    candles = tuple(
        NormalizedCandle(
            opened_at=base + timedelta(minutes=index * 15),
            closed_at=base + timedelta(minutes=(index + 1) * 15),
            open=Decimal(100 + index) - Decimal("0.5"),
            high=Decimal(100 + index) + Decimal("1"),
            low=Decimal(100 + index) - Decimal("1.5"),
            close=Decimal(100 + index),
            volume=Decimal("100"),
            closed=True,
        )
        for index in range(10)
    )
    return StrategyEvaluationContext(
        symbol=symbol,
        evaluated_at=candles[-1].closed_at,
        timeframe_minutes=15,
        candles=candles,
        last_price=candles[-1].close,
        mark_price=candles[-1].close,
        best_bid=candles[-1].close - Decimal("0.05"),
        best_ask=candles[-1].close + Decimal("0.05"),
    )


def test_strategy_manager_resolves_evaluator_and_records_explainable_decision(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url)
    payload = {
        "type_id": "adaptive_trend",
        "name": "BTC Trend",
        "environment": "paper",
        "symbol": "BTC_USDT",
        "timeframe_minutes": 15,
        "direction": "both",
        "configuration": {
            "fast_ema_period": 3,
            "slow_ema_period": 5,
            "adx_period": 3,
            "minimum_adx": "0",
            "atr_period": 3,
            "maximum_spread_percentage": "1",
        },
    }

    with TestClient(app) as client:
        instance = client.post("/v1/strategies", json=payload).json()
        instance_id = instance["instance_id"]
        authorize_existing_strategy_instance(client.app, instance_id)
        client.post(f"/v1/strategies/{instance_id}/start")

        result = app.state.strategy_manager.evaluate(instance_id, _trend_context())
        decisions = client.get(f"/v1/strategies/{instance_id}/decisions")

        assert result.eligible is True
        assert result.signal == "long"
        assert result.trade_request is not None
        assert decisions.status_code == 200
        assert decisions.json()[0]["signal"] == "long"
        assert decisions.json()[0]["analysis"]["trend"] == "upward"
        assert "explanation_ar" in decisions.json()[0]["analysis"]
        assert decisions.json()[0]["analysis"]["trade_request"]["direction"] == "long"

        with pytest.raises(ValueError, match="symbol"):
            app.state.strategy_manager.evaluate(
                instance_id, _trend_context("ETH_USDT")
            )

        client.post(f"/v1/strategies/{instance_id}/stop")
        with pytest.raises(RuntimeError, match="running or monitoring"):
            app.state.strategy_manager.evaluate(instance_id, _trend_context())

        client.put(
            f"/v1/strategies/{instance_id}",
            json={"direction": "short"},
        )
        client.post(f"/v1/strategies/{instance_id}/start")
        direction_blocked = app.state.strategy_manager.evaluate(
            instance_id, _trend_context()
        )

        assert direction_blocked.eligible is False
        assert direction_blocked.signal == "none"
        assert "long_direction_disabled" in direction_blocked.reason_codes
