"""Common metadata contracts for dynamically registered strategy types."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrategyFieldMetadata(BaseModel):
    """One strategy-specific value that a generic dashboard may render."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1, max_length=100)
    label_ar: str = Field(min_length=1, max_length=200)
    label_en: str = Field(min_length=1, max_length=200)
    value_type: str = Field(min_length=1, max_length=50)
    unit: str | None = Field(default=None, max_length=50)


class StrategyTypeMetadata(BaseModel):
    """Frontend-neutral description of one available strategy implementation."""

    model_config = ConfigDict(frozen=True)

    type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    display_name_ar: str = Field(min_length=1, max_length=200)
    display_name_en: str = Field(min_length=1, max_length=200)
    description_ar: str = Field(min_length=1, max_length=1000)
    description_en: str = Field(min_length=1, max_length=1000)
    version: str = Field(min_length=1, max_length=50)
    supports_monitoring: bool = True
    supports_automatic_trading: bool = True
    supports_long: bool = True
    supports_short: bool = True
    supported_directions: tuple[str, ...] = ("long", "short")
    supported_timeframes: tuple[int, ...] = (1, 5, 15, 30, 60, 240, 1440)
    required_market_data_feeds: tuple[str, ...] = (
        "candlesticks",
        "last_price",
        "mark_price",
        "best_bid_ask",
    )
    implementation_status: Literal["working", "experimental", "disabled"] = "working"
    evaluation_cadence: Literal["market_update", "closed_candle"] = "closed_candle"
    supports_scanning: bool = False
    supports_backtesting: bool = False
    minimum_backtest_candles: int = Field(default=100, ge=2, le=1000000)
    configuration_schema: dict[str, Any] = Field(default_factory=dict)
    candidate_metrics: tuple[StrategyFieldMetadata, ...] = ()
    summary_metrics: tuple[StrategyFieldMetadata, ...] = ()
    live_analysis_fields: tuple[StrategyFieldMetadata, ...] = ()
    recommended_widgets: tuple[str, ...] = ()
    chart_overlays: tuple[str, ...] = ()
    status_badges: tuple[str, ...] = ()
    important_warnings_ar: tuple[str, ...] = ()


StrategyEnvironment = Literal["paper", "testnet", "live"]
StrategyLifecycle = Literal["stopped", "running", "monitoring", "paused", "error"]
StrategyDirection = Literal["long", "short", "both"]


class BuiltInStrategyTemplate(BaseModel):
    """Immutable product template projected from one registered implementation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str = Field(pattern=r"^builtin:[a-z][a-z0-9_-]{1,63}$")
    type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    version: str = Field(min_length=1, max_length=50)
    immutable: Literal[True] = True
    supports_monitoring: bool
    supports_automatic_trading: bool
    supports_backtesting: bool
    supports_scanning: bool
    supported_directions: tuple[str, ...]
    supported_timeframes: tuple[int, ...]
    configuration_schema: dict[str, Any] = Field(default_factory=dict)


class StrategyInstanceFromTemplateCreate(BaseModel):
    """Create an Instance from an immutable Template and optional user Preset."""

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(pattern=r"^builtin:[a-z][a-z0-9_-]{1,63}$")
    preset_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    environment: StrategyEnvironment = "paper"
    symbol: str = Field(min_length=1, max_length=64)
    timeframe_minutes: int | None = Field(default=None, ge=1, le=10080)
    direction: StrategyDirection | None = None
    requested_margin: Decimal | None = Field(default=None, gt=0)
    requested_leverage: int | None = Field(default=None, ge=1, le=100)
    configuration_overrides: dict[str, Any] = Field(default_factory=dict)


class StrategyInstanceCreate(BaseModel):
    """Create one saved configuration of a registered strategy type."""

    model_config = ConfigDict(extra="forbid")

    type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    template_id: str | None = Field(
        default=None,
        pattern=r"^builtin:[a-z][a-z0-9_-]{1,63}$",
    )
    preset_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    environment: StrategyEnvironment = "live"
    symbol: str = Field(min_length=1, max_length=64)
    timeframe_minutes: int = Field(ge=1, le=10080)
    direction: StrategyDirection = "both"
    requested_margin: Decimal = Field(default=Decimal("20"), gt=0)
    requested_leverage: int = Field(default=3, ge=1, le=100)
    configuration: dict[str, Any] = Field(default_factory=dict)


class StrategyInstanceUpdate(BaseModel):
    """Editable fields for a stopped or paused strategy instance."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    environment: StrategyEnvironment | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    timeframe_minutes: int | None = Field(default=None, ge=1, le=10080)
    direction: StrategyDirection | None = None
    requested_margin: Decimal | None = Field(default=None, gt=0)
    requested_leverage: int | None = Field(default=None, ge=1, le=100)
    configuration: dict[str, Any] | None = None


