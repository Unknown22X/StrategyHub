"""Decimal-safe helpers shared by built-in strategy evaluators."""

from decimal import Decimal

from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyEvaluationResult,
)


HUNDRED = Decimal("100")


def engine_blocking_reasons(context: StrategyEvaluationContext) -> tuple[str, ...]:
    reasons: list[str] = []
    if context.emergency_stop:
        reasons.append("emergency_stop")
    if not context.reconciliation_ready:
        reasons.append("reconciliation_not_ready")
    if context.market_data_state != "fresh":
        reasons.append(f"market_data_{context.market_data_state}")
    return tuple(reasons)


def blocked_result(
    type_id: str,
    context: StrategyEvaluationContext,
    reasons: tuple[str, ...],
    *,
    used_closed_candles: int,
    analysis: dict[str, object] | None = None,
) -> StrategyEvaluationResult:
    explanations = {
        "emergency_stop": "إيقاف الطوارئ مفعّل؛ لا يُسمح بدخول جديد.",
        "reconciliation_not_ready": "المصالحة غير مكتملة؛ تم منع الدخول.",
        "market_data_stale": "بيانات السوق قديمة؛ تم منع الدخول.",
        "market_data_reconnecting": "إعادة الاتصال ببيانات السوق جارية.",
        "market_data_unavailable": "بيانات السوق غير متاحة.",
        "history_warming_up": "عدد الشموع المكتملة غير كافٍ بعد.",
    }
    explanation = " ".join(explanations.get(reason, reason) for reason in reasons)
    return StrategyEvaluationResult(
        type_id=type_id,
        symbol=context.symbol,
        evaluated_at=context.evaluated_at,
        signal="none",
        eligible=False,
        reason_codes=reasons,
        explanation_ar=explanation,
        analysis=analysis or {},
        used_closed_candles=used_closed_candles,
        protective_actions_available=True,
        trade_request=None,
    )


def ema(values: tuple[Decimal, ...], period: int) -> Decimal:
    if period < 1 or len(values) < period:
        raise ValueError("EMA requires at least `period` values.")
    alpha = Decimal("2") / Decimal(period + 1)
    current = sum(values[:period], Decimal("0")) / Decimal(period)
    for value in values[period:]:
        current = (value * alpha) + (current * (Decimal("1") - alpha))
    return current


def true_ranges(candles: tuple[NormalizedCandle, ...]) -> tuple[Decimal, ...]:
    if not candles:
        return ()
    ranges: list[Decimal] = [candles[0].high - candles[0].low]
    for previous, current in zip(candles, candles[1:], strict=False):
        ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return tuple(ranges)


def atr(candles: tuple[NormalizedCandle, ...], period: int) -> Decimal:
    ranges = true_ranges(candles)
    if period < 1 or len(ranges) < period:
        raise ValueError("ATR requires at least `period` candles.")
    return sum(ranges[-period:], Decimal("0")) / Decimal(period)


def adx(candles: tuple[NormalizedCandle, ...], period: int) -> Decimal:
    """Return a deterministic rolling ADX approximation using closed candles."""
    if period < 1 or len(candles) < (period * 2):
        raise ValueError("ADX requires at least two periods of candles.")

    ranges = true_ranges(candles)
    plus_dm: list[Decimal] = [Decimal("0")]
    minus_dm: list[Decimal] = [Decimal("0")]
    for previous, current in zip(candles, candles[1:], strict=False):
        upward = current.high - previous.high
        downward = previous.low - current.low
        plus_dm.append(upward if upward > downward and upward > 0 else Decimal("0"))
        minus_dm.append(
            downward if downward > upward and downward > 0 else Decimal("0")
        )

    dx_values: list[Decimal] = []
    for end in range(period, len(candles)):
        start = end - period + 1
        range_sum = sum(ranges[start : end + 1], Decimal("0"))
        if range_sum <= 0:
            dx_values.append(Decimal("0"))
            continue
        plus_di = (
            sum(plus_dm[start : end + 1], Decimal("0")) / range_sum
        ) * HUNDRED
        minus_di = (
            sum(minus_dm[start : end + 1], Decimal("0")) / range_sum
        ) * HUNDRED
        denominator = plus_di + minus_di
        dx_values.append(
            Decimal("0")
            if denominator == 0
            else (abs(plus_di - minus_di) / denominator) * HUNDRED
        )
    if len(dx_values) < period:
        raise ValueError("ADX history is incomplete.")
    return sum(dx_values[-period:], Decimal("0")) / Decimal(period)


def spread_percentage(context: StrategyEvaluationContext) -> Decimal | None:
    if context.best_bid is None or context.best_ask is None:
        return None
    if context.best_ask < context.best_bid:
        return None
    midpoint = (context.best_ask + context.best_bid) / Decimal("2")
    if midpoint <= 0:
        return None
    return ((context.best_ask - context.best_bid) / midpoint) * HUNDRED
