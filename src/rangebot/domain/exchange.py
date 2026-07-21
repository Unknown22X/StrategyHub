"""Exchange-mode safety models shared by Testnet and Live workflows."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TradingMode = Literal["testnet", "live"]


class ExchangePositionSnapshot(BaseModel):
    """Sanitized Gate.io position data owned by reconciliation."""

    model_config = ConfigDict(frozen=True)
    contract: str
    side: Literal["long", "short"]
    quantity: Decimal
    entry_price: Decimal | None = None
    mark_price: Decimal | None = None
    value: Decimal = Decimal("0")
    margin: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    liquidation_price: Decimal | None = None
    leverage: Decimal | None = None
    pending_orders: int = 0
    opened_at: datetime | None = None
    updated_at: datetime | None = None
    managed_by_rangebot: bool = False
    origin: (
        Literal[
            "manual", "automatic_strategy", "monitoring_conversion", "legacy_automatic"
        ]
        | None
    ) = None
    instance_id: str | None = None
    run_id: str | None = None
    strategy_name: str | None = None
    ownership_created_at: datetime | None = None
    trailing_stop_price: Decimal | None = None
    trailing_stop_distance: Decimal | None = None
    trailing_state: Literal["desired", "active", "error"] | None = None
    trailing_order_id: str | None = None
    trailing_last_error: str | None = None


class ExchangeOpenOrderSnapshot(BaseModel):
    """Sanitized Gate.io open-order row returned to the control panel."""

    model_config = ConfigDict(frozen=True)
    order_id: str
    contract: str
    side: Literal["long", "short"]
    order_type: Literal["market", "limit"]
    price: Decimal | None = None
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    status: str
    reduce_only: bool = False
    created_at: datetime | None = None
    managed_by_rangebot: bool = False
    origin: (
        Literal[
            "manual", "automatic_strategy", "monitoring_conversion", "legacy_automatic"
        ]
        | None
    ) = None
    instance_id: str | None = None
    run_id: str | None = None
    strategy_name: str | None = None


class ExchangeSnapshot(BaseModel):
    """A sanitized, read-only Gate.io reconciliation result."""

    model_config = ConfigDict(frozen=True)
    mode: TradingMode
    reconciled_at: datetime
    available_futures_balance: Decimal = Decimal("0")
    total_futures_balance: Decimal = Decimal("0")
    total_futures_equity: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    position_margin: Decimal = Decimal("0")
    order_margin: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    margin_usage_percentage: Decimal = Decimal("0")
    realized_pnl_total: Decimal = Decimal("0")
    fees_total: Decimal = Decimal("0")
    funding_total: Decimal = Decimal("0")
    net_pnl_total: Decimal = Decimal("0")
    open_exposure: Decimal = Decimal("0")
    position_quantity: Decimal = Decimal("0")
    liquidation_price: Decimal | None = None
    positions: tuple[ExchangePositionSnapshot, ...] = ()
    open_orders: tuple[ExchangeOpenOrderSnapshot, ...] = ()
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
    trailing_protection_ready: bool | None = None
    trailing_reconciliation_ready: bool = True
    trailing_order_ids: tuple[str, ...] = ()
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
    emergency_stop: bool
    can_enter: bool
    blocked_reasons_ar: tuple[str, ...]
    snapshot: ExchangeSnapshot | None = None


class ExchangeCredentialRequest(BaseModel):
    mode: TradingMode
    api_key: str = Field(min_length=1, max_length=512)
    api_secret: str = Field(min_length=1, max_length=512)


class ExchangeCredentialStatus(BaseModel):
    mode: TradingMode
    configured: bool


class ExchangeCredentialTestResult(BaseModel):
    mode: TradingMode
    valid: bool
    message_ar: str


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
    leverage: int = Field(default=5, ge=1, le=1000)
    time_in_force: Literal["gtc", "ioc", "poc", "fok"] = "gtc"
    expires_at: datetime | None = None
    signal_zone: str | None = None
    signal_symbol: str | None = None
    take_profit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    trailing_stop_price: Decimal | None = Field(default=None, gt=0)
    trailing_stop_distance: Decimal | None = Field(default=None, gt=0)
    origin: Literal[
        "automatic_strategy",
        "monitoring_conversion",
        "manual",
        "legacy_automatic",
        "legacy",
    ] = "legacy"
    take_profit_percentage: Decimal = Field(default=Decimal("30"), gt=0)
    stop_loss_percentage: Decimal = Field(default=Decimal("10"), gt=0)
    reduce_only: bool = False
    strategy_type_id: str | None = None
    cycle_id: str | None = None
    order_role: Literal["entry", "take_profit", "stop_loss"] | None = None
    entry_level_id: str | None = None
    order_generation: int = Field(default=0, ge=0)


class ExchangeTrailingStopRequest(BaseModel):
    """Engine-owned request to install or recover one reduce-only trailing stop."""

    symbol: str
    direction: Literal["long", "short"]
    quantity: Decimal = Field(gt=0)
    trailing_stop_distance: Decimal = Field(gt=0)
    client_request_id: str


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
    leverage: int = Field(default=5, ge=1, le=1000)
    time_in_force: Literal["gtc", "ioc", "poc", "fok"] = "ioc"
    instance_id: str | None = None
    run_id: str | None = None


class ExchangeRequestAudit(BaseModel):
    client_request_id: str
    mode: TradingMode
    kind: str
    status: str
    message_ar: str
    created_at: datetime
    updated_at: datetime
