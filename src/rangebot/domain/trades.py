"""Immutable executed-trade history shared by Gate and Paper environments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TradeEnvironment = Literal["paper", "testnet", "live"]
TradeSide = Literal["buy", "sell"]
TradeEffect = Literal["open", "close", "mixed", "unknown"]
TradeOrigin = Literal[
    "manual",
    "automatic_strategy",
    "monitoring_conversion",
    "legacy_automatic",
    "external",
]


class TradeFillCreate(BaseModel):
    """Normalized immutable fill before it is assigned a local row id."""

    model_config = ConfigDict(frozen=True)

    environment: TradeEnvironment
    external_trade_id: str = Field(min_length=1, max_length=200)
    order_id: str | None = Field(default=None, max_length=200)
    contract: str = Field(min_length=1, max_length=64)
    side: TradeSide
    position_effect: TradeEffect = "unknown"
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fee: Decimal = Decimal("0")
    role: Literal["maker", "taker", "unknown"] = "unknown"
    close_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    trade_value: Decimal = Decimal("0")
    realized_pnl: Decimal | None = None
    occurred_at: datetime
    source: Literal["paper_engine", "gate_rest"]
    origin: TradeOrigin | None = None
    instance_id: str | None = None
    run_id: str | None = None
    strategy_name_snapshot: str | None = Field(default=None, max_length=200)


class TradeFill(BaseModel):
    """Persisted trade-history row returned to the localhost control panel."""

    model_config = ConfigDict(frozen=True)

    fill_id: int
    environment: TradeEnvironment
    external_trade_id: str
    order_id: str | None = None
    contract: str
    side: TradeSide
    position_effect: TradeEffect
    quantity: Decimal
    price: Decimal
    fee: Decimal
    role: Literal["maker", "taker", "unknown"]
    close_quantity: Decimal
    trade_value: Decimal
    realized_pnl: Decimal | None
    occurred_at: datetime
    source: Literal["paper_engine", "gate_rest"]
    origin: TradeOrigin | None = None
    instance_id: str | None = None
    run_id: str | None = None
    strategy_name_snapshot: str | None = None
    ingested_at: datetime


class TradeHistorySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    fills: int
    opened_quantity: Decimal
    closed_quantity: Decimal
    realized_pnl: Decimal | None
    realized_pnl_known_fills: int
    winning_fills: int
    losing_fills: int
    win_rate_percentage: Decimal | None
    gross_profit: Decimal | None
    gross_loss: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    fees: Decimal
    gross_trade_value: Decimal
