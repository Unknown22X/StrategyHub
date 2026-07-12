"""Gate.io public-market mapping boundary with no credential handling."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from rangebot.domain.market import PublicContract, PublicMarketSnapshot
from rangebot.domain.analysis import Candle


class PublicMarketProvider(Protocol):
    """Public-only data required by the Paper dashboard."""

    def eligible_contracts(self) -> list[PublicContract]: ...

    def snapshot(self, symbol: str) -> PublicMarketSnapshot: ...


class GatePublicMarketAdapter:
    """Maps Gate public payloads into deliberately small domain objects."""

    @staticmethod
    def map_contracts(payloads: list[dict[str, object]]) -> list[PublicContract]:
        return [
            PublicContract(
                symbol=str(payload["name"]),
                quantity_step=Decimal(str(payload["quanto_multiplier"])),
                minimum_quantity=(
                    Decimal(str(payload["quanto_multiplier"]))
                    * Decimal(str(payload["order_size_min"]))
                ),
            )
            for payload in payloads
            if not bool(payload.get("in_delisting", False))
            and str(payload.get("settle", "usdt")).lower() == "usdt"
            and str(payload.get("contract_type", "perpetual")).lower() == "perpetual"
        ]

    @staticmethod
    def map_last_price(payload: dict[str, object]) -> PublicMarketSnapshot:
        return PublicMarketSnapshot(
            symbol=str(payload["contract"]),
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


class EmptyPublicMarketProvider:
    """Safe default until a public Gate.io feed is configured by the runtime."""

    def eligible_contracts(self) -> list[PublicContract]:
        return []

    def snapshot(self, symbol: str) -> PublicMarketSnapshot:
        raise LookupError(f"No public market snapshot is available for {symbol}.")
