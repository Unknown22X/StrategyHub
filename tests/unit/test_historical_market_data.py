from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from rangebot.engine.historical_market_data import GateHistoricalMarketDataProvider


def test_contract_universe_excludes_delisting_and_ranks_by_quote_volume() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/contracts"):
            return httpx.Response(
                200,
                json=[
                    {"name": "BTC_USDT", "in_delisting": False},
                    {"name": "ETH_USDT", "in_delisting": False},
                    {"name": "OLD_USDT", "in_delisting": True},
                ],
            )
        if request.url.path.endswith("/tickers"):
            return httpx.Response(
                200,
                json=[
                    {
                        "contract": "BTC_USDT",
                        "last": "60000",
                        "mark_price": "60010",
                        "index_price": "60005",
                        "highest_bid": "59999",
                        "lowest_ask": "60001",
                        "volume_24h_quote": "1000000",
                        "funding_rate": "0.0001",
                        "change_percentage": "2.5",
                        "high_24h": "61000",
                        "low_24h": "58000",
                    },
                    {
                        "contract": "ETH_USDT",
                        "last": "3000",
                        "mark_price": "3001",
                        "index_price": "3000.5",
                        "highest_bid": "2999.9",
                        "lowest_ask": "3000.1",
                        "volume_24h_quote": "2500000",
                        "funding_rate": "-0.0002",
                        "change_percentage": "-1.5",
                        "high_24h": "3100",
                        "low_24h": "2900",
                    },
                    {
                        "contract": "OLD_USDT",
                        "last": "1",
                        "volume_24h_quote": "9999999",
                    },
                ],
            )
        raise AssertionError(f"Unexpected path: {request.url.path}")

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
    )

    contracts = provider.contracts(minimum_quote_volume=Decimal("500000"))

    assert [contract.symbol for contract in contracts] == ["ETH_USDT", "BTC_USDT"]
    assert contracts[0].funding_rate == Decimal("-0.0002")
    assert contracts[0].best_bid == Decimal("2999.9")
    assert contracts[0].best_ask == Decimal("3000.1")


def test_candle_loader_excludes_current_unfinished_candle() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    def clock():
        return base + timedelta(minutes=3, seconds=30)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/candlesticks")
        return httpx.Response(
            200,
            json=[
                {
                    "t": int((base + timedelta(minutes=index)).timestamp()),
                    "o": "100",
                    "h": "105",
                    "l": "99",
                    "c": str(100 + index),
                    "v": "1000",
                }
                for index in range(4)
            ],
        )

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
        clock=clock,
    )

    candles = provider.candles(
        "BTC_USDT",
        1,
        start=base,
        end=base + timedelta(minutes=4),
    )

    assert [candle.opened_at for candle in candles] == [
        base,
        base + timedelta(minutes=1),
        base + timedelta(minutes=2),
    ]
    assert all(candle.closed for candle in candles)


def test_candle_loader_paginates_and_deduplicates_chunk_boundaries() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    end = base + timedelta(minutes=2002)
    requests: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start_epoch = int(request.url.params["from"])
        end_epoch = int(request.url.params["to"])
        requests.append((start_epoch, end_epoch))
        start_index = (start_epoch - int(base.timestamp())) // 60
        end_index = (end_epoch - int(base.timestamp())) // 60
        response = []
        if len(requests) > 1:
            start_index -= 1  # Gate or proxies may repeat a boundary candle.
        for index in range(start_index, end_index + 1):
            response.append(
                {
                    "t": int((base + timedelta(minutes=index)).timestamp()),
                    "o": "100",
                    "h": "101",
                    "l": "99",
                    "c": "100",
                    "v": "1",
                }
            )
        return httpx.Response(200, json=response)

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
        clock=lambda: end + timedelta(days=1),
    )

    candles = provider.candles("BTC_USDT", 1, start=base, end=end)

    assert len(requests) == 2
    assert len(candles) == 2002
    assert candles[0].opened_at == base
    assert candles[-1].opened_at == base + timedelta(minutes=2001)
    assert len({candle.opened_at for candle in candles}) == len(candles)


def test_funding_cost_uses_signed_gate_rates_for_long_and_short() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/funding_rate")
        return httpx.Response(
            200,
            json=[
                {"t": int((base + timedelta(hours=8)).timestamp()), "r": "0.001"},
                {"t": int((base + timedelta(hours=16)).timestamp()), "r": "-0.00025"},
            ],
        )

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
    )

    long_cost = provider.cost(
        symbol="BTC_USDT",
        direction="long",
        notional=Decimal("1000"),
        entered_at=base,
        exited_at=base + timedelta(hours=20),
    )
    short_cost = provider.cost(
        symbol="BTC_USDT",
        direction="short",
        notional=Decimal("1000"),
        entered_at=base,
        exited_at=base + timedelta(hours=20),
    )

    assert long_cost == Decimal("0.75000")
    assert short_cost == Decimal("-0.75000")
    assert "القيمة الاسمية عند الدخول" in provider.warning_ar


def test_funding_history_excludes_entry_timestamp_and_deduplicates_records() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"t": int(base.timestamp()), "r": "0.9"},
                {"t": int((base + timedelta(hours=8)).timestamp()), "r": "0.001"},
                {"t": int((base + timedelta(hours=8)).timestamp()), "r": "0.001"},
            ],
        )

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
    )

    rates = provider.funding_rates(
        "BTC_USDT",
        start=base,
        end=base + timedelta(hours=9),
    )

    assert rates == ((base + timedelta(hours=8), Decimal("0.001")),)


def test_latest_candles_requests_extra_point_and_returns_only_completed_limit() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "4"
        return httpx.Response(
            200,
            json=[
                {
                    "t": int((base + timedelta(minutes=index)).timestamp()),
                    "o": "100",
                    "h": "101",
                    "l": "99",
                    "c": "100",
                    "v": "1",
                }
                for index in range(4)
            ],
        )

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
        clock=lambda: base + timedelta(minutes=3, seconds=20),
    )

    candles = provider.latest_candles("BTC_USDT", 1, limit=3)

    assert len(candles) == 3
    assert candles[-1].opened_at == base + timedelta(minutes=2)


def test_historical_provider_reuses_client_and_retries_temporary_failures() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"label": "temporary"})
        return httpx.Response(200, json=[])

    provider = GateHistoricalMarketDataProvider(
        "live",
        transport=httpx.MockTransport(handler),
        maximum_attempts=3,
        retry_delay_seconds=0.1,
        sleep=delays.append,
    )

    assert provider.contracts() == ()
    assert attempts == 4  # contracts and tickers share one reusable client after retry.
    assert delays == [0.1, 0.2]
    provider.close()
