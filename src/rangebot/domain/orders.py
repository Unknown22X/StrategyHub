"""Central manual futures-order preview and submission contracts."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExecutionEnvironment = Literal["paper", "testnet", "live"]
OrderOrigin = Literal[
    "manual", "automatic_strategy", "monitoring_conversion", "legacy_automatic"
]
OrderDirection = Literal["long", "short"]
OrderType = Literal["market", "limit"]
OrderSizeMode = Literal["quantity", "margin", "balance_percentage"]
TimeInForce = Literal["gtc", "ioc", "poc", "fok"]
LiquidityBehavior = Literal["maker", "taker", "unknown"]


class FuturesContractRules(BaseModel):
    """Gate-derived USDT perpetual contract rules used by the Order Manager."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(pattern=r"^[A-Z0-9_]+$")
    active: bool = True
    in_delisting: bool = False
    contract_multiplier: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    minimum_quantity: Decimal = Field(gt=0)
    minimum_notional: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_quantity: Decimal | None = Field(default=None, gt=0)
    maximum_market_quantity: Decimal | None = Field(default=None, gt=0)
    price_step: Decimal = Field(gt=0)
    maximum_leverage: int = Field(ge=1, le=1000)
    maintenance_rate: Decimal = Field(default=Decimal("0"), ge=0, lt=1)
    maker_fee_rate: Decimal = Field(default=Decimal("0"), gt=-1)
    taker_fee_rate: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_spread_percentage: Decimal | None = Field(default=None, ge=0)
    supported_time_in_force: tuple[TimeInForce, ...] = (
        "gtc",
        "ioc",
        "poc",
        "fok",
    )


class OrderAccountContext(BaseModel):
    """Sanitized account and risk state consulted for every preview/submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: ExecutionEnvironment
    account_ready: bool = True
    adapter_mode_matches: bool = True
    credentials_configured: bool
    available_balance: Decimal = Field(ge=0)
    existing_position_quantity: Decimal = Decimal("0")
    one_way_confirmed: bool
    daily_risk_allowed: bool
    emergency_stop: bool
    reconciliation_ready: bool
    protection_ready: bool
    account_revision: str = Field(min_length=1, max_length=200)


class OrderSubmissionContext(BaseModel):
    """Origin and ownership identity carried through central order validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: OrderOrigin = "manual"
    instance_id: str | None = None
    run_id: str | None = None
    signal_zone: str | None = Field(default=None, max_length=200)
    signal_symbol: str | None = Field(default=None, pattern=r"^[A-Z0-9_]+$")
    take_profit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    trailing_stop_price: Decimal | None = Field(default=None, gt=0)
    strategy_type_id: str | None = Field(default=None, max_length=64)
    cycle_id: str | None = Field(default=None, max_length=100)
    order_role: Literal["entry", "take_profit", "stop_loss"] | None = None
    entry_level_id: str | None = Field(default=None, max_length=64)
    order_generation: int = Field(default=0, ge=0)


class ManualOrderPreviewRequest(BaseModel):
    """All user-controlled inputs for one manual futures-order preview."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: ExecutionEnvironment
    symbol: str = Field(pattern=r"^[A-Z0-9_]+$")
    direction: OrderDirection
    order_type: OrderType
    size_mode: OrderSizeMode
    quantity: Decimal | None = Field(default=None, gt=0)
    margin_amount: Decimal | None = Field(default=None, gt=0)
    balance_percentage: Decimal | None = None
    leverage: int = Field(ge=1, le=1000)
    limit_price: Decimal | None = Field(default=None, gt=0)
    time_in_force: TimeInForce = "gtc"
    expires_at: datetime | None = None
    reduce_only: bool = False

    @model_validator(mode="after")
    def validate_size_and_order_type(self) -> "ManualOrderPreviewRequest":
        if self.size_mode == "quantity":
            if (
                self.quantity is None
                or self.margin_amount is not None
                or self.balance_percentage is not None
            ):
                raise ValueError("Quantity sizing requires only `quantity`.")
        elif self.size_mode == "margin":
            if (
                self.margin_amount is None
                or self.quantity is not None
                or self.balance_percentage is not None
            ):
                raise ValueError("Margin sizing requires only `margin_amount`.")
        else:
            if self.balance_percentage not in {
                Decimal("10"),
                Decimal("25"),
                Decimal("50"),
                Decimal("75"),
                Decimal("100"),
            }:
                raise ValueError("Balance percentage must be 10, 25, 50, 75, or 100.")
            if self.quantity is not None or self.margin_amount is not None:
                raise ValueError("Percentage sizing cannot include quantity or margin.")

        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("Limit orders require `limit_price`.")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("Market orders cannot include `limit_price`.")
        if self.order_type == "market" and self.time_in_force not in {"ioc", "fok"}:
            raise ValueError("Market orders support IOC or FOK only.")
        if self.order_type == "market" and self.expires_at is not None:
            raise ValueError("Market orders cannot include `expires_at`.")
        if self.expires_at is not None and (
            self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None
        ):
            raise ValueError("Order expiration must include a timezone.")
        return self


class OrderValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message_ar: str
    field: str | None = None


class ManualOrderPreview(BaseModel):
    """Authoritative engine calculation shown before manual order submission."""

    model_config = ConfigDict(frozen=True)

    request: ManualOrderPreviewRequest
    generated_at: datetime
    last_price: Decimal
    mark_price: Decimal | None
    best_bid: Decimal | None
    best_ask: Decimal | None
    market_data_state: str
    market_observed_at: datetime
    available_balance: Decimal
    contract_multiplier: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    maximum_leverage: int
    estimated_quantity: Decimal
    estimated_notional: Decimal
    estimated_margin: Decimal
    estimated_opening_fee: Decimal
    estimated_fee_rate: Decimal
    estimated_take_profit_price: Decimal
    estimated_stop_loss_price: Decimal
    estimated_liquidation_price: Decimal | None
    reference_price: Decimal
    limit_distance_percentage: Decimal | None
    estimated_liquidity_behavior: LiquidityBehavior
    supported_time_in_force: tuple[TimeInForce, ...]
    validation_issues: tuple[OrderValidationIssue, ...]
    can_submit: bool
    uses_real_funds: bool
    live_warning_ar: str | None
    safety_fingerprint: str


class ManualOrderSubmissionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request: ManualOrderPreviewRequest
    preview_fingerprint: str = Field(min_length=64, max_length=64)


class ManualOrderSubmissionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    environment: ExecutionEnvironment
    origin: OrderOrigin = "manual"
    client_request_id: str
    order_id: str | None = None
    message_ar: str
    preview: ManualOrderPreview
