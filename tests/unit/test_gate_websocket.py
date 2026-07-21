import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import httpx
import pytest

from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.engine.gate_websocket import (
    GateFuturesMessageHandler,
    GateFuturesRestSnapshotProvider,
    GateFuturesWebSocketService,
    GateMarketTarget,
    GateWebSocketHeartbeatTimeout,
    LIVE_WEBSOCKET_URL,
    MarketSubscriptionRegistry,
    TESTNET_WEBSOCKET_URL,
    subscription_messages,
)
from rangebot.engine.market_data_manager import MarketDataManager


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _snapshot(
    sequence: int,
    *,
    price: str = "100",
    symbol: str = "BTC_USDT",
) -> MarketPriceUpdate:
    last = Decimal(price)
    return MarketPriceUpdate(
        symbol=symbol,
        last_price=last,
        mark_price=last - Decimal("0.1"),
        index_price=last - Decimal("0.15"),
        best_bid=last - Decimal("0.2"),
        best_ask=last + Decimal("0.2"),
        change_percentage_24h=Decimal("1.5"),
        high_24h=last + Decimal("5"),
        low_24h=last - Decimal("5"),
        volume_24h=Decimal("1000"),
        open_interest=Decimal("500"),
        funding_rate=Decimal("-0.0001"),
        next_funding_at=NOW + timedelta(hours=4),
        observed_at=NOW,
        source="gate_rest",
        sequence=sequence,
    )


def test_subscription_registry_is_deduplicated_revisioned_and_validated() -> None:
    target = GateMarketTarget("BTC_USDT", 5)
    registry = MarketSubscriptionRegistry((target, target))

    revision, targets = registry.snapshot()
    unchanged = registry.replace((target,))
    changed = registry.replace((target, GateMarketTarget("ETH_USDT", 15)))

    assert revision == 1
    assert targets == (target,)
    assert unchanged == 1
    assert changed == 2
    assert registry.snapshot()[1] == (
        target,
        GateMarketTarget("ETH_USDT", 15),
    )
    with pytest.raises(ValueError, match="uppercase"):
        GateMarketTarget("btc_usdt", 5)
    with pytest.raises(ValueError, match="Unsupported"):
        GateMarketTarget("BTC_USDT", 2)


def test_subscription_messages_deduplicate_symbol_channels() -> None:
    targets = (
        GateMarketTarget("BTC_USDT", 5),
        GateMarketTarget("BTC_USDT", 15),
    )

    messages = subscription_messages(targets, event="subscribe", now=123)

    assert [message["channel"] for message in messages] == [
        "futures.tickers",
        "futures.book_ticker",
        "futures.order_book_update",
        "futures.candlesticks",
        "futures.candlesticks",
    ]
    assert messages[2]["payload"] == ["BTC_USDT", "100ms", "100"]
    assert messages[3]["payload"] == ["5m", "BTC_USDT"]
    assert messages[4]["payload"] == ["15m", "BTC_USDT"]
    assert all(message["event"] == "subscribe" for message in messages)


def test_rest_snapshot_maps_prices_depth_sequence_and_negative_funding() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/contracts/BTC_USDT"):
            return httpx.Response(
                200,
                json={
                    "name": "BTC_USDT",
                    "last_price": "65000.5",
                    "mark_price": "64999.9",
                    "index_price": "64998.8",
                    "position_size": "25000",
                    "volume_24h_quote": "12500000",
                    "funding_rate": "-0.0002",
                    "funding_next_apply": 1784318400,
                },
            )
        return httpx.Response(
            200,
            json={
                "id": 900,
                "current": 1784289600.5,
                "bids": [{"p": "65000.0", "s": "10"}],
                "asks": [{"p": "65001.0", "s": "8"}],
            },
        )

    provider = GateFuturesRestSnapshotProvider(
        "live",
        base_url="https://gate.invalid/api/v4/futures/usdt",
        transport=httpx.MockTransport(handle),
    )

    snapshot = provider.snapshot("BTC_USDT")

    assert snapshot.last_price == Decimal("65000.5")
    assert snapshot.mark_price == Decimal("64999.9")
    assert snapshot.index_price == Decimal("64998.8")
    assert snapshot.best_bid == Decimal("65000.0")
    assert snapshot.best_ask == Decimal("65001.0")
    assert snapshot.open_interest == Decimal("25000")
    assert snapshot.funding_rate == Decimal("-0.0002")
    assert snapshot.next_funding_at == datetime.fromtimestamp(1784318400, UTC)
    assert snapshot.sequence == 900
    assert snapshot.source == "gate_rest"
    assert len(requests) == 2
    assert requests[1].url.params["with_id"] == "true"
    assert requests[1].url.params["limit"] == "1"


