from decimal import Decimal

import httpx
import pytest

from rangebot.engine.contract_rules import (
    GateContractRulesMapper,
    GateContractRulesProvider,
)


def _payload(**changes) -> dict[str, object]:
    values: dict[str, object] = {
        "name": "BTC_USDT",
        "status": "trading",
        "in_delisting": False,
        "quanto_multiplier": "0.0001",
        "order_size_round": "0.1",
        "order_size_min": "1.5",
        "order_size_max": "100000",
        "market_order_size_max": "50000",
        "order_price_round": "0.1",
        "leverage_max": "100",
        "maintenance_rate": "0.005",
        "maker_fee_rate": "-0.00005",
        "taker_fee_rate": "0.0005",
    }
    values.update(changes)
    return values


def test_gate_contract_rules_mapper_preserves_decimal_size_and_fee_fields() -> None:
    rules = GateContractRulesMapper.map(_payload())

    assert rules.symbol == "BTC_USDT"
    assert rules.active is True
    assert rules.contract_multiplier == Decimal("0.0001")
    assert rules.quantity_step == Decimal("0.1")
    assert rules.minimum_quantity == Decimal("1.5")
    assert rules.maximum_quantity == Decimal("100000")
    assert rules.maximum_market_quantity == Decimal("50000")
    assert rules.price_step == Decimal("0.1")
    assert rules.maximum_leverage == 100
    assert rules.maintenance_rate == Decimal("0.005")
    assert rules.maker_fee_rate == Decimal("-0.00005")
    assert rules.taker_fee_rate == Decimal("0.0005")
    assert rules.supported_time_in_force == ("gtc", "ioc", "poc", "fok")


def test_gate_contract_rules_mapper_marks_delisting_contract_inactive() -> None:
    rules = GateContractRulesMapper.map(
        _payload(status="delisting", in_delisting=True)
    )

    assert rules.active is False
    assert rules.in_delisting is True


def test_gate_contract_rules_provider_uses_public_endpoint_without_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/contracts/BTC_USDT")
        assert "KEY" not in request.headers
        assert "SIGN" not in request.headers
        return httpx.Response(200, json=_payload())

    provider = GateContractRulesProvider(
        transport=httpx.MockTransport(handler)
    )

    assert provider("BTC_USDT").maximum_leverage == 100


def test_gate_contract_rules_provider_rejects_mismatched_or_unavailable_contract() -> None:
    mismatch = GateContractRulesProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=_payload(name="ETH_USDT"))
        )
    )
    unavailable = GateContractRulesProvider(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, json={"label": "UNAVAILABLE"})
        )
    )

    with pytest.raises(LookupError, match="does not match"):
        mismatch("BTC_USDT")
    with pytest.raises(LookupError, match="unavailable"):
        unavailable("BTC_USDT")
