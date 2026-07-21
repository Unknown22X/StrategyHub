from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from rangebot.engine.contract_rules import GateContractRulesProvider
from rangebot.engine.gate_websocket import LIVE_REST_URL, TESTNET_REST_URL
from rangebot.engine.historical_market_data import GateHistoricalMarketDataProvider
from rangebot.engine.market import GatePublicMarketProvider
from rangebot.engine.public_rest_runtime import PublicRestEnvironmentManager


@pytest.mark.parametrize(
    ("environment", "expected_base", "forbidden_base"),
    (
        ("testnet", TESTNET_REST_URL, LIVE_REST_URL),
        ("live", LIVE_REST_URL, TESTNET_REST_URL),
    ),
)
def test_gate_public_rest_providers_use_only_selected_environment(
    environment: str,
    expected_base: str,
    forbidden_base: str,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path.endswith("/contracts/BTC_USDT"):
            return httpx.Response(
                200,
                json={
                    "name": "BTC_USDT",
                    "status": "trading",
                    "in_delisting": False,
                    "settle": "usdt",
                    "contract_type": "perpetual",
                    "quanto_multiplier": "0.0001",
                    "order_size_round": "1",
                    "order_size_min": "1",
                    "order_value_min": "1",
                    "order_size_max": "100000",
                    "market_order_size_max": "50000",
                    "order_price_round": "0.1",
                    "leverage_max": "20",
                    "maintenance_rate": "0.005",
                    "maker_fee_rate": "0.0002",
                    "taker_fee_rate": "0.0005",
                    "last": "100",
                },
            )
        if request.url.path.endswith("/candlesticks"):
            return httpx.Response(
                200,
                json=[
                    {
                        "t": 1_700_000_000,
                        "o": "100",
                        "h": "101",
                        "l": "99",
                        "c": "100.5",
                        "v": "10",
                    },
                    {
                        "t": 1_700_000_060,
                        "o": "100.5",
                        "h": "102",
                        "l": "100",
                        "c": "101",
                        "v": "12",
                    },
                ],
            )
        return httpx.Response(404, json={"label": "NOT_FOUND"})

    transport = httpx.MockTransport(handler)
    GateContractRulesProvider(
        environment=environment,
        transport=transport,
    )("BTC_USDT")
    GatePublicMarketProvider(
        environment=environment,
        transport=transport,
    ).snapshot("BTC_USDT")
    GateHistoricalMarketDataProvider(
        environment,
        transport=transport,
        clock=lambda: datetime(2025, 1, 1, tzinfo=UTC),
    ).latest_candles("BTC_USDT", 1, limit=1)

    assert requested_urls
    assert all(url.startswith(expected_base) for url in requested_urls)
    assert all(not url.startswith(forbidden_base) for url in requested_urls)


class _ProviderMarker:
    def __init__(self, kind: str, environment: str, generation: int) -> None:
        self.kind = kind
        self.environment = environment
        self.generation = generation


def test_public_rest_runtime_rebuilds_all_providers_and_documents_paper_policy() -> (
    None
):
    created: list[_ProviderMarker] = []

    def factory(kind: str):
        def build(environment: str) -> _ProviderMarker:
            marker = _ProviderMarker(kind, environment, len(created) + 1)
            created.append(marker)
            return marker

        return build

    runtime = PublicRestEnvironmentManager(
        "paper",
        public_market_factory=factory("market"),
        contract_rules_factory=factory("rules"),
        historical_factory=factory("historical"),
    )
    paper_providers = (
        runtime.current_public_market(),
        runtime.current_contract_rules(),
        runtime.current_historical(),
    )

    assert runtime.application_environment == "paper"
    assert runtime.effective_environment == "live"
    assert [item.environment for item in created] == ["live", "live", "live"]

    runtime.activate("testnet")
    testnet_providers = (
        runtime.current_public_market(),
        runtime.current_contract_rules(),
        runtime.current_historical(),
    )
    assert runtime.application_environment == "testnet"
    assert runtime.effective_environment == "testnet"
    assert all(item.environment == "testnet" for item in testnet_providers)
    assert all(
        before is not after for before, after in zip(paper_providers, testnet_providers)
    )

    runtime.activate("live")
    live_providers = (
        runtime.current_public_market(),
        runtime.current_contract_rules(),
        runtime.current_historical(),
    )
    assert runtime.application_environment == "live"
    assert runtime.effective_environment == "live"
    assert all(item.environment == "live" for item in live_providers)
    assert all(
        before is not after for before, after in zip(testnet_providers, live_providers)
    )
    assert runtime.revision == 3


def test_public_rest_runtime_keeps_previous_generation_when_rebuild_fails() -> None:
    def failing_rules(environment: str) -> _ProviderMarker:
        if environment == "testnet":
            raise RuntimeError("temporary provider construction failure")
        return _ProviderMarker("rules", environment, 1)

    runtime = PublicRestEnvironmentManager(
        "live",
        public_market_factory=lambda environment: _ProviderMarker(
            "market", environment, 1
        ),
        contract_rules_factory=failing_rules,
        historical_factory=lambda environment: _ProviderMarker(
            "historical", environment, 1
        ),
    )
    previous = (
        runtime.current_public_market(),
        runtime.current_contract_rules(),
        runtime.current_historical(),
    )

    with pytest.raises(RuntimeError):
        runtime.activate("testnet")

    assert runtime.application_environment == "live"
    assert runtime.effective_environment == "live"
    assert previous == (
        runtime.current_public_market(),
        runtime.current_contract_rules(),
        runtime.current_historical(),
    )
    assert runtime.revision == 1
