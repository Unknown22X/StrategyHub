"""Explainable Decimal-safe Paper range analysis."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


TIMEFRAME_CANDLE_COUNTS = {5: 5, 15: 15, 60: 60, 1440: 1440}


class Candle(BaseModel):
    """A normalized public candle; exchange payload fields never enter this model."""

    model_config = ConfigDict(frozen=True)

    opened_at: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)


class RangeAnalysisConfig(BaseModel):
    """Paper range and direction settings used for a single evaluation."""

    model_config = ConfigDict(frozen=True)

    mode: Literal["rolling_window", "current_gate_candle"] = "rolling_window"
    timeframe_minutes: Literal[5, 15, 60, 1440] = 5
    range_mode: Literal["exact", "interval"] = "interval"
    target_range_percentage: Decimal = Field(default=Decimal("20"), ge=0)
    tolerance_percentage_points: Decimal = Field(default=Decimal("0"), ge=0)
    minimum_range_percentage: Decimal = Field(default=Decimal("20"), ge=0)
    maximum_range_percentage: Decimal = Field(default=Decimal("25"), ge=0)
    proximity_percentage: Decimal = Field(default=Decimal("3"), ge=0)
    direction: Literal["long_only", "short_only", "both"] = "both"


class ConditionDetail(BaseModel):
    """One passed or failed entry condition with an operator-facing Arabic explanation."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    arabic_explanation: str


class RangeAnalysisRequest(BaseModel):
    config: RangeAnalysisConfig
    candles: list[Candle]
    last_price: Decimal = Field(gt=0)
    evaluated_at: datetime | None = None
    symbol: str | None = None


class RangeAnalysisResult(BaseModel):
    """Structured Paper decision details; protective actions stay available on blocks."""

    model_config = ConfigDict(frozen=True)

    history_status: Literal["ready", "warming_up", "history_gap"]
    entry_blocked: bool
    protective_actions_available: bool
    opening_price: Decimal | None
    high: Decimal | None
    low: Decimal | None
    range_percentage: Decimal | None
    long_proximity_percentage: Decimal | None
    short_proximity_percentage: Decimal | None
    long_eligible: bool
    short_eligible: bool
    blocking_reasons: list[str]
    conditions: list[ConditionDetail]


def evaluate_range(
    config: RangeAnalysisConfig,
    candles: list[Candle],
    last_price: Decimal,
    evaluated_at: datetime | None = None,
) -> RangeAnalysisResult:
    """Evaluate current Paper conditions with no float arithmetic or side effects."""
    selected, history_status = _select_candles(config, candles, evaluated_at)
    if history_status != "ready":
        explanation = (
            "السجل غير مكتمل" if history_status == "warming_up" else "فجوة في السجل"
        )
        return _blocked_history_result(history_status, explanation)

    opening_price = selected[0].open
    high = max(candle.high for candle in selected)
    low = min(candle.low for candle in selected)
    if low <= 0 or high < low or any(not _valid_candle(candle) for candle in selected):
        return _blocked_history_result("history_gap", "بيانات الشموع غير صالحة")

    range_percentage = ((high - low) / low) * Decimal("100")
    long_proximity = ((last_price - low) / low) * Decimal("100")
    short_proximity = ((high - last_price) / high) * Decimal("100")
    range_passed = _range_passes(config, range_percentage)
    long_passed = long_proximity >= 0 and long_proximity <= config.proximity_percentage
    short_passed = (
        short_proximity >= 0 and short_proximity <= config.proximity_percentage
    )
    long_eligible = range_passed and long_passed and config.direction != "short_only"
    short_eligible = range_passed and short_passed and config.direction != "long_only"
    blocking_reasons: list[str] = []

    if long_eligible and short_eligible:
        long_eligible = False
        short_eligible = False
        blocking_reasons.append("conflicting_signals")

    conditions = [
        ConditionDetail(name="history", passed=True, arabic_explanation="السجل جاهز"),
        ConditionDetail(
            name="range",
            passed=range_passed,
            arabic_explanation=(
                "النطاق ضمن الإعدادات" if range_passed else "النطاق خارج الإعدادات"
            ),
        ),
        ConditionDetail(
            name="long_proximity",
            passed=long_passed,
            arabic_explanation=(
                "قرب الشراء صالح" if long_passed else "قرب الشراء غير صالح"
            ),
        ),
        ConditionDetail(
            name="short_proximity",
            passed=short_passed,
            arabic_explanation=(
                "قرب البيع صالح" if short_passed else "قرب البيع غير صالح"
            ),
        ),
        ConditionDetail(
            name="direction",
            passed=long_eligible or short_eligible,
            arabic_explanation=(
                "اتجاه الإشارة صالح"
                if long_eligible or short_eligible
                else "لا توجد إشارة دخول صالحة"
            ),
        ),
        ConditionDetail(
            name="long_direction",
            passed=long_eligible,
            arabic_explanation=(
                "إشارة الشراء صالحة" if long_eligible else "إشارة الشراء غير صالحة"
            ),
        ),
        ConditionDetail(
            name="short_direction",
            passed=short_eligible,
            arabic_explanation=(
                "إشارة البيع صالحة" if short_eligible else "إشارة البيع غير صالحة"
            ),
        ),
    ]
    if "conflicting_signals" in blocking_reasons:
        conditions.append(
            ConditionDetail(
                name="conflict",
                passed=False,
                arabic_explanation="تعارضت إشارتا الشراء والبيع",
            )
        )

    return RangeAnalysisResult(
        history_status="ready",
        entry_blocked=not (long_eligible or short_eligible),
        protective_actions_available=True,
        opening_price=opening_price,
        high=high,
        low=low,
        range_percentage=range_percentage,
        long_proximity_percentage=long_proximity,
        short_proximity_percentage=short_proximity,
        long_eligible=long_eligible,
        short_eligible=short_eligible,
        blocking_reasons=blocking_reasons,
        conditions=conditions,
    )


