"""Gate.io USDT perpetual contract-rule retrieval for central order validation."""

from decimal import Decimal
from typing import Literal

import httpx

from rangebot.domain.orders import FuturesContractRules
from rangebot.engine.gate_websocket import LIVE_REST_URL, TESTNET_REST_URL


GateContractEnvironment = Literal["live", "testnet"]


class GateContractRulesMapper:
    """Map the official Gate Contract payload without changing units."""

    @staticmethod
    def map(payload: dict[str, object]) -> FuturesContractRules:
        symbol = str(payload["name"])
        status = str(payload.get("status", "trading")).lower()
        in_delisting = bool(payload.get("in_delisting", False)) or status in {
            "delisting",
            "delisted",
        }
        maximum_market = Decimal(str(payload.get("market_order_size_max", "0")))
        return FuturesContractRules(
            symbol=symbol,
            active=status == "trading" and not in_delisting,
            in_delisting=in_delisting,
            contract_multiplier=Decimal(str(payload["quanto_multiplier"])),
            quantity_step=Decimal(str(payload.get("order_size_round", "1"))),
            minimum_quantity=Decimal(str(payload["order_size_min"])),
            minimum_notional=Decimal(str(payload.get("order_value_min", "0"))),
            maximum_quantity=Decimal(str(payload["order_size_max"])),
            maximum_market_quantity=(maximum_market if maximum_market > 0 else None),
            price_step=Decimal(str(payload["order_price_round"])),
            maximum_leverage=int(Decimal(str(payload["leverage_max"]))),
            maintenance_rate=Decimal(str(payload["maintenance_rate"])),
            maker_fee_rate=Decimal(str(payload["maker_fee_rate"])),
            taker_fee_rate=Decimal(str(payload["taker_fee_rate"])),
            supported_time_in_force=("gtc", "ioc", "poc", "fok"),
        )


class GateContractRulesProvider:
    """Read one contract from Gate's public USDT futures endpoint."""

    BASE_URL = LIVE_REST_URL

    def __init__(
        self,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
        *,
        environment: GateContractEnvironment = "live",
    ) -> None:
        self._base_url = (
            base_url or (LIVE_REST_URL if environment == "live" else TESTNET_REST_URL)
        ).rstrip("/")
        self._transport = transport

    def __call__(self, symbol: str) -> FuturesContractRules:
        try:
            with httpx.Client(transport=self._transport, timeout=10.0) as client:
                response = client.get(f"{self._base_url}/contracts/{symbol}")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LookupError(
                f"Gate contract rules are unavailable for {symbol}."
            ) from error
        payload = response.json()
        if not isinstance(payload, dict):
            raise LookupError(f"Gate contract response is invalid for {symbol}.")
        rules = GateContractRulesMapper.map(payload)
        if rules.symbol != symbol:
            raise LookupError(f"Gate contract response does not match {symbol}.")
        return rules
