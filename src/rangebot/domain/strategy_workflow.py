"""Product workflow contracts for reusable strategies, coin setups, and deployments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rangebot.domain.backtesting import BacktestAssessmentLabel, BacktestSettings
from rangebot.domain.strategy import StrategyDirection, StrategyEnvironment
from rangebot.domain.strategy_runtime import MarketDataState


StrategyTemplateStatus = Literal["draft", "active", "archived"]
StrategySetupStatus = Literal[
    "draft",
    "ready_for_backtest",
    "backtest_required",
    "backtest_failed",
    "backtest_passed",
    "approved_paper",
    "approved_testnet",
    "approved_live",
    "archived",
]
OpportunityStatus = Literal[
    "new",
    "reviewed",
    "approved",
    "rejected",
    "ignored",
    "expired",
    "converted",
]
ApprovalMode = Literal["paper", "testnet", "live"]
ApprovalStatus = Literal["approved", "stale", "revoked"]
DeploymentStatus = Literal[
    "not_started",
    "starting",
    "running",
    "monitoring",
    "paused",
    "stopped",
    "error",
]
ExecutionOrderType = Literal["market", "limit"]
TimeInForce = Literal["gtc", "ioc", "poc", "fok"]
PriceState = Literal["fresh", "delayed", "unavailable"]


class EntryExecutionSettings(BaseModel):
    """How an entry intent should be submitted after all strategy conditions pass."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_type: ExecutionOrderType = "market"
    limit_price: Decimal | None = Field(default=None, gt=0)
    limit_price_formula: str | None = Field(default=None, max_length=500)
    time_in_force: TimeInForce = "gtc"
    expires_after_minutes: int | None = Field(default=None, ge=1, le=10080)
    cancellation_policy: Literal[
        "keep_open", "cancel_on_expiry", "cancel_on_signal_reset"
    ] = "cancel_on_signal_reset"
    partial_fill_behavior: Literal[
        "accept_partial", "cancel_remainder", "require_full_fill"
    ] = "accept_partial"

    @model_validator(mode="after")
    def validate_limit_settings(self) -> "EntryExecutionSettings":
        has_limit_value = self.limit_price is not None or bool(self.limit_price_formula)
        if self.order_type == "limit" and not has_limit_value:
            raise ValueError(
                "Limit entry requires a price or a documented price formula."
            )
        if self.order_type == "market" and has_limit_value:
            raise ValueError("Market entry cannot include a limit price or formula.")
        return self


class ExitExecutionSettings(BaseModel):
    """How one exit trigger should execute; trigger logic remains strategy-owned."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_type: ExecutionOrderType = "market"
    limit_offset_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    time_in_force: TimeInForce = "ioc"
    maximum_wait_seconds: int = Field(default=30, ge=1, le=86400)
    fallback_to_market: bool = True

    @model_validator(mode="after")
    def validate_limit_settings(self) -> "ExitExecutionSettings":
        if self.order_type == "limit" and self.limit_offset_percentage is None:
            raise ValueError("Limit exit requires a limit offset percentage.")
        if self.order_type == "market" and self.limit_offset_percentage is not None:
            raise ValueError("Market exit cannot include a limit offset percentage.")
        return self


class StrategyExecutionPlan(BaseModel):
    """Explicit entry and exit execution defaults inherited by coin setups."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry: EntryExecutionSettings = Field(default_factory=EntryExecutionSettings)
    take_profit: ExitExecutionSettings = Field(default_factory=ExitExecutionSettings)
    stop_loss: ExitExecutionSettings = Field(default_factory=ExitExecutionSettings)
    strategy_exit: ExitExecutionSettings = Field(default_factory=ExitExecutionSettings)
    manual_exit: ExitExecutionSettings = Field(default_factory=ExitExecutionSettings)


class DcaSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    maximum_entries: int = Field(default=1, ge=1, le=100)
    spacing_percentage: Decimal = Field(default=Decimal("1"), gt=0, le=1000)
    allocation_method: Literal["equal", "weighted", "custom"] = "equal"
    custom_allocations: tuple[Decimal, ...] = ()

    @model_validator(mode="after")
    def validate_allocations(self) -> "DcaSettings":
        if not self.enabled and self.maximum_entries != 1:
            raise ValueError("Disabled DCA must keep exactly one entry.")
        if self.allocation_method == "custom":
            if len(self.custom_allocations) != self.maximum_entries:
                raise ValueError("Custom DCA allocations must match maximum entries.")
            if any(value <= 0 for value in self.custom_allocations):
                raise ValueError("Custom DCA allocations must be positive.")
        elif self.custom_allocations:
            raise ValueError("Custom allocations require the custom allocation method.")
        return self


class StrategyRiskDefaults(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_margin: Decimal = Field(default=Decimal("20"), gt=0)
    requested_leverage: int = Field(default=3, ge=1, le=100)
    maximum_positions: int = Field(default=1, ge=1, le=100)
    maximum_exposure_percentage: Decimal = Field(default=Decimal("25"), gt=0, le=100)


class StrategySetupDefaults(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_plan: StrategyExecutionPlan = Field(default_factory=StrategyExecutionPlan)
    dca: DcaSettings = Field(default_factory=DcaSettings)
    risk: StrategyRiskDefaults = Field(default_factory=StrategyRiskDefaults)


class StrategyTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    timeframe_minutes: int = Field(ge=1, le=10080)
    direction: StrategyDirection = "both"
    configuration: dict[str, Any] = Field(default_factory=dict)
    setup_defaults: StrategySetupDefaults = Field(default_factory=StrategySetupDefaults)
    status: Literal["draft", "active"] = "draft"


class StrategyTemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    timeframe_minutes: int | None = Field(default=None, ge=1, le=10080)
    direction: StrategyDirection | None = None
    configuration: dict[str, Any] | None = None
    setup_defaults: StrategySetupDefaults | None = None
    status: Literal["draft", "active"] | None = None


class StrategyTemplate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    type_id: str
    name: str
    description: str
    status: StrategyTemplateStatus
    current_revision: int = Field(ge=1)
    timeframe_minutes: int
    direction: StrategyDirection
    configuration: dict[str, Any]
    setup_defaults: StrategySetupDefaults
    setup_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class StrategyTemplateVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version_id: int
    template_id: str
    revision: int = Field(ge=1)
    timeframe_minutes: int
    direction: StrategyDirection
    configuration: dict[str, Any]
    setup_defaults: StrategySetupDefaults
    created_at: datetime


class StrategyPresetCreate(StrategyTemplateCreate):
    """Create an editable user Preset; legacy Template records use this model."""


class StrategyPresetUpdate(StrategyTemplateUpdate):
    """Update an editable user Preset."""


class StrategyPreset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    preset_id: str
    type_id: str
    name: str
    description: str
    status: StrategyTemplateStatus
    current_revision: int = Field(ge=1)
    timeframe_minutes: int
    direction: StrategyDirection
    configuration: dict[str, Any]
    setup_defaults: StrategySetupDefaults
    setup_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None
    legacy_template_id: str


class StrategyPresetVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version_id: int
    preset_id: str
    revision: int = Field(ge=1)
    timeframe_minutes: int
    direction: StrategyDirection
    configuration: dict[str, Any]
    setup_defaults: StrategySetupDefaults
    created_at: datetime


class StrategyCoinSetupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    symbol: str = Field(pattern=r"^[A-Z0-9_]+$")
    exchange: str = Field(default="gateio", min_length=1, max_length=50)
    market_type: Literal["usdt_perpetual"] = "usdt_perpetual"
    quote_currency: str = Field(default="USDT", pattern=r"^[A-Z0-9]+$")
    timeframe_minutes: int | None = Field(default=None, ge=1, le=10080)
    direction: StrategyDirection | None = None
    configuration_overrides: dict[str, Any] = Field(default_factory=dict)
    setup_defaults_override: StrategySetupDefaults | None = None
    source_opportunity_id: str | None = None


class StrategyCoinSetupUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = Field(default=None, pattern=r"^[A-Z0-9_]+$")
    timeframe_minutes: int | None = Field(default=None, ge=1, le=10080)
    direction: StrategyDirection | None = None
    configuration_overrides: dict[str, Any] | None = None
    setup_defaults_override: StrategySetupDefaults | None = None


class StrategyCoinSetup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_id: str
    template_id: str
    template_revision: int = Field(ge=1)
    runtime_instance_id: str | None = None
    exchange: str
    market_type: str
    symbol: str
    quote_currency: str
    current_price: Decimal | None = None
    price_observed_at: datetime | None = None
    price_state: PriceState = "unavailable"
    timeframe_minutes: int
    direction: StrategyDirection
    inherited_configuration: dict[str, Any]
    configuration_overrides: dict[str, Any]
    effective_configuration: dict[str, Any]
    inherited_setup_defaults: StrategySetupDefaults
    setup_defaults_override: StrategySetupDefaults | None = None
    effective_setup_defaults: StrategySetupDefaults
    status: StrategySetupStatus
    latest_backtest_id: str | None = None
    latest_backtest_revision: int | None = None
    latest_backtest_assessment: BacktestAssessmentLabel | None = None
    active_approval_mode: ApprovalMode | None = None
    source_opportunity_id: str | None = None
    revision: int = Field(ge=1)
    warnings: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class StrategyCoinSetupVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version_id: int
    setup_id: str
    revision: int = Field(ge=1)
    snapshot: dict[str, Any]
    created_at: datetime


class SetupBacktestRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    start: datetime
    end: datetime
    settings: BacktestSettings = Field(default_factory=BacktestSettings)

    @model_validator(mode="after")
    def validate_window(self) -> "SetupBacktestRequest":
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Backtest timestamps must be timezone-aware.")
        if self.end <= self.start:
            raise ValueError("Backtest end must be after start.")
        return self


class SetupApprovalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ApprovalMode
    note: str = Field(default="", max_length=1000)
    accept_non_promising: bool = False
    skip_backtest: bool = False
    confirmation: str | None = Field(default=None, max_length=100)


class StrategySetupApproval(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_id: str
    setup_id: str
    setup_revision: int = Field(ge=1)
    mode: ApprovalMode
    status: ApprovalStatus
    note: str
    approved_at: datetime
    invalidated_at: datetime | None = None


class StrategyOpportunity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    opportunity_id: str
    scan_id: str
    strategy_type_id: str
    strategy_version: str
    timeframe_minutes: int
    configuration: dict[str, Any]
    symbol: str
    exchange: str
    market_type: str
    quote_currency: str
    current_price: Decimal | None = None
    price_observed_at: datetime | None = None
    price_state: PriceState
    scanner_score: int = Field(ge=0, le=100)
    signal: Literal["long", "short", "none"]
    eligible_now: bool
    qualifying_factors: tuple[str, ...]
    explanation_ar: str
    warnings: tuple[str, ...]
    discovered_at: datetime
    expires_at: datetime
    status: OpportunityStatus
    converted_setup_id: str | None = None


class OpportunityStatusUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["reviewed", "approved", "rejected", "ignored", "expired"]


class OpportunityConversionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    setup_defaults_override: StrategySetupDefaults | None = None
    configuration_overrides: dict[str, Any] = Field(default_factory=dict)


class BotDeploymentCreate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: StrategyEnvironment


class BotDeployment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: str
    setup_id: str
    setup_revision: int = Field(ge=1)
    template_id: str
    template_revision: int = Field(ge=1)
    runtime_instance_id: str
    environment: StrategyEnvironment
    strategy_type_id: str
    strategy_version: str
    configuration_snapshot: dict[str, Any]
    status: DeploymentStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_message: str | None = None


class WorkflowSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    templates: int = Field(ge=0)
    setups: int = Field(ge=0)
    opportunities_new: int = Field(ge=0)
    backtests_required: int = Field(ge=0)
    approvals_ready: int = Field(ge=0)
    deployments_running: int = Field(ge=0)


def price_state_from_market_state(state: MarketDataState) -> PriceState:
    if state == "fresh":
        return "fresh"
    if state in {"stale", "reconnecting"}:
        return "delayed"
    return "unavailable"
