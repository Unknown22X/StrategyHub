"""Deterministic backtesting contracts shared by discovery and future research tools."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BacktestExitReason = Literal[
    "take_profit",
    "stop_loss",
    "trailing_stop",
    "time_exit",
    "end_of_data",
]
BacktestAssessmentLabel = Literal[
    "promising",
    "mixed",
    "weak",
    "insufficient_data",
]
BacktestMode = Literal["manual_symbols", "historical_scanner"]
BacktestAmbiguityPolicy = Literal[
    "conservative", "optimistic", "lower_timeframe", "mark_ambiguous"
]
BacktestSizingMode = Literal[
    "fixed_quote", "percentage_available", "percentage_starting", "risk_based"
]
BacktestUniverseQuality = Literal[
    "exact_historical", "approximate_historical", "current_survivor"
]
BacktestOrderStatus = Literal[
    "pending", "submitted", "filled", "canceled", "expired", "rejected"
]
BacktestRunStatus = Literal[
    "queued", "loading_data", "running", "calculating_results",
    "completed", "failed", "canceled"
]


class BacktestExecutionSettings(BaseModel):
    """Immutable candle-execution assumptions shared by both opportunity sources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entry_expiration_candles: int | None = Field(default=None, ge=1, le=10000)
    time_exit_candles: int | None = Field(default=None, ge=1, le=100000)
    take_profit_order_type: Literal["market", "limit"] = "limit"
    stop_loss_order_type: Literal["market", "limit"] = "market"
    take_profit_percentage: Decimal | None = Field(default=None, gt=0, le=1000)
    stop_loss_percentage: Decimal | None = Field(default=None, gt=0, le=1000)
    dca_enabled: bool = False
    dca_spacing_percentage: Decimal = Field(default=Decimal("1"), gt=0, le=100)
    dca_allocations: tuple[Decimal, ...] = (Decimal("100"),)
    recalculate_target_after_dca: bool = True
    cooldown_candles: int = Field(default=0, ge=0, le=100000)

    @model_validator(mode="after")
    def validate_dca(self) -> "BacktestExecutionSettings":
        if any(value <= 0 for value in self.dca_allocations):
            raise ValueError("DCA allocations must be positive.")
        if sum(self.dca_allocations, Decimal("0")) != Decimal("100"):
            raise ValueError("DCA allocations must total 100%.")
        if not self.dca_enabled and self.dca_allocations != (Decimal("100"),):
            raise ValueError("Disabled DCA must use one 100% allocation.")
        if self.dca_enabled and len(self.dca_allocations) < 2:
            raise ValueError("Enabled DCA requires at least two allocations.")
        return self


class BacktestSettings(BaseModel):
    """Execution and assessment assumptions for one deterministic simulation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_balance: Decimal = Field(default=Decimal("1000"), gt=0)
    margin_per_trade: Decimal = Field(default=Decimal("100"), gt=0)
    leverage: int = Field(default=1, ge=1, le=200)
    maker_fee_rate: Decimal = Field(default=Decimal("0.0002"), ge=0, le=1)
    taker_fee_rate: Decimal = Field(default=Decimal("0.0005"), ge=0, le=1)
    slippage_basis_points: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    spread_basis_points: Decimal = Field(default=Decimal("0"), ge=0, le=1000)
    ambiguity_policy: BacktestAmbiguityPolicy = "conservative"
    position_sizing_mode: BacktestSizingMode = "fixed_quote"
    position_size_percentage: Decimal = Field(default=Decimal("10"), gt=0, le=100)
    risk_percentage: Decimal = Field(default=Decimal("1"), gt=0, le=100)
    maximum_positions: int = Field(default=1, ge=1, le=100)
    maximum_allocation_percentage: Decimal = Field(
        default=Decimal("100"), gt=0, le=100
    )
    maximum_volume_participation_percentage: Decimal | None = Field(
        default=None, gt=0, le=100
    )
    default_take_profit_percentage: Decimal = Field(
        default=Decimal("5"), gt=0, le=1000
    )
    default_stop_loss_percentage: Decimal = Field(
        default=Decimal("3"), gt=0, le=1000
    )
    minimum_trades_for_assessment: int = Field(default=5, ge=1, le=10000)


class BacktestPortfolioRequest(BaseModel):
    """Immutable production run snapshot for manual or historical-scanner mode."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: BacktestMode
    setup_id: str | None = None
    setup_revision: int | None = Field(default=None, ge=1)
    strategy_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    strategy_version: str = Field(min_length=1, max_length=100)
    scanner_version: str | None = Field(default=None, max_length=100)
    exchange: str = "gateio"
    market_type: Literal["usdt_perpetual"] = "usdt_perpetual"
    quote_currency: str = "USDT"
    symbols: tuple[str, ...] = Field(min_length=1, max_length=200)
    timeframe_minutes: int = Field(ge=1, le=10080)
    additional_timeframes: tuple[int, ...] = ()
    configuration: dict[str, Any] = Field(default_factory=dict)
    parameter_overrides: dict[str, Any] = Field(default_factory=dict)
    start: datetime
    end: datetime
    warmup_candles: int = Field(default=0, ge=0, le=100000)
    scan_frequency_candles: int = Field(default=1, ge=1, le=10000)
    maximum_candidates: int = Field(default=20, ge=1, le=200)
    universe_quality: BacktestUniverseQuality = "current_survivor"
    data_provider: str = "gateio_rest"
    data_version: str | None = Field(default=None, max_length=500)
    code_version: str | None = Field(default=None, max_length=200)
    pre_test_hypothesis: str = Field(default="", max_length=4000)
    execution: BacktestExecutionSettings = Field(default_factory=BacktestExecutionSettings)
    settings: BacktestSettings = Field(default_factory=BacktestSettings)

    @field_validator("start", "end")
    @classmethod
    def require_portfolio_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Backtest timestamps must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def validate_portfolio_request(self) -> "BacktestPortfolioRequest":
        if self.end <= self.start:
            raise ValueError("Backtest end must be after start.")
        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("Backtest symbols must be unique.")
        if (self.setup_id is None) != (self.setup_revision is None):
            raise ValueError("Backtest setup identity requires both ID and revision.")
        return self


class BacktestCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    occurred_at: datetime
    symbol: str
    score: int = Field(ge=0, le=100)
    rank: int = Field(ge=1)
    qualified: bool
    selected: bool
    factor_values: dict[str, Any] = Field(default_factory=dict)
    reason_codes: tuple[str, ...] = ()
    explanation_ar: str
    rejection_reason: str | None = None


class BacktestDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    occurred_at: datetime
    symbol: str
    event: Literal["evaluated", "qualified", "selected", "rejected", "entered", "exited"]
    qualified: bool = False
    selected: bool = False
    reason_codes: tuple[str, ...] = ()
    explanation_ar: str
    available_candle_count: int = Field(ge=0)


class BacktestOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    symbol: str
    role: Literal["entry", "dca", "take_profit", "stop_loss", "time_exit"]
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit"]
    submitted_at: datetime
    eligible_from: datetime
    requested_price: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal = Field(ge=0)
    status: BacktestOrderStatus
    expires_after_candle: int | None = Field(default=None, ge=1)
    rejection_reason: str | None = None


class BacktestFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str
    order_id: str
    symbol: str
    role: Literal["entry", "dca", "take_profit", "stop_loss", "time_exit"]
    filled_at: datetime
    price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    fee: Decimal = Field(ge=0)
    slippage_amount: Decimal = Field(ge=0)
    maker: bool = False


class BacktestRunRequest(BaseModel):
    """User-selected candidate and historical window to simulate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scan_id: str | None = None
    setup_id: str | None = None
    setup_revision: int | None = Field(default=None, ge=1)
    strategy_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    symbol: str = Field(min_length=1, max_length=64)
    timeframe_minutes: int = Field(ge=1, le=10080)
    configuration: dict[str, Any] = Field(default_factory=dict)
    start: datetime
    end: datetime
    settings: BacktestSettings = Field(default_factory=BacktestSettings)

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Backtest timestamps must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "BacktestRunRequest":
        if (self.setup_id is None) != (self.setup_revision is None):
            raise ValueError("Backtest setup identity requires both ID and revision.")
        if self.end <= self.start:
            raise ValueError("Backtest end must be after start.")
        return self

    def spec(self) -> "BacktestSpec":
        return BacktestSpec(
            strategy_type_id=self.strategy_type_id,
            symbol=self.symbol,
            timeframe_minutes=self.timeframe_minutes,
            configuration=self.configuration,
            settings=self.settings,
        )


class BacktestSpec(BaseModel):
    """Strategy and market identity used by a backtest run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    symbol: str = Field(min_length=1, max_length=64)
    timeframe_minutes: int = Field(ge=1, le=10080)
    configuration: dict[str, Any] = Field(default_factory=dict)
    settings: BacktestSettings = Field(default_factory=BacktestSettings)


