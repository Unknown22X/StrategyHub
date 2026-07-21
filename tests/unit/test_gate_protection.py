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


def test_gate_entry_requires_and_submits_explicit_server_side_tp_sl() -> None:
    calls: list[tuple[str, str, str, str]] = []

    def transport(method, url, query, headers, body):
        del headers
        calls.append((method, url, query, body))
        return {"id": "protected-order"}

    adapter = GateIoV4Adapter(
        _configuration(),
        transport,
        allow_network=True,
        allow_order_submission=True,
    )
    missing = adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="2",
            client_request_id="missing-protection",
        ),
    )
    accepted = adapter.submit_entry(
        "testnet",
        ExchangeEntryRequest(
            symbol="BTC_USDT",
            direction="long",
            quantity="2",
            client_request_id="protected-entry",
            take_profit_price="66000",
            stop_loss_price="63000",
        ),
    )

    assert missing.accepted is False
    assert len(calls) == 1
    assert accepted.accepted is True
    payload = json.loads(calls[-1][3])
    assert payload["tpsl_tp_trigger_price"] == "66000"
    assert payload["tpsl_sl_trigger_price"] == "63000"
    assert payload["reduce_only"] is False


def test_gate_reconciliation_marks_position_unprotected_when_one_trigger_is_missing() -> None:
    protection_rows = [
        {
            "id": "tp-only",
            "status": "open",
            "order_type": "close-long-position",
            "initial": {"contract": "BTC_USDT"},
            "trigger": {"rule": 1, "price": "66000"},
        }
    ]

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
            return [
                {
                    "contract": "BTC_USDT",
                    "size": "2",
                    "entry_price": "65000",
                    "mark_price": "65100",
                    "value": "130",
                    "initial_margin": "26",
                    "unrealised_pnl": "0.2",
                    "liq_price": "52000",
                    "lever": "5",
                }
            ]
        if url.endswith("price_orders"):
            return protection_rows
        if url.endswith("/futures/usdt/orders"):
            return []
        raise AssertionError(url)

    adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )
    unprotected = adapter.reconcile("testnet")
    protection_rows.append(
        {
            "id": "sl-second",
            "status": "open",
            "order_type": "close-long-position",
            "initial": {"contract": "BTC_USDT"},
            "trigger": {"rule": 2, "price": "63000"},
        }
    )
    protected = adapter.reconcile("testnet")

    assert unprotected.protection_ready is False
    assert protected.protection_ready is True
    assert protected.position_quantity == Decimal("2")


def test_gate_cancel_rediscovers_managed_pending_entries_after_restart() -> None:
    deleted: list[str] = []

    def transport(method, url, query, headers, body):
        del headers, body
        if method == "GET" and url.endswith("/futures/usdt/orders"):
            assert query == "status=open"
            return [
                {
                    "id": "managed-entry",
                    "text": "t-rangebot-existing-request",
                    "reduce_only": False,
                },
                {
                    "id": "managed-close",
                    "text": "t-rangebot-close",
                    "reduce_only": True,
                },
                {
                    "id": "external-entry",
                    "text": "external-client",
                    "reduce_only": False,
                },
            ]
        if method == "DELETE" and "/futures/usdt/orders/" in url:
            deleted.append(url.rsplit("/", 1)[-1])
            return {"id": deleted[-1], "status": "cancelled"}
        raise AssertionError((method, url, query))

    restarted_adapter = GateIoV4Adapter(
        _configuration(), transport, allow_network=True, allow_order_submission=True
    )

    result = restarted_adapter.cancel_managed_entry("testnet")

    assert result.accepted is True
    assert deleted == ["managed-entry"]
