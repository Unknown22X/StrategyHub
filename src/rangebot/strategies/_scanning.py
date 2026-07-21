"""Shared helpers for explainable strategy-owned market scanning."""

from decimal import Decimal
from typing import Any, Literal

from rangebot.domain.discovery import StrategyScanCandidate
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
)
from rangebot.strategies._common import spread_percentage


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def clamp_score(value: Decimal | int) -> int:
    numeric = int(Decimal(value).to_integral_value(rounding="ROUND_HALF_UP"))
    return max(0, min(100, numeric))


def ratio_score(value: Decimal | None, target: Decimal, points: int) -> Decimal:
    if value is None or target <= ZERO or value <= ZERO:
        return ZERO
    return min(value / target, Decimal("1")) * Decimal(points)


def inverse_ratio_score(value: Decimal | None, maximum: Decimal, points: int) -> Decimal:
    if value is None or maximum <= ZERO:
        return ZERO
    if value <= maximum:
        return Decimal(points)
    excess_ratio = (value - maximum) / maximum
    return max(ZERO, Decimal(points) * (Decimal("1") - excess_ratio))


def proximity_score(value: Decimal | None, threshold: Decimal, points: int) -> Decimal:
    if value is None or threshold < ZERO or value < ZERO:
        return ZERO
    if threshold == ZERO:
        return Decimal(points) if value == ZERO else ZERO
    return max(
        ZERO,
        Decimal(points) * (Decimal("1") - min(value / (threshold * Decimal("3")), Decimal("1"))),
    )


def scan_warnings(
    context: StrategyEvaluationContext,
    result: StrategyEvaluationResult,
    minimum_backtest_candles: int,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if context.market_data_state != "fresh":
        warnings.append("بيانات السوق ليست حديثة؛ لا تعتمد على هذا الترشيح قبل التحديث.")
    if spread_percentage(context) is None:
        warnings.append("أفضل عرض وطلب غير متاحين، لذلك لا يمكن تقييم السيولة بالكامل.")
    if result.used_closed_candles < minimum_backtest_candles:
        warnings.append("السجل الحالي غير كافٍ لإجراء اختبار خلفي موثوق.")
    if "history_warming_up" in result.reason_codes:
        warnings.append("الاستراتيجية ما زالت في مرحلة تجميع السجل المطلوب.")
    return tuple(warnings)


def make_candidate(
    *,
    context: StrategyEvaluationContext,
    result: StrategyEvaluationResult,
    score: Decimal | int,
    minimum_backtest_candles: int,
    metrics: dict[str, Any],
    signal: Literal["long", "short", "none"] | None = None,
    explanation_ar: str | None = None,
) -> StrategyScanCandidate:
    completed = len(context.completed_candles())
    return StrategyScanCandidate(
        symbol=context.symbol,
        exchange="gateio",
        market_type="usdt_perpetual",
        quote_currency="USDT",
        current_price=context.last_price,
        price_observed_at=context.evaluated_at,
        score=clamp_score(score),
        signal=signal or result.signal,
        eligible_now=result.eligible,
        evaluated_at=result.evaluated_at,
        market_data_state=context.market_data_state,
        explanation_ar=explanation_ar or result.explanation_ar,
        reason_codes=result.reason_codes,
        warnings=scan_warnings(context, result, minimum_backtest_candles),
        metrics=metrics,
        completed_candles=completed,
        backtest_ready=completed >= minimum_backtest_candles,
    )
