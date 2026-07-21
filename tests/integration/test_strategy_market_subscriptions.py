from fastapi.testclient import TestClient

from rangebot.engine.api import create_app
from rangebot.engine.gate_websocket import MarketSubscriptionRegistry


CONFIGURATION = {
    "mode": "rolling_window",
    "minimum_range_percentage": "20",
    "maximum_range_percentage": "25",
}


def _payload(name: str, symbol: str) -> dict[str, object]:
    return {
        "type_id": "range",
        "name": name,
        "environment": "paper",
        "symbol": symbol,
        "timeframe_minutes": 15,
        "direction": "both",
        "requested_margin": "20",
        "requested_leverage": 1,
        "configuration": CONFIGURATION,
    }


def test_configured_pinned_running_and_restored_symbols_stay_subscribed(
    tmp_path,
) -> None:
    registry = MarketSubscriptionRegistry()
    app = create_app(
        f"sqlite:///{tmp_path / 'rangebot.db'}",
        market_subscription_registry=registry,
    )

    with TestClient(app) as client:
        btc = client.post("/v1/strategies", json=_payload("BTC", "BTC_USDT")).json()
        eth = client.post("/v1/strategies", json=_payload("ETH", "ETH_USDT")).json()
        client.post(f"/v1/strategies/{btc['instance_id']}/pin")
        client.post(f"/v1/strategies/{btc['instance_id']}/start")
        _, targets = registry.snapshot()
        assert {target.symbol for target in targets} >= {"BTC_USDT", "ETH_USDT"}

        client.post(f"/v1/strategies/{btc['instance_id']}/stop")
        client.post(f"/v1/strategies/{eth['instance_id']}/archive")
        _, archived_targets = registry.snapshot()
        assert "BTC_USDT" in {target.symbol for target in archived_targets}
        assert "ETH_USDT" not in {target.symbol for target in archived_targets}

        client.post(f"/v1/strategies/{eth['instance_id']}/restore")
        _, restored_targets = registry.snapshot()
        assert {target.symbol for target in restored_targets} >= {
            "BTC_USDT",
            "ETH_USDT",
        }
