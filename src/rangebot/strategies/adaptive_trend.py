"""Adaptive Trend Following strategy using closed candles and Decimal indicators."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rangebot.domain.discovery import StrategyScanCandidate
from rangebot.domain.strategy import StrategyFieldMetadata, StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.strategies._common import (
    HUNDRED,
    adx,
    atr,
    blocked_result,
    ema,
    engine_blocking_reasons,
    spread_percentage,
)
from rangebot.strategies._scanning import (
    inverse_ratio_score,
    make_candidate,
    ratio_score,
)


class AdaptiveTrendConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fast_ema_period: int = Field(default=9, ge=2, le=200)
    slow_ema_period: int = Field(default=21, ge=3, le=400)
    adx_period: int = Field(default=14, ge=2, le=100)
    minimum_adx: Decimal = Field(default=Decimal("20"), ge=0, le=100)
    atr_period: int = Field(default=14, ge=2, le=100)
    minimum_atr_percentage: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_spread_percentage: Decimal = Field(default=Decimal("0.20"), ge=0)
    minimum_volume: Decimal = Field(default=Decimal("0"), ge=0)
    cooldown_candles: int = Field(default=0, ge=0, le=10000)
    direction: Literal["long_only", "short_only", "both"] = "both"
    take_profit_atr_multiple: Decimal = Field(default=Decimal("2"), gt=0)
    stop_loss_atr_multiple: Decimal = Field(default=Decimal("1"), gt=0)
    trailing_stop_atr_multiple: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_periods(self) -> "AdaptiveTrendConfig":
        if self.fast_ema_period >= self.slow_ema_period:
            raise ValueError("Fast EMA period must be smaller than slow EMA period.")
        return self


class AdaptiveTrendEvaluator:
    type_id = "adaptive_trend"
    configuration_model = AdaptiveTrendConfig

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult:
        config = AdaptiveTrendConfig.model_validate(configuration)
        candles = context.completed_candles()
        engine_reasons = engine_blocking_reasons(context)
        if engine_reasons:
            return blocked_result(
                self.type_id,
                context,
                engine_reasons,
                used_closed_candles=len(candles),
            )

        required = max(
            config.slow_ema_period,
            config.atr_period,
            config.adx_period * 2,
        )
        if len(candles) < required:
            return blocked_result(
                self.type_id,
                context,
                ("history_warming_up",),
                used_closed_candles=len(candles),
                analysis={"required_closed_candles": required},
            )

        closes = tuple(candle.close for candle in candles)
        fast_ema = ema(closes, config.fast_ema_period)
        slow_ema = ema(closes, config.slow_ema_period)
        current_adx = adx(candles, config.adx_period)
        current_atr = atr(candles, config.atr_period)
        atr_percentage = (current_atr / candles[-1].close) * HUNDRED
        spread = spread_percentage(context)
        current_volume = candles[-1].volume
        trend = (
            "upward"
            if fast_ema > slow_ema
            else "downward"
            if fast_ema < slow_ema
            else "flat"
        )

        blocking: list[str] = []
        if current_adx < config.minimum_adx:
            blocking.append("adx_below_minimum")
        if atr_percentage < config.minimum_atr_percentage:
            blocking.append("atr_below_minimum")
        if current_volume < config.minimum_volume:
            blocking.append("volume_below_minimum")
        if spread is None:
            blocking.append("order_book_unavailable")
        elif spread > config.maximum_spread_percentage:
            blocking.append("spread_too_wide")
        if (
            context.candles_since_last_entry is not None
            and context.candles_since_last_entry < config.cooldown_candles
        ):
            blocking.append("cooldown_active")

        direction: Literal["long", "short"] | None = None
        if trend == "upward":
            if config.direction == "short_only":
                blocking.append("long_direction_disabled")
            else:
                direction = "long"
        elif trend == "downward":
            if config.direction == "long_only":
                blocking.append("short_direction_disabled")
            else:
                direction = "short"
        else:
            blocking.append("ema_trend_flat")

        eligible = direction is not None and not blocking
        trade_request = (
            self._trade_request(context, direction, current_atr, config)
            if eligible and direction is not None
            else None
        )
        reason_codes = tuple(
            ([f"trend_{trend}"] if trend != "flat" else [])
            + (["entry_conditions_passed"] if eligible else blocking)
        )
        explanation = (
            "الاتجاه مؤكد وشروط القوة والسيولة مكتملة؛ الطلب جاهز لمدير الأوامر."
            if eligible
            else self._explanation(blocking, trend)
        )
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal=direction if eligible and direction is not None else "none",
            eligible=eligible,
            reason_codes=reason_codes,
            explanation_ar=explanation,
            analysis={
                "trend": trend,
                "fast_ema": fast_ema,
                "slow_ema": slow_ema,
                "adx": current_adx,
                "atr": current_atr,
                "atr_percentage": atr_percentage,
                "spread_percentage": spread,
                "current_volume": current_volume,
                "trailing_stop_atr_multiple": config.trailing_stop_atr_multiple,
            },
            used_closed_candles=len(candles),
            protective_actions_available=True,
            trade_request=trade_request,
        )

    @staticmethod
    def _trade_request(
        context: StrategyEvaluationContext,
        direction: Literal["long", "short"],
        current_atr: Decimal,
        config: AdaptiveTrendConfig,
    ) -> StrategyTradeRequest:
        trailing_distance = (
            current_atr * config.trailing_stop_atr_multiple
            if config.trailing_stop_atr_multiple is not None
            else None
        )
        if direction == "long":
            take_profit = context.last_price + (
                current_atr * config.take_profit_atr_multiple
            )
            stop_loss_value = context.last_price - (
                current_atr * config.stop_loss_atr_multiple
            )
            trailing_stop = (
                context.last_price - trailing_distance
                if trailing_distance is not None
                else None
            )
        else:
            take_profit = context.last_price - (
                current_atr * config.take_profit_atr_multiple
            )
            stop_loss_value = context.last_price + (
                current_atr * config.stop_loss_atr_multiple
            )
            trailing_stop = (
                context.last_price + trailing_distance
                if trailing_distance is not None
                else None
            )
        return StrategyTradeRequest(
            symbol=context.symbol,
            direction=direction,
            reference_price=context.last_price,
            take_profit_price=take_profit if take_profit > 0 else None,
            stop_loss_price=stop_loss_value if stop_loss_value > 0 else None,
            trailing_stop_price=(
                trailing_stop if trailing_stop is not None and trailing_stop > 0 else None
            ),
            reason_code="adaptive_trend_confirmed",
        )

    @staticmethod
    def _explanation(blocking: list[str], trend: str) -> str:
        labels = {
            "adx_below_minimum": "قوة الاتجاه ADX أقل من الحد المطلوب.",
            "atr_below_minimum": "حركة ATR أقل من الحد المطلوب.",
            "volume_below_minimum": "الحجم أقل من الحد المطلوب.",
            "order_book_unavailable": "أفضل عرض وطلب غير متاحين.",
            "spread_too_wide": "الفارق السعري أوسع من الحد المسموح.",
            "cooldown_active": "فترة التهدئة بعد آخر دخول ما زالت فعالة.",
            "long_direction_disabled": "الاتجاه الصاعد موجود لكن الشراء معطل.",
            "short_direction_disabled": "الاتجاه الهابط موجود لكن البيع معطل.",
            "ema_trend_flat": "المتوسطان لا يحددان اتجاهاً واضحاً.",
        }
        prefix = f"الاتجاه الحالي: {trend}. "
        return prefix + " ".join(labels.get(reason, reason) for reason in blocking)


class AdaptiveTrendScanner:
    type_id = "adaptive_trend"

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate:
        config = AdaptiveTrendConfig.model_validate(configuration)
        result = AdaptiveTrendEvaluator().evaluate(context, configuration)
        analysis = result.analysis
        fast_ema = self._decimal(analysis.get("fast_ema"))
        slow_ema = self._decimal(analysis.get("slow_ema"))
        current_adx = self._decimal(analysis.get("adx"))
        atr_percentage = self._decimal(analysis.get("atr_percentage"))
        current_volume = self._decimal(analysis.get("current_volume"))
        spread = self._decimal(analysis.get("spread_percentage"))
        trend = str(analysis.get("trend") or "flat")

        score = Decimal("0")
        if fast_ema is not None and slow_ema is not None:
            score += Decimal("15")
            separation = (
                abs(fast_ema - slow_ema) / slow_ema * HUNDRED
                if slow_ema > 0
                else Decimal("0")
            )
            score += ratio_score(separation, Decimal("0.50"), 20)
        else:
            separation = None
        score += ratio_score(current_adx, max(config.minimum_adx, Decimal("1")), 25)
        if config.minimum_atr_percentage > 0:
            score += ratio_score(atr_percentage, config.minimum_atr_percentage, 10)
        elif atr_percentage is not None and atr_percentage > 0:
            score += Decimal("10")
        if config.minimum_volume > 0:
            score += ratio_score(current_volume, config.minimum_volume, 10)
        elif current_volume is not None and current_volume > 0:
            score += Decimal("10")
        score += inverse_ratio_score(spread, config.maximum_spread_percentage, 10)
        if result.eligible:
            score += Decimal("10")

        preferred_signal = (
            "long"
            if trend == "upward" and config.direction != "short_only"
            else "short"
            if trend == "downward" and config.direction != "long_only"
            else "none"
        )
        explanation = (
            result.explanation_ar
            if result.eligible
            else "تم ترتيب العقد حسب وضوح اتجاه EMA وقوة ADX وحركة ATR والحجم والفارق السعري."
        )
        return make_candidate(
            context=context,
            result=result,
            score=score,
            minimum_backtest_candles=minimum_backtest_candles,
            signal=result.signal if result.signal != "none" else preferred_signal,
            explanation_ar=explanation,
            metrics={
                "trend": trend,
                "fast_ema": fast_ema,
                "slow_ema": slow_ema,
                "ema_separation_percentage": separation,
                "adx": current_adx,
                "atr_percentage": atr_percentage,
                "current_volume": current_volume,
                "spread_percentage": spread,
            },
        )

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))


STRATEGY_TYPE = StrategyTypeMetadata(
    type_id="adaptive_trend",
    display_name_ar="اتباع الاتجاه المتكيف",
    display_name_en="Adaptive Trend Following",
    description_ar=(
        "يتحقق من اتجاه EMA وقوة ADX وحركة ATR والحجم والفارق السعري باستخدام "
        "الشموع المكتملة فقط."
    ),
    description_en=(
        "Uses completed candles to combine EMA direction, ADX strength, ATR movement, "
        "volume, spread, and cooldown validation."
    ),
    version="1",
    supports_long=True,
    supports_short=True,
    supported_timeframes=(5, 15, 30, 60, 240, 1440),
    required_market_data_feeds=(
        "candlesticks",
        "last_price",
        "mark_price",
        "best_bid_ask",
        "volume",
    ),
    implementation_status="working",
    supports_scanning=True,
    supports_backtesting=True,
    minimum_backtest_candles=300,
    configuration_schema=AdaptiveTrendConfig.model_json_schema(),
    candidate_metrics=(
        StrategyFieldMetadata(
            key="trend",
            label_ar="الاتجاه",
            label_en="Trend",
            value_type="status",
        ),
        StrategyFieldMetadata(
            key="adx",
            label_ar="قوة الاتجاه ADX",
            label_en="ADX strength",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="ema_separation_percentage",
            label_ar="تباعد المتوسطات",
            label_en="EMA separation",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="spread_percentage",
            label_ar="الفارق السعري",
            label_en="Spread",
            value_type="decimal",
            unit="percent",
        ),
    ),
    summary_metrics=(
        StrategyFieldMetadata(
            key="trend",
            label_ar="الاتجاه",
            label_en="Trend",
            value_type="status",
        ),
        StrategyFieldMetadata(
            key="adx",
            label_ar="قوة الاتجاه ADX",
            label_en="ADX strength",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="atr",
            label_ar="الحركة ATR",
            label_en="ATR movement",
            value_type="decimal",
        ),
    ),
    live_analysis_fields=(
        StrategyFieldMetadata(
            key="fast_ema",
            label_ar="EMA السريع",
            label_en="Fast EMA",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="slow_ema",
            label_ar="EMA البطيء",
            label_en="Slow EMA",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="spread_percentage",
            label_ar="الفارق السعري",
            label_en="Spread",
            value_type="decimal",
            unit="percent",
        ),
    ),
    recommended_widgets=(
        "active_strategy",
        "strategy_chart",
        "decision_explanation",
        "risk_status",
    ),
    chart_overlays=("fast_ema", "slow_ema", "entry", "take_profit", "stop_loss"),
    status_badges=("trend", "adx_strength", "entry_eligibility"),
    important_warnings_ar=(
        "لا تستخدم الاستراتيجية الشمعة غير المكتملة في تأكيد الاتجاه.",
    ),
)

EVALUATOR_FACTORY = AdaptiveTrendEvaluator
SCANNER_FACTORY = AdaptiveTrendScanner
