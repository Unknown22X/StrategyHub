from decimal import Decimal

from rangebot.engine.exchange import GateIoConfiguration, GateIoV4Adapter


def test_gate_reconciliation_maps_authoritative_account_position_and_order_rows() -> None:
    def transport(method, url, query, headers, body):
        del method, query, headers, body
        if url.endswith("accounts"):
            return {
                "total": "970.25",
                "cross_margin_balance": "1002.50",
                "cross_available": "850.00",
                "cross_unrealised_pnl": "32.25",
                "position_margin": "75",
                "cross_order_margin": "12.50",
                "position_mode": "single",
                "margin_mode": "cross",
                "leverage": "5",
                "history": {"pnl": "44", "fee": "-3.5", "fund": "-1.25"},
            }
        if url.endswith("positions"):
            return [
                {
                    "contract": "BTC_USDT",
                    "size": "-2.5",
                    "entry_price": "62000",
                    "mark_price": "61500",
                    "value": "153.75",
                    "initial_margin": "30.75",
                    "unrealised_pnl": "1.25",
                    "realised_pnl": "4.5",
                    "liq_price": "74000",
                    "lever": "5",
                    "pending_orders": 1,
                    "open_time": 1_752_710_400,
                    "update_time": 1_752_710_460,
                }
            ]
        if url.endswith("price_orders"):
            return [
                {
                    "id": "tp-1",
                    "status": "open",
                    "order_type": "close-short-position",
                    "initial": {"contract": "BTC_USDT"},
                    "trigger": {"rule": 2, "price": "60000"},
                },
                {
                    "id": "sl-1",
                    "status": "open",
                    "order_type": "close-short-position",
                    "initial": {"contract": "BTC_USDT"},
                    "trigger": {"rule": 1, "price": "70000"},
                },
            ]
        if url.endswith("/futures/usdt/orders"):
            return [
                {
                    "id": "order-1",
                    "contract": "BTC_USDT",
                    "size": "-2.5",
                    "left": "1.5",
                    "price": "61000",
                    "status": "open",
                    "is_reduce_only": False,
                    "create_time": 1_752_710_430,
                    "text": "t-rangebot-managed",
                }
            ]
        raise AssertionError(url)

    key_value = "".join(("runtime", "-", "key"))
    secret_value = "".join(("runtime", "-", "credential"))
    adapter = GateIoV4Adapter(
        GateIoConfiguration(
            mode="live",
            key=key_value,
            secret=secret_value,
            base_url="https://api.gateio.ws/api/v4",
        ),
        transport,
        allow_network=True,
    )

    snapshot = adapter.reconcile("live")

    assert snapshot.total_futures_balance == Decimal("970.25")
    assert snapshot.total_futures_equity == Decimal("1002.50")
    assert snapshot.available_futures_balance == Decimal("850.00")
    assert snapshot.unrealized_pnl == Decimal("32.25")
    assert snapshot.position_margin == Decimal("30.75")
    assert snapshot.order_margin == Decimal("12.50")
    assert snapshot.used_margin == Decimal("43.25")
    assert snapshot.margin_usage_percentage == Decimal("43.25") / Decimal("1002.50") * Decimal("100")
    assert snapshot.realized_pnl_total == Decimal("44")
    assert snapshot.fees_total == Decimal("-3.5")
    assert snapshot.funding_total == Decimal("-1.25")
    assert snapshot.net_pnl_total == Decimal("39.25")
    assert snapshot.open_exposure == Decimal("153.75")
    assert snapshot.position_quantity == Decimal("2.5")
    assert len(snapshot.positions) == 1
    position = snapshot.positions[0]
    assert position.contract == "BTC_USDT"
    assert position.side == "short"
    assert position.entry_price == Decimal("62000")
    assert position.mark_price == Decimal("61500")
    assert position.margin == Decimal("30.75")
    assert position.unrealized_pnl == Decimal("1.25")
    assert position.leverage == Decimal("5")
    assert position.opened_at is not None
    assert len(snapshot.open_orders) == 1
    order = snapshot.open_orders[0]
    assert order.side == "short"
    assert order.order_type == "limit"
    assert order.quantity == Decimal("2.5")
    assert order.filled_quantity == Decimal("1.0")
    assert order.managed_by_rangebot is True
    assert snapshot.protection_ready is True