class StrategyInstanceDuplicate(BaseModel):
    """Optional overrides applied when copying a stopped strategy instance."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)


class StrategyArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=500)


class StrategyInstance(StrategyInstanceCreate):
    """Committed saved strategy instance returned by the engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instance_id: str
    template_id: str = Field(pattern=r"^builtin:[a-z][a-z0-9_-]{1,63}$")
    template_version: str = Field(min_length=1, max_length=50)
    preset_id: str | None = Field(default=None, max_length=64)
    preset_revision: int | None = Field(default=None, ge=1)
    status: StrategyLifecycle
    is_pinned: bool = False
    archived_at: datetime | None = None
    archive_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    revision: int = Field(ge=1)


class StrategyDeletionReadiness(BaseModel):
    """Explain whether permanent deletion is safe or archival is required."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    instance_id: str
    can_delete: bool
    must_archive: bool
    reason_codes: tuple[str, ...] = ()
    messages: dict[str, str] = Field(default_factory=dict)


class StrategyOverviewItem(StrategyInstance):
    """Engine-owned dashboard projection for one saved strategy instance."""

    current_signal: str | None = None
    latest_decision_eligible: bool | None = None
    latest_reason_codes: tuple[str, ...] = ()
    last_decision_at: datetime | None = None
    today_realized_pnl: Decimal | None = None
    total_realized_pnl: Decimal | None = None
    win_rate_percentage: Decimal | None = None
    total_fills: int = Field(default=0, ge=0)
    last_trade_at: datetime | None = None
    warning_codes: tuple[str, ...] = ()


StrategyRunMode = Literal["automatic", "monitoring"]
StrategyRunStatus = Literal["active", "completed", "error"]
TradeOrigin = Literal[
    "automatic_strategy", "monitoring_conversion", "manual", "legacy_automatic"
]
TradeIdentityKind = Literal["order", "position"]


class StrategyConfigurationVersion(BaseModel):
    model_config = ConfigDict(frozen=True)

    version_id: int
    instance_id: str
    revision: int = Field(ge=1)
    requested_margin: Decimal
    requested_leverage: int
    configuration: dict[str, Any]
    created_at: datetime


class StrategyRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    instance_id: str
    mode: StrategyRunMode
    status: StrategyRunStatus
    configuration_revision: int = Field(ge=1)
    configuration_snapshot: dict[str, Any]
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None


class StrategyDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: str = Field(min_length=1, max_length=100)
    eligible: bool
    reason_codes: tuple[str, ...] = ()
    analysis: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class StrategyDecision(StrategyDecisionCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: int
    run_id: str
    instance_id: str
    symbol: str
    occurred_at: datetime


class TradeOwnershipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_kind: TradeIdentityKind
    external_identity: str = Field(min_length=1, max_length=200)
    origin: TradeOrigin
    environment: Literal["paper", "testnet", "live"] | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    direction: Literal["long", "short"] | None = None
    trailing_stop_price: Decimal | None = Field(default=None, gt=0)
    trailing_stop_distance: Decimal | None = Field(default=None, gt=0)
    trailing_state: Literal["desired", "active", "error"] | None = None
    trailing_order_id: str | None = Field(default=None, max_length=200)
    trailing_last_error: str | None = Field(default=None, max_length=500)
    trailing_updated_at: datetime | None = None
    instance_id: str | None = None
    run_id: str | None = None


class TradeOwnership(TradeOwnershipCreate):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ownership_id: int
    created_at: datetime