class BacktestTrade(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_number: int = Field(ge=1)
    symbol: str = ""
    direction: Literal["long", "short"]
    signal_at: datetime
    entered_at: datetime
    exited_at: datetime
    entry_price: Decimal = Field(gt=0)
    average_entry_price: Decimal | None = Field(default=None, gt=0)
    exit_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    allocated_margin: Decimal = Field(gt=0)
    leverage: int = Field(ge=1)
    gross_pnl: Decimal
    fees: Decimal = Field(ge=0)
    funding: Decimal = Field(default=Decimal("0"))
    net_pnl: Decimal
    return_on_margin_percentage: Decimal
    exit_reason: BacktestExitReason
    bars_held: int = Field(ge=1)
    entry_fills: tuple[BacktestFill, ...] = ()
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    take_profit_price: Decimal | None = Field(default=None, gt=0)
    result_r: Decimal | None = None
    slippage: Decimal = Field(default=Decimal("0"), ge=0)
    ambiguous: bool = False
    entry_explanation_ar: str = ""


class BacktestEquityPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    occurred_at: datetime
    equity: Decimal
    drawdown_percentage: Decimal = Field(ge=0)
    cash: Decimal | None = None
    invested_capital: Decimal = Field(default=Decimal("0"), ge=0)


class BacktestMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    starting_balance: Decimal
    ending_balance: Decimal
    net_profit: Decimal
    return_percentage: Decimal
    total_trades: int = Field(ge=0)
    winning_trades: int = Field(ge=0)
    losing_trades: int = Field(ge=0)
    win_rate_percentage: Decimal = Field(ge=0, le=100)
    gross_profit: Decimal = Field(ge=0)
    gross_loss: Decimal = Field(le=0)
    fees: Decimal = Field(ge=0)
    funding: Decimal
    average_win: Decimal = Field(ge=0)
    average_loss: Decimal = Field(le=0)
    profit_factor: Decimal | None = Field(default=None, ge=0)
    maximum_drawdown_percentage: Decimal = Field(ge=0)
    maximum_losing_streak: int = Field(ge=0)
    long_net_pnl: Decimal
    short_net_pnl: Decimal
    largest_winner_share_percentage: Decimal | None = Field(default=None, ge=0)
    gross_return_percentage: Decimal = Decimal("0")
    ending_equity: Decimal | None = None
    expectancy: Decimal = Decimal("0")
    average_r: Decimal | None = None
    largest_win: Decimal = Decimal("0")
    largest_loss: Decimal = Decimal("0")
    maximum_winning_streak: int = Field(default=0, ge=0)
    consecutive_losses: int = Field(default=0, ge=0)
    total_fees: Decimal = Field(default=Decimal("0"), ge=0)
    total_slippage: Decimal = Field(default=Decimal("0"), ge=0)
    average_holding_seconds: Decimal = Field(default=Decimal("0"), ge=0)
    exposure_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    ambiguous_trades: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> "BacktestMetrics":
        if self.winning_trades + self.losing_trades > self.total_trades:
            raise ValueError("Winning and losing counts exceed total trades.")
        return self


class BacktestAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    label: BacktestAssessmentLabel
    score: int = Field(ge=0, le=100)
    summary_ar: str = Field(min_length=1, max_length=2000)
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class BacktestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: BacktestSpec
    started_at: datetime
    ended_at: datetime
    candle_count: int = Field(ge=0)
    trades: tuple[BacktestTrade, ...]
    equity_curve: tuple[BacktestEquityPoint, ...]
    metrics: BacktestMetrics
    assessment: BacktestAssessment
    warnings: tuple[str, ...] = ()
    portfolio_request: BacktestPortfolioRequest | None = None
    candidates: tuple[BacktestCandidate, ...] = ()
    decisions: tuple[BacktestDecision, ...] = ()
    orders: tuple[BacktestOrder, ...] = ()
    fills: tuple[BacktestFill, ...] = ()
    post_test_observations: str = ""


class StoredBacktestRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_id: str
    scan_id: str | None = None
    strategy_version: str
    created_at: datetime
    request: BacktestRunRequest
    result: BacktestResult
    applied_instance_id: str | None = None


class BacktestReadiness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    missing_rules: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class StoredPortfolioBacktestRun(BaseModel):
    """Persisted immutable production run and its editable post-test note."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    backtest_id: str
    status: BacktestRunStatus
    progress_percentage: int = Field(default=0, ge=0, le=100)
    stage_message_ar: str = ""
    configuration_hash: str
    input_data_hash: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    request: BacktestPortfolioRequest
    result: BacktestResult | None = None
    failure_reason: str | None = None
    post_test_observations: str = ""


class BacktestPostTestNotesUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    observations: str = Field(default="", max_length=10000)


class BacktestStrategyCreateRequest(BaseModel):
    """Create a reviewable stopped strategy from one stored backtest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    environment: Literal["live", "testnet", "paper"] = "paper"
    direction: Literal["long_only", "short_only", "both"] = "both"
