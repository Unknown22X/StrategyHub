"""Normalized strategy evaluation contracts owned by the central engine."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


MarketDataState = Literal["fresh", "stale", "reconnecting", "unavailable"]
StrategySignal = Literal["long", "short", "none"]


class NormalizedCandle(BaseModel):
    """Exchange-neutral candle with explicit completion state and volume."""

    model_config = ConfigDict(frozen=True)

    opened_at: datetime
    closed_at: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(default=Decimal("0"), ge=0)
    closed: bool = True

    @model_validator(mode="after")
    def validate_ohlc_and_time(self) -> "NormalizedCandle":
        if self.closed_at <= self.opened_at:
            raise ValueError("Candle close time must be after open time.")
        if self.high < max(self.open, self.close) or self.low > min(
            self.open, self.close
        ):
            raise ValueError("Candle OHLC values are inconsistent.")
        if self.high < self.low:
            raise ValueError("Candle high must not be below low.")
        return self


class StrategyEvaluationContext(BaseModel):
    """Authoritative engine snapshot supplied to one strategy evaluation."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1, max_length=64)
    evaluated_at: datetime
    timeframe_minutes: int = Field(ge=1, le=10080)
    candles: tuple[NormalizedCandle, ...]
    higher_timeframe_candles: dict[int, tuple[NormalizedCandle, ...]] = Field(
        default_factory=dict
    )
    last_price: Decimal = Field(gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    market_data_state: MarketDataState = "fresh"
    reconciliation_ready: bool = True
    emergency_stop: bool = False
    candles_since_last_entry: int | None = Field(default=None, ge=0)

    def completed_candles(self) -> tuple[NormalizedCandle, ...]:
        return tuple(
            sorted(
                (
                    candle
                    for candle in self.candles
                    if candle.closed and candle.closed_at <= self.evaluated_at
                ),
                key=lambda candle: candle.opened_at,
            )
        )

    def completed_higher_timeframe(
        self, timeframe_minutes: int
    ) -> tuple[NormalizedCandle, ...]:
        return tuple(
            candle
            for candle in self.higher_timeframe_candles.get(timeframe_minutes, ())
            if candle.closed and candle.closed_at <= self.evaluated_at
        )


class StrategyTradeRequest(BaseModel):
    """Unsized trade intent requiring Order Manager and risk validation."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    direction: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    reference_price: Decimal = Field(gt=0)
    take_profit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss_price: Decimal | None = Field(default=None, gt=0)
    trailing_stop_price: Decimal | None = Field(default=None, gt=0)
    reason_code: str = Field(min_length=1, max_length=100)


class StrategyEvaluationResult(BaseModel):
    """Explainable strategy decision; eligibility never submits an order directly."""

    model_config = ConfigDict(frozen=True)

    type_id: str
    symbol: str
    evaluated_at: datetime
    signal: StrategySignal
    eligible: bool
    reason_codes: tuple[str, ...]
    explanation_ar: str
    analysis: dict[str, Any] = Field(default_factory=dict)
    used_closed_candles: int = Field(ge=0)
    protective_actions_available: bool = True
    trade_request: StrategyTradeRequest | None = None


class StrategyEvaluator(Protocol):
    type_id: str

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult: ...
