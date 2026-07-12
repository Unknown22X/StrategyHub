"""Gate.io public-market mapping boundary with no credential handling."""

from datetime import UTC, datetime
from decimal import Decimal
import re
from typing import Protocol

import httpx

from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.analysis import Candle


PUBLIC_CONTRACT_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9_]+$")


class PublicMarketProvider(Protocol):
    """Public-only data required by the Paper dashboard."""

    def eligible_contracts(self) -> list[PublicContract]: ...

    def snapshot(self, symbol: str) -> PublicMarketSnapshot: ...


class GatePublicMarketAdapter:
    """Maps Gate public payloads into deliberately small domain objects."""

    @staticmethod
    def map_contracts(payloads: list[dict[str, object]]) -> list[PublicContract]:
        contracts: list[PublicContract] = []
        for payload in payloads:
            if bool(payload.get("in_delisting", False)):
                continue
            if str(payload.get("settle", "usdt")).lower() != "usdt":
                continue
            if str(payload.get("contract_type", "")).lower() not in {"", "perpetual"}:
                continue
            symbol = str(payload["name"])
            if not PUBLIC_CONTRACT_SYMBOL_PATTERN.fullmatch(symbol):
                continue
            quantity_step = Decimal(str(payload["quanto_multiplier"]))
            minimum_quantity = quantity_step * Decimal(str(payload["order_size_min"]))
            if quantity_step <= 0 or minimum_quantity <= 0:
                continue
            contracts.append(
                PublicContract(
                    symbol=symbol,
                    quantity_step=quantity_step,
                    minimum_quantity=minimum_quantity,
                )
            )
        return contracts

    @staticmethod
    def map_last_price(payload: dict[str, object]) -> PublicMarketSnapshot:
        return PublicMarketSnapshot(
            symbol=str(payload.get("contract", payload["name"])),
            last_price=Decimal(str(payload["last"])),
            observed_at=datetime.now(UTC),
        )

    @staticmethod
    def map_candles(payloads: list[dict[str, object]]) -> list[Candle]:
        """Map only normalized candle fields and preserve chronological order."""
        return sorted(
            [
                Candle(
                    opened_at=datetime.fromtimestamp(
                        int(str(payload["timestamp"])), UTC
                    ),
                    open=Decimal(str(payload["open"])),
                    high=Decimal(str(payload["high"])),
                    low=Decimal(str(payload["low"])),
                    close=Decimal(str(payload["close"])),
                )
                for payload in payloads
            ],
            key=lambda candle: candle.opened_at,
        )


class GatePublicMarketProvider:
    """Read-only Gate.io public futures market provider."""

    BASE_URL = "https://api.gateio.ws/api/v4/futures/usdt"

    def __init__(
        self, base_url: str = BASE_URL, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def eligible_contracts(self) -> list[PublicContract]:
        payload = self._get_json("contracts")
        if not isinstance(payload, list):
            raise LookupError("Gate public contracts response is not a list.")
        return GatePublicMarketAdapter.map_contracts(payload)

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        payload = self._get_json(f"contracts/{symbol}")
        if not isinstance(payload, dict):
            raise LookupError(f"Gate public snapshot is not available for {symbol}.")
        if not GatePublicMarketAdapter.map_contracts([payload]):
            raise LookupError(f"Gate public snapshot is not eligible for {symbol}.")
        return GatePublicMarketAdapter.map_last_price(payload)

    def _get_json(self, path: str) -> object:
        try:
            with httpx.Client(transport=self._transport, timeout=10.0) as client:
                response = client.get(f"{self._base_url}/{path}")
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise LookupError("Gate public market data is unavailable.") from error
        return response.json()


class EmptyPublicMarketProvider:
    """Safe default until a public Gate.io feed is configured by the runtime."""

    def eligible_contracts(self) -> list[PublicContract]:
        return []

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        raise LookupError(f"No public market snapshot is available for {symbol}.")
