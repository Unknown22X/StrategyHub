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
