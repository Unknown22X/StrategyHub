from datetime import UTC, datetime
from decimal import Decimal

from rangebot.engine.exchange import GateIoConfiguration, GateIoV4Adapter


def _configuration() -> GateIoConfiguration:
    return GateIoConfiguration(
        mode="testnet",
        key="-".join(("fixture", "key")),
        secret="-".join(("fixture", "credential")),
        base_url="https://example.invalid/api/v4",
    )


def test_gate_trade_history_maps_signed_fills_and_normalizes_fee_cost() -> None:
    calls: list[tuple[str, str, str]] = []

    def transport(method, url, query, headers, body):
        del headers, body
        calls.append((method, url, query))
        return [
            {
                "id": "1001",
                "create_time": 1_721_310_400,
                "contract": "BTC_USDT",
                "order_id": "order-open",
                "size": "3",
                "price": "65000",
                "text": "t-rangebot-open",
                "fee": "-0.75",
                "role": "taker",
                "close_size": "0",
                "trade_value": "195000",
            },
            {
                "trade_id": "1002",
                "create_time": 1_721_310_460,
                "contract": "BTC_USDT",
                "order_id": "order-close",
                "size": "-3",
                "price": "65100",
                "fee": "0.05",
                "role": "maker",
                "close_size": "3",
                "trade_value": "195300",
            },
            {"id": "invalid", "contract": "", "size": "0", "price": "0"},
        ]

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    fills = adapter.recent_trade_fills("testnet")

    assert calls == [
        (
            "GET",
            "https://example.invalid/api/v4/futures/usdt/my_trades",
            "limit=1000",
        )
    ]
    assert len(fills) == 2
    opened, closed = fills
    assert opened.external_trade_id == "1001"
    assert opened.side == "buy"
    assert opened.position_effect == "open"
    assert opened.quantity == Decimal("3")
    assert opened.fee == Decimal("0.75")
    assert opened.occurred_at == datetime.fromtimestamp(1_721_310_400, UTC)
    assert closed.side == "sell"
    assert closed.position_effect == "close"
    assert closed.close_quantity == Decimal("3")
    assert closed.fee == Decimal("-0.05")
    assert closed.role == "maker"
