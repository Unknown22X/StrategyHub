"""Normalized market-data snapshots and explicit freshness ownership."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rangebot.domain.strategy_runtime import MarketDataState, NormalizedCandle


MarketDataSource = Literal["gate_rest", "gate_websocket"]


class MarketPriceUpdate(BaseModel):
    """One normalized Gate.io public price update entering the engine."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^[A-Z0-9_]+$")
    last_price: Decimal = Field(gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    index_price: Decimal | None = Field(default=None, gt=0)
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    change_percentage_24h: Decimal | None = None
    high_24h: Decimal | None = Field(default=None, gt=0)
    low_24h: Decimal | None = Field(default=None, gt=0)
    volume_24h: Decimal | None = Field(default=None, ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    funding_rate: Decimal | None = None
    next_funding_at: datetime | None = None
    observed_at: datetime
    source: MarketDataSource
    sequence_start: int | None = Field(default=None, ge=0)
    sequence: int | None = Field(default=None, ge=0)

    @field_validator("observed_at", "next_funding_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Market timestamps must include a timezone.")
        return value

    @model_validator(mode="after")
    def validate_sequence_range(self) -> "MarketPriceUpdate":
        if self.sequence_start is not None and self.sequence is None:
            raise ValueError("Sequence range start requires a final sequence.")
        if (
            self.sequence_start is not None
            and self.sequence is not None
            and self.sequence_start > self.sequence
        ):
            raise ValueError("Sequence range start cannot exceed final sequence.")
        return self


class MarketDataSnapshot(BaseModel):
    """Latest engine-owned market snapshot with explicit source and state."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    last_price: Decimal = Field(gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    index_price: Decimal | None = Field(default=None, gt=0)
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    change_percentage_24h: Decimal | None = None
    high_24h: Decimal | None = Field(default=None, gt=0)
    low_24h: Decimal | None = Field(default=None, gt=0)
    volume_24h: Decimal | None = Field(default=None, ge=0)
    open_interest: Decimal | None = Field(default=None, ge=0)
    funding_rate: Decimal | None = None
    next_funding_at: datetime | None = None
    observed_at: datetime
    received_at: datetime
    source: MarketDataSource
    sequence: int | None = None
    state: MarketDataState
    state_reason: str | None = None
    sequence_gap: bool = False
    last_update_age_seconds: Decimal = Field(ge=0)


class MarketDataStatus(BaseModel):
    """Connection/freshness status even when no price has been received yet."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    state: MarketDataState
    state_reason: str | None = None
    source: MarketDataSource | None = None
    sequence_gap: bool = False
    last_update_at: datetime | None = None
    last_update_age_seconds: Decimal | None = Field(default=None, ge=0)


class MarketCandleSeries(BaseModel):
    """Chronological candle series retained by the Market Data Manager."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe_minutes: int = Field(ge=1, le=10080)
    candles: tuple[NormalizedCandle, ...]
    source: MarketDataSource
    updated_at: datetime