def test_ticker_update_maps_contract_statistics_and_preserves_next_funding() -> None:
    async def scenario() -> None:
        manager = MarketDataManager(clock=lambda: NOW)
        handler = GateFuturesMessageHandler(manager, lambda symbol: _snapshot(100))
        await handler.bootstrap(("BTC_USDT",))

        await handler.handle(
            json.dumps(
                {
                    "time": 1784289600,
                    "channel": "futures.tickers",
                    "event": "update",
                    "result": [
                        {
                            "contract": "BTC_USDT",
                            "last": "101",
                            "mark_price": "100.9",
                            "index_price": "100.8",
                            "highest_bid": "100.7",
                            "lowest_ask": "101.1",
                            "change_percentage": "2.4",
                            "high_24h": "105",
                            "low_24h": "95",
                            "volume_24h_quote": "2000",
                            "total_size": "750",
                            "funding_rate": "-0.0003",
                        }
                    ],
                }
            )
        )

        market = manager.snapshot("BTC_USDT")
        assert market.last_price == Decimal("101")
        assert market.mark_price == Decimal("100.9")
        assert market.index_price == Decimal("100.8")
        assert market.best_bid == Decimal("100.7")
        assert market.best_ask == Decimal("101.1")
        assert market.change_percentage_24h == Decimal("2.4")
        assert market.high_24h == Decimal("105")
        assert market.low_24h == Decimal("95")
        assert market.volume_24h == Decimal("2000")
        assert market.open_interest == Decimal("750")
        assert market.funding_rate == Decimal("-0.0003")
        assert market.next_funding_at == NOW + timedelta(hours=4)

    asyncio.run(scenario())


def test_message_handler_merges_channels_candles_and_restores_sequence_gap() -> None:
    async def scenario() -> None:
        manager = MarketDataManager(clock=lambda: NOW)
        rest_calls: list[str] = []

        def rest(symbol: str) -> MarketPriceUpdate:
            rest_calls.append(symbol)
            return _snapshot(100 if len(rest_calls) == 1 else 110, symbol=symbol)

        handler = GateFuturesMessageHandler(manager, rest)
        await handler.bootstrap(("BTC_USDT",))
        await handler.handle(
            json.dumps(
                {
                    "time": 1784289600,
                    "channel": "futures.tickers",
                    "event": "update",
                    "result": [
                        {
                            "contract": "BTC_USDT",
                            "last": "101",
                            "mark_price": "100.9",
                            "volume_24h_quote": "2000",
                            "funding_rate": "-0.0003",
                        }
                    ],
                }
            )
        )
        await handler.handle(
            json.dumps(
                {
                    "time_ms": 1784289600100,
                    "channel": "futures.book_ticker",
                    "event": "update",
                    "result": {
                        "s": "BTC_USDT",
                        "b": "100.8",
                        "a": "101.2",
                    },
                }
            )
        )
        await handler.handle(
            json.dumps(
                {
                    "channel": "futures.candlesticks",
                    "event": "update",
                    "result": [
                        {
                            "t": 1784289300,
                            "o": "100",
                            "h": "102",
                            "l": "99",
                            "c": "101",
                            "v": "500",
                            "n": "5m_BTC_USDT",
                            "w": True,
                        }
                    ],
                }
            )
        )
        await handler.handle(
            json.dumps(
                {
                    "time_ms": 1784289600200,
                    "channel": "futures.order_book_update",
                    "event": "update",
                    "result": {
                        "s": "BTC_USDT",
                        "U": 102,
                        "u": 105,
                        "b": [],
                        "a": [],
                    },
                }
            )
        )

        market = manager.snapshot("BTC_USDT")
        candles = manager.candle_series("BTC_USDT", 5)
        assert market.state == "fresh"
        assert market.last_price == Decimal("100")
        assert market.best_bid == Decimal("99.8")
        assert market.best_ask == Decimal("100.2")
        assert market.funding_rate == Decimal("-0.0001")
        assert market.sequence == 110
        assert rest_calls == ["BTC_USDT", "BTC_USDT"]
        assert len(candles.candles) == 1
        assert candles.candles[0].closed is True
        assert candles.candles[0].close == Decimal("101")

    asyncio.run(scenario())


