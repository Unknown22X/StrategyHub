"""Public-market domain models used by Paper Trading."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PublicContract(BaseModel):
    """Eligible Gate.io perpetual contract rule subset."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^[A-Z0-9_]+$")
    quantity_step: Decimal = Field(gt=0)
    minimum_quantity: Decimal = Field(gt=0)


class PublicMarketSnapshot(BaseModel):
    """Last Price received from a public market-data source."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    last_price: Decimal = Field(gt=0)
    observed_at: datetime


class WatchlistItem(BaseModel):
    """A manually selected Paper contract and its display-only priority."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    priority: int
    is_active: bool
    monitoring_only: bool
    direction: Literal["long_only", "short_only", "both"] = "both"
    last_price: Decimal | None = None


class PaperWatchlist(BaseModel):
    """Paper watchlist and automatic-trading intent."""

    model_config = ConfigDict(frozen=True)

    items: list[WatchlistItem]
    automatic_trading_enabled: bool


class WatchlistStrategyReference(BaseModel):
    """Saved strategy currently associated with a watchlist contract."""

    model_config = ConfigDict(frozen=True)

    instance_id: str
    name: str
    environment: Literal["paper", "testnet", "live"]
    status: str
    current_signal: str | None = None
    last_decision_at: datetime | None = None


class WatchlistOverviewItem(BaseModel):
    """Engine-owned Gate market and strategy projection for one watched contract."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    priority: int
    is_active: bool
    monitoring_only: bool
    direction: Literal["long_only", "short_only", "both"]
    last_price: Decimal | None = None
    mark_price: Decimal | None = None
    index_price: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    spread_percentage: Decimal | None = None
    change_percentage_24h: Decimal | None = None
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    volume_24h: Decimal | None = None
    open_interest: Decimal | None = None
    funding_rate: Decimal | None = None
    next_funding_at: datetime | None = None
    observed_at: datetime | None = None
    source: Literal["gate_rest", "gate_websocket"] | None = None
    state: Literal["fresh", "stale", "reconnecting", "unavailable"]
    state_reason: str | None = None
    last_update_age_seconds: Decimal | None = None
    current_signal: str | None = None
    strategies: tuple[WatchlistStrategyReference, ...] = ()


class WatchlistOverview(BaseModel):
    """Watchlist values sourced from the normalized Gate market-data manager."""

    model_config = ConfigDict(frozen=True)

    items: tuple[WatchlistOverviewItem, ...]
    automatic_trading_enabled: bool