def _select_candles(
    config: RangeAnalysisConfig, candles: list[Candle], evaluated_at: datetime | None
) -> tuple[list[Candle], Literal["ready", "warming_up", "history_gap"]]:
    ordered = sorted(candles, key=lambda candle: candle.opened_at)
    if config.mode == "current_gate_candle":
        if len(ordered) != 1 or evaluated_at is None:
            return [], "history_gap"
        candle = ordered[0]
        if _interval_start(candle.opened_at, config.timeframe_minutes) != candle.opened_at:
            return [], "history_gap"
        current_start = _interval_start(evaluated_at, config.timeframe_minutes)
        if candle.opened_at != current_start:
            return [], "history_gap"
        return ordered, "ready"

    required_count = TIMEFRAME_CANDLE_COUNTS[config.timeframe_minutes]
    if len(ordered) < required_count:
        if len(ordered) > 1 and ordered[-1].opened_at - ordered[
            0
        ].opened_at > _one_minute() * (len(ordered) - 1):
            return [], "history_gap"
        return [], "warming_up"
    selected = ordered[-required_count:]
    if any(
        later.opened_at - earlier.opened_at != _one_minute()
        for earlier, later in zip(selected, selected[1:], strict=False)
    ):
        return [], "history_gap"
    return selected, "ready"


def _interval_start(value: datetime, timeframe_minutes: int) -> datetime:
    anchor = value.replace(year=1970, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elapsed_minutes = int((value - anchor).total_seconds() // 60)
    return anchor + timedelta(
        minutes=(elapsed_minutes // timeframe_minutes) * timeframe_minutes
    )


def _one_minute() -> timedelta:
    return timedelta(minutes=1)


def _valid_candle(candle: Candle) -> bool:
    return (
        candle.low <= min(candle.open, candle.close)
        and candle.high >= max(candle.open, candle.close)
        and candle.high >= candle.low
    )


def _range_passes(config: RangeAnalysisConfig, range_percentage: Decimal) -> bool:
    if config.range_mode == "exact":
        difference = abs(range_percentage - config.target_range_percentage)
        return difference <= config.tolerance_percentage_points
    return (
        config.minimum_range_percentage
        <= range_percentage
        <= config.maximum_range_percentage
    )


def _blocked_history_result(
    history_status: Literal["warming_up", "history_gap"], explanation: str
) -> RangeAnalysisResult:
    return RangeAnalysisResult(
        history_status=history_status,
        entry_blocked=True,
        protective_actions_available=True,
        opening_price=None,
        high=None,
        low=None,
        range_percentage=None,
        long_proximity_percentage=None,
        short_proximity_percentage=None,
        long_eligible=False,
        short_eligible=False,
        blocking_reasons=[history_status],
        conditions=[
            ConditionDetail(
                name="history", passed=False, arabic_explanation=explanation
            )
        ],
    )
