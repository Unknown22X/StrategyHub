from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from fastapi.testclient import TestClient

from rangebot.domain.strategy import (
    StrategyDecisionCreate,
    StrategyInstanceCreate,
    TradeOwnershipCreate,
)
from rangebot.engine.api import create_app
from rangebot.engine.database import create_database_engine
from rangebot.engine.repository import ExchangeModeRepository
from rangebot.engine.strategy_instances import StrategyInstanceRepository


def test_activity_feed_combines_sources_filters_and_redacts_payload(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'activity.db'}"
    with TestClient(create_app(database_url)) as client:
        engine = create_database_engine(database_url)
        strategies = StrategyInstanceRepository(engine)
        exchange = ExchangeModeRepository(engine)

        instance = strategies.create(
            StrategyInstanceCreate(
                type_id="range",
                name="BTC Range Research",
                environment="live",
                symbol="BTC_USDT",
                timeframe_minutes=15,
                direction="long",
                configuration={
                    "timeframe_minutes": 15,
                    "direction": "long",
                },
            )
        )
        running = strategies.transition(instance.instance_id, "running")
        run = next(item for item in strategies.runs(running.instance_id) if item.ended_at is None)
        strategies.record_decision(
            instance.instance_id,
            StrategyDecisionCreate(
                occurred_at=datetime.now(UTC),
                signal="eligible_long",
                eligible=True,
                reason_codes=["range_ok", "spread_ok"],
                analysis={"range_percentage": "21.5"},
            ),
        )
        strategies.record_trade_ownership(
            TradeOwnershipCreate(
                identity_kind="order",
                external_identity="activity-order",
                origin="automatic_strategy",
                instance_id=instance.instance_id,
                run_id=run.run_id,
            )
        )
        exchange.persist_intent(
            "live",
            "activity-order",
            "market_entry",
            json.dumps(
                {
                    "symbol": "BTC_USDT",
                    "instance_id": instance.instance_id,
                    "private_marker": "must-never-appear",
                }
            ),
        )
        exchange.mark_intent("activity-order", "submitted")
        emergency = client.post(
            "/v1/paper/emergency-stop",
            json={
                "confirmation": "EMERGENCY STOP",
                "reason": "operator safety drill",
            },
        )
        assert emergency.status_code == 200

        response = client.get("/v1/activity?limit=100")
        assert response.status_code == 200
        events = response.json()
        categories = {event["category"] for event in events}
        assert {"decision", "strategy", "order", "risk", "system"} <= categories
        assert [event["occurred_at"] for event in events] == sorted(
            (event["occurred_at"] for event in events), reverse=True
        )
        body = response.text
        assert "must-never-appear" not in body
        order_event = next(event for event in events if event["event_id"] == "order:activity-order")
        assert order_event["symbol"] == "BTC_USDT"
        assert order_event["strategy_instance_id"] == instance.instance_id
        assert order_event["strategy_name"] == "BTC Range Research"
        assert order_event["status"] == "submitted"

        filtered = client.get(
            "/v1/activity",
            params={
                "category": "decision",
                "strategy_instance_id": instance.instance_id,
                "symbol": "BTC_USDT",
                "since": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            },
        )
        assert filtered.status_code == 200
        filtered_events = filtered.json()
        assert filtered_events
        assert {event["category"] for event in filtered_events} == {"decision"}
        assert {event["strategy_instance_id"] for event in filtered_events} == {
            instance.instance_id
        }


def test_exchange_operation_timestamps_survive_restart(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'activity-restart.db'}"
    with TestClient(create_app(database_url)):
        repository = ExchangeModeRepository(create_database_engine(database_url))
        repository.persist_intent("testnet", "restart-order", "limit_entry", "{}")
        repository.mark_intent("restart-order", "submitted")

    with TestClient(create_app(database_url)) as client:
        response = client.get("/v1/exchange/testnet/operations")
        assert response.status_code == 200
        operation = next(
            item for item in response.json() if item["client_request_id"] == "restart-order"
        )
        assert operation["created_at"]
        assert operation["updated_at"]
        assert operation["updated_at"] >= operation["created_at"]
