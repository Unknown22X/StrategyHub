import json
from decimal import Decimal

from rangebot.domain.exchange import ExchangeEntryRequest
from rangebot.engine.exchange import GateIoConfiguration, GateIoV4Adapter


def _configuration() -> GateIoConfiguration:
    return GateIoConfiguration(
        mode="testnet",
        key="-".join(("fixture", "key")),
        secret="-".join(("fixture", "credential")),
        base_url="https://example.invalid/api/v4",
    )


def _request(direction: str = "long") -> ExchangeEntryRequest:
    return ExchangeEntryRequest(
        symbol="BTC_USDT",
        direction=direction,
        order_type="market",
        quantity=Decimal("2"),
        client_request_id="12345678-1234-5678-1234-567812345678",
        take_profit_price=Decimal("66000") if direction == "long" else Decimal("62000"),
        stop_loss_price=Decimal("63000") if direction == "long" else Decimal("67000"),
        trailing_stop_price=Decimal("64000") if direction == "long" else Decimal("66000"),
        trailing_stop_distance=Decimal("1000"),
        origin="automatic_strategy",
    )


def test_gate_long_market_entry_creates_reduce_only_position_related_trail() -> None:
    calls: list[tuple[str, str, str]] = []

    def transport(method, url, query, headers, body):
        del query, headers
        calls.append((method, url, body))
        if url.endswith("/futures/usdt/orders"):
            return {"id": "entry-order"}
        if url.endswith("/autoorder/v1/trail/create"):
            return {"id": "trail-order"}
        raise AssertionError(url)

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    result = adapter.submit_entry("testnet", _request("long"))

    assert result.accepted is True
    assert result.pending_unknown is False
    assert len(calls) == 2
    trail_payload = json.loads(calls[1][2])
    assert trail_payload["amount"] == "-2"
    assert trail_payload["activation_price"] == "0"
    assert trail_payload["price_type"] == 3
    assert trail_payload["price_offset"] == "1000"
    assert trail_payload["reduce_only"] is True
    assert trail_payload["position_related"] is True
    assert trail_payload["pos_margin_mode"] == "cross"
    assert trail_payload["position_mode"] == "single"
    assert trail_payload["text"].startswith("t-rbtrail-")


def test_gate_short_trail_uses_positive_close_amount() -> None:
    payloads: list[dict[str, object]] = []

    def transport(method, url, query, headers, body):
        del method, query, headers
        payloads.append(json.loads(body))
        return {"id": "trail-order" if url.endswith("trail/create") else "entry-order"}

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    result = adapter.submit_entry("testnet", _request("short"))

    assert result.accepted is True
    assert payloads[-1]["amount"] == "2"


def test_gate_reconciliation_reports_active_rangebot_trail_order() -> None:
    def transport(method, url, query, headers, body):
        del method, query, headers, body
        if url.endswith("accounts"):
            return {
                "total": "1000",
                "cross_available": "900",
                "position_mode": "single",
                "margin_mode": "cross",
                "leverage": "5",
            }
        if url.endswith("positions"):
            return [{"contract": "BTC_USDT", "size": "2"}]
        if url.endswith("price_orders"):
            return [
                {
                    "id": "tp",
                    "status": "open",
                    "order_type": "close-long-position",
                    "initial": {"contract": "BTC_USDT"},
                    "trigger": {"rule": 1},
                },
                {
                    "id": "sl",
                    "status": "open",
                    "order_type": "close-long-position",
                    "initial": {"contract": "BTC_USDT"},
                    "trigger": {"rule": 2},
                },
            ]
        if url.endswith("/autoorder/v1/trail/list"):
            return {
                "orders": [
                    {
                        "id": "trail-active",
                        "contract": "BTC_USDT",
                        "status": "open",
                        "text": "t-rbtrail-1234567890abcdef",
                        "reduce_only": True,
                        "position_related": True,
                    }
                ]
            }
        if url.endswith("/futures/usdt/orders"):
            return []
        raise AssertionError(url)

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    snapshot = adapter.reconcile("testnet")

    assert snapshot.protection_ready is True
    assert snapshot.trailing_protection_ready is True
    assert snapshot.trailing_order_ids == ("trail-active",)


def test_gate_orphaned_trail_is_not_reported_as_healthy() -> None:
    def transport(method, url, query, headers, body):
        del method, query, headers, body
        if url.endswith("accounts"):
            return {
                "total": "1000",
                "cross_available": "1000",
                "position_mode": "single",
                "margin_mode": "cross",
                "leverage": "5",
            }
        if url.endswith("positions"):
            return []
        if url.endswith("price_orders"):
            return []
        if url.endswith("/autoorder/v1/trail/list"):
            return {
                "orders": [
                    {
                        "id": "123456",
                        "contract": "BTC_USDT",
                        "status": "open",
                        "text": "t-rbtrail-1234567890abcdef",
                        "reduce_only": True,
                        "position_related": True,
                    }
                ]
            }
        if url.endswith("/futures/usdt/orders"):
            return []
        raise AssertionError(url)

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    snapshot = adapter.reconcile("testnet")

    assert snapshot.position_quantity == Decimal("0")
    assert snapshot.trailing_order_ids == ("123456",)
    assert snapshot.trailing_protection_ready is False


def test_gate_entry_keeps_fixed_protection_when_trail_creation_fails() -> None:
    def transport(method, url, query, headers, body):
        del method, query, headers, body
        if url.endswith("/futures/usdt/orders"):
            return {"id": "entry-order"}
        if url.endswith("/autoorder/v1/trail/create"):
            raise RuntimeError("trail temporarily unavailable")
        raise AssertionError(url)

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    result = adapter.submit_entry("testnet", _request("long"))

    assert result.accepted is True
    assert result.pending_unknown is True
    assert "TP/SL" in result.message_ar
    assert "وقف التتبع" in result.message_ar


def test_gate_trailing_cleanup_uses_official_stop_payload() -> None:
    calls: list[tuple[str, str, str]] = []

    def transport(method, url, query, headers, body):
        del query, headers
        calls.append((method, url, body))
        return {"status": "success"}

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    result = adapter.cancel_trailing_protection("testnet", "123456")

    assert result.accepted is True
    assert calls == [
        (
            "POST",
            "https://example.invalid/api/v4/futures/usdt/autoorder/v1/trail/stop",
            '{"id":123456}',
        )
    ]


def test_gate_trailing_cleanup_failure_is_explicit() -> None:
    def transport(method, url, query, headers, body):
        del method, url, query, headers, body
        raise RuntimeError("cleanup unavailable")

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    result = adapter.cancel_trailing_protection("testnet", "123456")

    assert result.accepted is False
    assert result.client_request_id == "cancel-trail-123456"
    assert "تعذر إلغاء وقف التتبع" in result.message_ar
