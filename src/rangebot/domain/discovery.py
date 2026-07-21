"""Strategy-owned market scanning contracts for the Discovery Lab."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from rangebot.domain.strategy_runtime import (
    MarketDataState,
    NormalizedCandle,
    StrategyEvaluationContext,
)


class DiscoveryMarketContract(BaseModel):
    """Sanitized Gate public market row used to build scanner contexts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=64)
    last_price: Decimal = Field(gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    index_price: Decimal | None = Field(default=None, gt=0)
    best_bid: Decimal | None = Field(default=None, gt=0)
    best_ask: Decimal | None = Field(default=None, gt=0)
    volume_24h_quote: Decimal = Field(default=Decimal("0"), ge=0)
    funding_rate: Decimal | None = None
    change_percentage: Decimal | None = None
    high_24h: Decimal | None = Field(default=None, gt=0)
    low_24h: Decimal | None = Field(default=None, gt=0)


class StrategyScanRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    timeframe_minutes: int = Field(ge=1, le=10080)
    configuration: dict[str, Any] = Field(default_factory=dict)
    minimum_quote_volume: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_symbols: int = Field(default=30, ge=1, le=200)
    maximum_candidates: int = Field(default=20, ge=1, le=200)
    minimum_score: int = Field(default=0, ge=0, le=100)


class StrategyScanCandidate(BaseModel):
    """Explainable strategy-specific suitability result for one contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    exchange: str = "gateio"
    market_type: Literal["usdt_perpetual"] = "usdt_perpetual"
    quote_currency: str = "USDT"
    current_price: Decimal | None = Field(default=None, gt=0)
    price_observed_at: datetime | None = None
    score: int = Field(ge=0, le=100)
    signal: Literal["long", "short", "none"]
    eligible_now: bool
    evaluated_at: datetime
    market_data_state: MarketDataState
    explanation_ar: str = Field(min_length=1, max_length=2000)
    reason_codes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = Field(default_factory=dict)
    completed_candles: int = Field(ge=0)
    backtest_ready: bool


class StrategyScanFailure(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    reason_code: str
    explanation_ar: str = Field(min_length=1, max_length=1000)


class StoredStrategyScan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scan_id: str
    strategy_version: str
    created_at: datetime
    request: StrategyScanRequest
    result: "StrategyScanResult"


class StrategyScanResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_type_id: str
    timeframe_minutes: int
    scanned_at: datetime
    universe_symbols: int = Field(default=0, ge=0)
    scanned_symbols: int = Field(ge=0)
    candidates: tuple[StrategyScanCandidate, ...]
    failures: tuple[StrategyScanFailure, ...] = ()


class DiscoveryMarketDataProvider(Protocol):
    def contracts(
        self,
        *,
        minimum_quote_volume: Decimal = Decimal("0"),
        maximum_contracts: int | None = None,
    ) -> tuple[DiscoveryMarketContract, ...]: ...

    def latest_candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        limit: int,
    ) -> tuple[NormalizedCandle, ...]: ...

    def candles(
        self,
        symbol: str,
        timeframe_minutes: int,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedCandle, ...]: ...


class StrategyScanner(Protocol):
    type_id: str

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate: ...
