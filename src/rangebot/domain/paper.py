"""Paper Trading account models with no exchange-account authority."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from rangebot.domain.entry_preview import EntryPreview, EntryPreviewRequest


PAPER_MODE = "paper"
DEFAULT_PAPER_STARTING_BALANCE = Decimal("1000")
DEFAULT_PAPER_FEE_RATE = Decimal("0.001")


class PaperAccountSnapshot(BaseModel):
    """The complete local state of the Paper Account."""

    model_config = ConfigDict(frozen=True)

    mode: str = PAPER_MODE
    starting_balance: Decimal
    available_futures_balance: Decimal
    position_quantity: Decimal
    pending_entry: bool
    protection_state: str
    cooldown_until: datetime | None
    risk_state: str
    last_change_reason: str
    revision: int


class PaperAccountChange(BaseModel):
    """Validated operator request to initialize or reset Paper Trading."""

    starting_balance: Decimal = Field(default=DEFAULT_PAPER_STARTING_BALANCE, gt=0)
    reason: str = Field(min_length=1, max_length=500)
    confirmation: str | None = None


class PaperAuditEntry(BaseModel):
    """A non-secret audit record for a Paper Account state change."""

    model_config = ConfigDict(frozen=True)

    occurred_at: datetime
    action: str
    reason: str


class PaperFeeSchedule(BaseModel):
    """Local Paper-only Maker and Taker fee rates, never fetched from Gate.io."""

    model_config = ConfigDict(frozen=True)

    maker_fee_rate: Decimal = Field(default=DEFAULT_PAPER_FEE_RATE, ge=0, lt=1)
    taker_fee_rate: Decimal = Field(default=DEFAULT_PAPER_FEE_RATE, ge=0, lt=1)


class PaperMarketEntryRequest(BaseModel):
    """A final, Paper-only confirmation to create a simulated Market position."""

    model_config = ConfigDict(frozen=True)

    preview: EntryPreview
    current_request: EntryPreviewRequest
    slippage_percentage: Decimal = Field(default=Decimal("0.10"), ge=0)
    confirmation: str
    market_ready: bool = True
    history_ready: bool = True


class PaperPosition(BaseModel):
    """The single local position created by a confirmed Paper Market entry."""

    model_config = ConfigDict(frozen=True)

    direction: str
    quantity: Decimal
    entry_price: Decimal
    entry_fee: Decimal
    allocated_margin: Decimal
    leverage: int
    taker_fee_rate: Decimal
    maker_fee_rate: Decimal
    opened_at: datetime


class PaperProtection(BaseModel):
    """Paper TP/SL instructions, always capped to the remaining position."""

    model_config = ConfigDict(frozen=True)

    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    quantity: Decimal
    state: str
    warning: str | None = None


class PaperMarketEntryResult(BaseModel):
    """Persisted result of one confirmed Paper Market entry."""

    model_config = ConfigDict(frozen=True)

    position: PaperPosition
    account: PaperAccountSnapshot
    activity: str


class PaperProtectionCheck(BaseModel):
    market_price: Decimal = Field(gt=0)


class PaperProtectionTriggerResult(BaseModel):
    triggered: bool
    reason: str | None = None
    account: PaperAccountSnapshot
    exit_fee_rate: Decimal | None = None
    exit_fee: Decimal | None = None
    activity: str | None = None


class PaperCloseRequest(BaseModel):
    market_price: Decimal = Field(gt=0)
    confirmation: str
    quantity: Decimal | None = Field(default=None, gt=0)


class PaperCloseResult(BaseModel):
    account: PaperAccountSnapshot
    exit_fee_rate: Decimal
    exit_fee: Decimal
    realized_pnl: Decimal
    activity: str


class PaperPendingEntry(BaseModel):
    id: int
    kind: Literal["limit"]
    direction: Literal["long", "short"]
    quantity: Decimal
    limit_price: Decimal
    expires_at: datetime
    signal_zone: str | None = None
    state: Literal["pending"] = "pending"


class PaperLimitEntryRequest(BaseModel):
    preview: EntryPreview
    current_request: EntryPreviewRequest
    limit_price: Decimal = Field(gt=0)
    placement_price: Decimal = Field(gt=0)
    expires_at: datetime
    confirmation: str
    signal_zone: str | None = None
    signal_symbol: str | None = None


class PaperAutomaticLimitRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    trigger_zone: str = Field(min_length=1, max_length=200)
    preview: EntryPreview
    current_request: EntryPreviewRequest
    placement_price: Decimal = Field(gt=0)
    offset_percentage: Decimal = Field(default=Decimal("0"), ge=0)
    expires_at: datetime
    market_ready: bool = True
    history_ready: bool = True


class PaperLimitCheck(BaseModel):
    market_price: Decimal = Field(gt=0)
    observed_at: datetime


class PaperLimitCheckResult(BaseModel):
    filled: bool
    expired: bool
    account: PaperAccountSnapshot
    pending_entry: PaperPendingEntry | None = None
    position: PaperPosition | None = None
    activity: str | None = None


class PaperRiskSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    daily_loss_limit: Decimal = Field(default=Decimal("100"), ge=0)
    losing_trade_limit: int = Field(default=3, ge=0)
    automatic_fill_limit: int = Field(default=10, ge=0)
    cooldown_seconds: int = Field(default=60, ge=0)


class PaperRiskSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    day: str
    baseline_balance: Decimal
    realized_net_loss: Decimal
    losing_trades: int
    automatic_fills: int
    settings: PaperRiskSettings
    manual_entries_blocked: bool
    automatic_entries_blocked: bool
    cooldown_until: datetime | None


class PaperRiskAdjustment(BaseModel):
    realized_pnl: Decimal = Decimal("0")
    fees: Decimal = Decimal("0")
    funding: Decimal = Decimal("0")
    automatic_fill: bool = False


class PaperAutomaticSignalRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=64)
    trigger_zone: str = Field(min_length=1, max_length=200)
    direction: Literal["long", "short"]
    preview: EntryPreview
    current_request: EntryPreviewRequest
    market_ready: bool = True
    history_ready: bool = True


class PaperUsedSignal(BaseModel):
    symbol: str
    direction: Literal["long", "short"]
    trigger_zone: str
    used_at: datetime
    reset_seen: bool


class PaperDirectionalResetRequest(BaseModel):
    market_price: Decimal = Field(gt=0)
    reset_distance_percentage: Decimal = Field(default=Decimal("1"), gt=0)


class PaperEmergencyStopRequest(BaseModel):
    confirmation: str
    reason: str = Field(min_length=1, max_length=500)


class PaperEmergencyState(BaseModel):
    active: bool
    reason: str | None
    activated_at: datetime | None
    automatic_trading_requires_restart: bool


class PaperResumeRequest(BaseModel):
    confirmation: str


class PaperProfile(BaseModel):
    id: int
    name: str
    settings: dict[str, object]
    safety_fingerprint: str


class PaperProfileChange(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    settings: dict[str, JsonValue] = Field(default_factory=dict)
    confirmation: str | None = None

    @field_validator("settings")
    @classmethod
    def reject_runtime_or_secret_settings(
        cls, settings: dict[str, object]
    ) -> dict[str, JsonValue]:
        allowed = {
            "theme", "language", "font_size", "layout", "leverage",
            "maker_fee_rate", "taker_fee_rate", "daily_loss_limit",
            "losing_trade_limit", "automatic_fill_limit", "cooldown_seconds",
        }
        for key in settings:
            if key not in allowed:
                raise ValueError("Paper profiles may contain only approved Paper settings.")
        return settings


class PaperProfileApplyResult(BaseModel):
    profile: PaperProfile
    change_summary: list[str]
    activity: str


class PaperHelpTopic(BaseModel):
    slug: str
    title_ar: str
    body_ar: str


class PaperVerificationRecord(BaseModel):
    id: int
    recorded_at: datetime
    engine_build: str
    safety_fingerprint: str
    evidence: str
    stale: bool
    advisory_warning_ar: str | None = None


class PaperVerificationRequest(BaseModel):
    evidence: str = Field(min_length=1, max_length=2000)