def test_message_handler_accepts_contiguous_gate_sequence_range() -> None:
    async def scenario() -> None:
        manager = MarketDataManager(clock=lambda: NOW)
        handler = GateFuturesMessageHandler(manager, lambda symbol: _snapshot(100))
        await handler.bootstrap(("BTC_USDT",))

        await handler.handle(
            json.dumps(
                {
                    "time_ms": 1784289600200,
                    "channel": "futures.order_book_update",
                    "event": "update",
                    "result": {
                        "s": "BTC_USDT",
                        "U": 101,
                        "u": 105,
                        "b": [],
                        "a": [],
                    },
                }
            )
        )

        market = manager.snapshot("BTC_USDT")
        assert market.state == "fresh"
        assert market.sequence == 105
        assert market.sequence_gap is False

    asyncio.run(scenario())


class FakeConnection:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.incoming: asyncio.Queue[str | bytes | BaseException] = asyncio.Queue()

    async def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    async def recv(self) -> str | bytes:
        value = await self.incoming.get()
        if isinstance(value, BaseException):
            raise value
        return value


class FakeConnectionContext(AbstractAsyncContextManager[FakeConnection]):
    def __init__(self, connection: FakeConnection, enter_error: Exception | None = None) -> None:
        self.connection = connection
        self.enter_error = enter_error

    async def __aenter__(self) -> FakeConnection:
        if self.enter_error is not None:
            raise self.enter_error
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


class SequencedFactory:
    def __init__(self, contexts: list[FakeConnectionContext]) -> None:
        self.contexts = contexts
        self.urls: list[str] = []

    def __call__(self, url: str) -> FakeConnectionContext:
        self.urls.append(url)
        if not self.contexts:
            raise RuntimeError("No fake Gate connection remains.")
        return self.contexts.pop(0)


def test_service_reconnects_and_resubscribes_dynamic_targets() -> None:
    async def scenario() -> None:
        manager = MarketDataManager(clock=lambda: NOW)
        registry = MarketSubscriptionRegistry((GateMarketTarget("BTC_USDT", 5),))
        failed = FakeConnectionContext(FakeConnection(), ConnectionError("offline"))
        connection = FakeConnection()
        factory = SequencedFactory([failed, FakeConnectionContext(connection)])
        stop = asyncio.Event()
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)
            await asyncio.sleep(0)

        service = GateFuturesWebSocketService(
            environment="testnet",
            market_data=manager,
            subscriptions=registry,
            rest_snapshot=lambda symbol: _snapshot(
                10,
                symbol=symbol,
                price="100" if symbol == "BTC_USDT" else "200",
            ),
            connection_factory=factory,
            reconnect_delays_seconds=(0,),
            heartbeat_interval_seconds=1,
            heartbeat_timeout_seconds=1,
            sleep=sleep,
            epoch_clock=lambda: 123.0,
        )
        task = asyncio.create_task(service.run(stop))

        while len(connection.sent) < 4:
            await asyncio.sleep(0)
        registry.replace(
            (
                GateMarketTarget("BTC_USDT", 5),
                GateMarketTarget("ETH_USDT", 15),
            )
        )
        await connection.incoming.put(
            json.dumps(
                {
                    "time": 123,
                    "channel": "futures.pong",
                    "event": "update",
                    "result": None,
                }
            )
        )
        while len(connection.sent) < 13:
            await asyncio.sleep(0)
        stop.set()
        await task

        assert factory.urls == [TESTNET_WEBSOCKET_URL, TESTNET_WEBSOCKET_URL]
        assert sleeps == []
        assert manager.snapshot("ETH_USDT").state == "fresh"
        events = [message.get("event") for message in connection.sent]
        assert events.count("unsubscribe") == 4
        assert events.count("subscribe") == 12
        assert any(
            message.get("channel") == "futures.candlesticks"
            and message.get("payload") == ["15m", "ETH_USDT"]
            for message in connection.sent
        )

    asyncio.run(scenario())


def test_service_heartbeat_sends_gate_ping_and_times_out() -> None:
    async def scenario() -> None:
        manager = MarketDataManager(clock=lambda: NOW)
        connection = FakeConnection()
        service = GateFuturesWebSocketService(
            environment="live",
            market_data=manager,
            subscriptions=MarketSubscriptionRegistry(),
            rest_snapshot=lambda symbol: _snapshot(1, symbol=symbol),
            heartbeat_interval_seconds=0.001,
            heartbeat_timeout_seconds=0.001,
            reconnect_delays_seconds=(0,),
            epoch_clock=lambda: 456.0,
        )

        with pytest.raises(GateWebSocketHeartbeatTimeout):
            await service._receive_with_heartbeat(connection, asyncio.Event())

        assert connection.sent == [{"time": 456, "channel": "futures.ping"}]
        assert service._url == LIVE_WEBSOCKET_URL

    asyncio.run(scenario())
