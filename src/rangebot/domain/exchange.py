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
    liquidation_price: Decimal | None = None
    managed_order_ids: tuple[str, ...] = ()
    unmanaged_state: bool = False
    reconciliation_error: str | None = None
    one_way_confirmed: bool = False
    cross_margin_confirmed: bool = False
    leverage_confirmed: int | None = None
    market_ready: bool = False
    history_ready: bool = False
    risk_ready: bool = False
    active_contract_ready: bool = False
    daily_baseline_ready: bool = False
    protection_ready: bool = True
    tp_enabled: bool = True
    sl_enabled: bool = True
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


class ExchangeCredentialRequest(BaseModel):
    mode: TradingMode
    api_key: str = Field(min_length=1, max_length=512)
    api_secret: str = Field(min_length=1, max_length=512)


class ExchangeCredentialStatus(BaseModel):
    mode: TradingMode
    configured: bool


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
    limit_price: Decimal | None = None
    confirmation: str = ""
    protections_enabled: bool = True
    leverage: Literal[1, 5, 10] = 5
    take_profit_percentage: Decimal = Field(default=Decimal("30"), gt=0)
    stop_loss_percentage: Decimal = Field(default=Decimal("10"), gt=0)
    market_guard: "MarketEntryGuardRequest | None" = None
    client_request_id: str | None = None


class ExchangeEntryRequest(BaseModel):
    """Validated command passed only from the engine to an exchange adapter."""

    symbol: str
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    quantity: Decimal = Field(gt=0)
    client_request_id: str
    limit_price: Decimal | None = None
    protections_enabled: bool = True
    leverage: Literal[1, 5, 10] = 5
    take_profit_percentage: Decimal = Field(default=Decimal("30"), gt=0)
    stop_loss_percentage: Decimal = Field(default=Decimal("10"), gt=0)


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


class MarketGuardQuoteRequest(BaseModel):
    symbol: str = Field(default="BTC_USDT", min_length=1, max_length=64)
    direction: Literal["long", "short"]
    quantity: Decimal = Field(gt=0)


class ExchangeVerificationRequest(BaseModel):
    evidence: str = Field(min_length=1, max_length=2000)


class ExchangeVerificationRecord(BaseModel):
    mode: TradingMode
    recorded_at: datetime
    engine_build: str
    safety_fingerprint: str
    evidence: str
    stale: bool = False


class AutomaticStartRequest(BaseModel):
    active_contract: str = Field(min_length=1, max_length=64)


class AutomaticSignalRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    direction: Literal["long", "short"]
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = Field(default=None, gt=0)


class ExchangeRequestAudit(BaseModel):
    client_request_id: str
    mode: TradingMode
    kind: str
    status: str
    message_ar: str
