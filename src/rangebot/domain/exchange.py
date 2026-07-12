"""Exchange-mode safety models shared by Testnet and locked Live workflows."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TradingMode = Literal["testnet", "live"]


class ExchangeSnapshot(BaseModel):
    """A sanitized, read-only Gate.io reconciliation result."""

    model_config = ConfigDict(frozen=True)
    mode: TradingMode
    reconciled_at: datetime
    available_futures_balance: Decimal = Decimal("0")
    position_quantity: Decimal = Decimal("0")
    managed_order_ids: tuple[str, ...] = ()
    unmanaged_state: bool = False
    reconciliation_error: str | None = None
    one_way_confirmed: bool = False
    cross_margin_confirmed: bool = False
    leverage_confirmed: int | None = None
    market_ready: bool = False
    history_ready: bool = False
    protection_ready: bool = True
    subscription_confirmed: bool = False
    rest_snapshot_confirmed: bool = False
    websocket_price_updates: int = 0
    market_observed_at: datetime | None = None


class ReconciliationRequest(BaseModel):
    """Test seam for a sanitized adapter snapshot; credentials are never accepted."""

    available_futures_balance: Decimal = Decimal("0")
    position_quantity: Decimal = Decimal("0")
    managed_order_ids: list[str] = Field(default_factory=list)
    unmanaged_state: bool = False
    reconciliation_error: str | None = None
    one_way_confirmed: bool = True
    cross_margin_confirmed: bool = True
    leverage_confirmed: int = Field(default=5, ge=1)
    market_ready: bool = True
    history_ready: bool = True
    protection_ready: bool = True


class ModeState(BaseModel):
    model_config = ConfigDict(frozen=True)
    mode: TradingMode
    live_locked: bool
    emergency_stop: bool
    can_enter: bool
    blocked_reasons_ar: tuple[str, ...]
    snapshot: ExchangeSnapshot | None = None


class LiveActivationRequest(BaseModel):
    confirmation: str


class ProtectionChangeRequest(BaseModel):
    protection: Literal["tp", "sl"]
    enabled: bool
    confirmation: str = ""


class LiveEntryRequest(BaseModel):
    """Small command contract for the mocked Gate adapter execution seam."""

    symbol: str
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    quantity: Decimal = Field(gt=0)
    confirmation: str = ""
    protections_enabled: bool = True
    market_guard: "MarketEntryGuardRequest | None" = None


class ExchangeEntryRequest(BaseModel):
    """Validated command passed only from the engine to an exchange adapter."""

    symbol: str
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    quantity: Decimal = Field(gt=0)
    client_request_id: str
    limit_price: Decimal | None = None
    protections_enabled: bool = True


class ExchangeOperationResult(BaseModel):
    """Sanitized result of a mocked or real managed exchange operation."""

    accepted: bool
    client_request_id: str
    message_ar: str
    order_id: str | None = None
    pending_unknown: bool = False


class ExchangeCloseRequest(BaseModel):
    confirmation: str


class OrderBookLevel(BaseModel):
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    observed_at: datetime


class MarketEntryGuardRequest(BaseModel):
    direction: Literal["long", "short"]
    quantity: Decimal = Field(gt=0)
    last_price: Decimal = Field(gt=0)
    last_price_observed_at: datetime
    asks: list[OrderBookLevel] = Field(default_factory=list)
    bids: list[OrderBookLevel] = Field(default_factory=list)


class MarketEntryGuardResult(BaseModel):
    allowed: bool
    expected_price: Decimal | None = None
    deviation_percentage: Decimal | None = None
    reason_ar: str | None = None
