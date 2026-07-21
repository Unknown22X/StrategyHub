from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.strategy_runtime import NormalizedCandle
from rangebot.engine.api import create_app
from rangebot.engine.market_data_manager import MarketDataManager


class _PublicMarket:
    def eligible_contracts(self) -> list[PublicContract]:
        return [
            PublicContract(
                symbol="AKE_USDT",
                quantity_step=Decimal("1"),
                minimum_quantity=Decimal("1"),
            )
        ]

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        assert symbol == "AKE_USDT"
        return PublicMarketSnapshot(
            symbol=symbol,
            last_price=Decimal("0.0016964"),
            observed_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        )


def test_market_data_api_exposes_real_source_freshness_and_missing_states(
    tmp_path,
) -> None:
    now = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    manager = MarketDataManager(
        clock=lambda: now,
        freshness_threshold=timedelta(seconds=10),
    )
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("65000.25"),
            mark_price=Decimal("64998.75"),
            best_bid=Decimal("65000.00"),
            best_ask=Decimal("65000.50"),
            volume_24h=Decimal("123456789.12"),
            funding_rate=Decimal("0.0001"),
            observed_at=now,
            source="gate_rest",
            sequence=41,
        )
    )
    candle = NormalizedCandle(
        opened_at=now - timedelta(minutes=15),
        closed_at=now,
        open=Decimal("64900"),
        high=Decimal("65100"),
        low=Decimal("64850"),
        close=Decimal("65000.25"),
        volume=Decimal("1200"),
        closed=True,
    )
    manager.replace_candles("BTC_USDT", 15, [candle], source="gate_rest")
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"

    with TestClient(
        create_app(database_url, market_data_manager=manager)
    ) as client:
        snapshot = client.get("/v1/market-data/BTC_USDT")
        status = client.get("/v1/market-data/BTC_USDT/status")
        candles = client.get("/v1/market-data/BTC_USDT/candles/15")
        missing_snapshot = client.get("/v1/market-data/ETH_USDT")
        missing_status = client.get("/v1/market-data/ETH_USDT/status")
        missing_candles = client.get("/v1/market-data/ETH_USDT/candles/15")

    assert snapshot.status_code == 200
    assert snapshot.json()["last_price"] == "65000.25"
    assert snapshot.json()["mark_price"] == "64998.75"
    assert snapshot.json()["source"] == "gate_rest"
    assert snapshot.json()["state"] == "fresh"
    assert snapshot.json()["sequence"] == 41
    assert snapshot.json()["last_update_age_seconds"] == "0"
    assert status.status_code == 200
    assert status.json()["state"] == "fresh"
    assert status.json()["last_update_at"] is not None
    assert candles.status_code == 200
    assert candles.json()["source"] == "gate_rest"
    assert candles.json()["candles"][0]["close"] == "65000.25"
    assert missing_snapshot.status_code == 404
    assert missing_status.status_code == 200
    assert missing_status.json()["state"] == "unavailable"
    assert missing_status.json()["state_reason"] == "symbol_not_tracked"
    assert missing_candles.status_code == 404


def test_market_data_api_hydrates_untracked_symbol_from_public_rest(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rangebot.db'}"
    manager = MarketDataManager()

    with TestClient(
        create_app(
            database_url,
            market_data_manager=manager,
            public_market_provider=_PublicMarket(),
        )
    ) as client:
        response = client.get("/v1/market-data/AKE_USDT")

    assert response.status_code == 200
    assert response.json()["symbol"] == "AKE_USDT"
    assert response.json()["last_price"] == "0.0016964"
    assert response.json()["source"] == "gate_rest"
