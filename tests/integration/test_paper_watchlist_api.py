from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.engine.api import create_app


class FakePublicMarketProvider:
    def eligible_contracts(self) -> list[PublicContract]:
        return [
            PublicContract(
                symbol="BTC_USDT",
                quantity_step=Decimal("0.001"),
                minimum_quantity=Decimal("0.001"),
            ),
            PublicContract(
                symbol="ETH_USDT",
                quantity_step=Decimal("0.01"),
                minimum_quantity=Decimal("0.01"),
            ),
            PublicContract(
                symbol="BASED_USDT",
                quantity_step=Decimal("1"),
                minimum_quantity=Decimal("1"),
            ),
        ]

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        return PublicMarketSnapshot(
            symbol=symbol,
            last_price=Decimal("100"),
            observed_at=datetime.now(UTC),
        )


def test_paper_watchlist_is_limited_and_active_change_stops_automation(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=FakePublicMarketProvider())

    with TestClient(app) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        contracts = client.get("/v1/paper/contracts", params={"query": "BTC"})
        client.post("/v1/paper/watchlist/BTC_USDT")
        client.post("/v1/paper/watchlist/ETH_USDT")
        client.post("/v1/paper/watchlist/BTC_USDT/active")
        client.post("/v1/paper/automatic-trading/start")
        changed = client.post("/v1/paper/watchlist/ETH_USDT/active")
        priority = client.patch(
            "/v1/paper/watchlist/BTC_USDT/priority", json={"priority": 0 + 1}
        )
        watchlist = client.get("/v1/paper/watchlist")

    assert contracts.json()[0]["symbol"] == "BTC_USDT"
    assert changed.status_code == 200
    assert priority.status_code == 200
    assert watchlist.json()["automatic_trading_enabled"] is False
    assert [item["symbol"] for item in watchlist.json()["items"]] == [
        "BTC_USDT",
        "ETH_USDT",
    ]
    assert watchlist.json()["items"][1]["is_active"] is True
    assert watchlist.json()["items"][0]["monitoring_only"] is True
    assert watchlist.json()["items"][0]["last_price"] == "100"


def test_paper_watchlist_accepts_url_encoded_pair_symbols(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    app = create_app(database_url, public_market_provider=FakePublicMarketProvider())

    with TestClient(app) as client:
        client.post("/v1/paper-account/initialize", json={"reason": "setup"})
        added = client.post("/v1/paper/watchlist/BASED%2FUSDT")
        active = client.post("/v1/paper/watchlist/BASED%2FUSDT/active")
        priority = client.patch(
            "/v1/paper/watchlist/BASED%2FUSDT/priority", json={"priority": 1}
        )
        direction = client.patch(
            "/v1/paper/watchlist/BASED%2FUSDT/direction",
            json={"direction": "long_only"},
        )
        watchlist = client.get("/v1/paper/watchlist")

    assert added.status_code == 204
    assert active.status_code == 200
    assert priority.status_code == 200
    assert direction.status_code == 200
    assert watchlist.json()["items"][0]["symbol"] == "BASED_USDT"
    assert watchlist.json()["items"][0]["is_active"] is True
    assert watchlist.json()["items"][0]["direction"] == "long_only"


def test_public_adapter_maps_only_domain_contract_and_price_fields() -> None:
    from rangebot.engine.market import GatePublicMarketAdapter

    contracts = GatePublicMarketAdapter.map_contracts(
        [
            {
                "name": "BTC_USDT",
                "in_delisting": False,
                "quanto_multiplier": "0.001",
                "order_size_min": 1,
                "private_key": "must not escape",
            },
            {
                "name": "BTC_USDC",
                "settle": "usdc",
                "quanto_multiplier": "0.001",
                "order_size_min": 1,
            },
        ]
    )
    snapshot = GatePublicMarketAdapter.map_last_price(
        {"contract": "BTC_USDT", "last": "101.25", "signature": "secret"}
    )

    assert contracts == [
        PublicContract(
            symbol="BTC_USDT",
            quantity_step=Decimal("0.001"),
            minimum_quantity=Decimal("0.001"),
        )
    ]
    assert snapshot.symbol == "BTC_USDT"
    assert snapshot.last_price == Decimal("101.25")
