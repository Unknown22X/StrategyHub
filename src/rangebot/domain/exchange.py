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
