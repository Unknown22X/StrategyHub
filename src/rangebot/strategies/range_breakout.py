"""Trading Range Breakout strategy using a prior completed-candle channel."""

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
    atr,
    blocked_result,
    engine_blocking_reasons,
    spread_percentage,
)
from rangebot.strategies._scanning import (
    inverse_ratio_score,
    make_candidate,
    proximity_score,
    ratio_score,
)


class RangeBreakoutConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_period: int = Field(default=20, ge=2, le=1000)
    confirmation_closes: int = Field(default=1, ge=1, le=5)
    volume_period: int = Field(default=20, ge=2, le=1000)
    volume_multiplier: Decimal = Field(default=Decimal("1.25"), ge=0)
    atr_period: int = Field(default=14, ge=2, le=1000)
    minimum_breakout_atr_multiple: Decimal = Field(default=Decimal("0.10"), ge=0)
    maximum_breakout_atr_multiple: Decimal = Field(default=Decimal("2"), gt=0)
    maximum_spread_percentage: Decimal = Field(default=Decimal("0.20"), ge=0)
    cooldown_candles: int = Field(default=0, ge=0, le=10000)
    require_signal_reset: bool = True
    direction: Literal["long_only", "short_only", "both"] = "both"
    take_profit_atr_multiple: Decimal = Field(default=Decimal("2"), gt=0)
    stop_loss_atr_multiple: Decimal = Field(default=Decimal("1"), gt=0)
    trailing_stop_atr_multiple: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_breakout_distance(self) -> "RangeBreakoutConfig":
        if (
            self.maximum_breakout_atr_multiple
            <= self.minimum_breakout_atr_multiple
        ):
            raise ValueError(
                "Maximum breakout distance must exceed the minimum distance."
            )
        return self


class RangeBreakoutEvaluator:
    type_id = "range_breakout"
    configuration_model = RangeBreakoutConfig

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult:
        config = RangeBreakoutConfig.model_validate(configuration)
        candles = context.completed_candles()
        engine_reasons = engine_blocking_reasons(context)
        if engine_reasons:
            return blocked_result(
                self.type_id,
                context,
                engine_reasons,
                used_closed_candles=len(candles),
            )

        reset_history = (
            config.confirmation_closes if config.require_signal_reset else 0
        )
        required = max(
            config.channel_period + config.confirmation_closes + reset_history,
            config.volume_period + config.confirmation_closes + reset_history,
            config.atr_period + config.confirmation_closes + reset_history,
        )
        if len(candles) < required:
            return blocked_result(
                self.type_id,
                context,
                ("history_warming_up",),
                used_closed_candles=len(candles),
                analysis={"required_closed_candles": required},
            )

        confirmation = candles[-config.confirmation_closes :]
        prior = candles[: -config.confirmation_closes]
        channel_window = prior[-config.channel_period :]
        channel_high = max(candle.high for candle in channel_window)
        channel_low = min(candle.low for candle in channel_window)
        current_close = confirmation[-1].close
        current_volume = confirmation[-1].volume
        average_volume = sum(
            (candle.volume for candle in prior[-config.volume_period :]),
            Decimal("0"),
        ) / Decimal(config.volume_period)
        current_atr = atr(candles, config.atr_period)
        spread = spread_percentage(context)

        long_confirmed = all(candle.close > channel_high for candle in confirmation)
        short_confirmed = all(candle.close < channel_low for candle in confirmation)
        direction: Literal["long", "short"] | None = None
        breakout_distance = Decimal("0")
        if long_confirmed:
            direction = "long"
            breakout_distance = current_close - channel_high
        elif short_confirmed:
            direction = "short"
            breakout_distance = channel_low - current_close

        previous_breakout_direction: Literal["long", "short"] | None = None
        if config.require_signal_reset:
            previous_confirmation = prior[-config.confirmation_closes :]
            previous_history = prior[: -config.confirmation_closes]
            previous_channel = previous_history[-config.channel_period :]
            previous_high = max(candle.high for candle in previous_channel)
            previous_low = min(candle.low for candle in previous_channel)
            if all(
                candle.close > previous_high for candle in previous_confirmation
            ):
                previous_breakout_direction = "long"
            elif all(
                candle.close < previous_low for candle in previous_confirmation
            ):
                previous_breakout_direction = "short"

        distance_multiple = (
            breakout_distance / current_atr if current_atr > 0 else Decimal("0")
        )
        blocking: list[str] = []
        if direction is None:
            blocking.append("inside_channel")
        elif direction == "long" and config.direction == "short_only":
            blocking.append("long_direction_disabled")
        elif direction == "short" and config.direction == "long_only":
            blocking.append("short_direction_disabled")
        if (
            direction is not None
            and previous_breakout_direction == direction
            and config.require_signal_reset
        ):
            blocking.append("signal_not_reset")
        if current_volume < average_volume * config.volume_multiplier:
            blocking.append("volume_confirmation_missing")
        if direction is not None:
            if distance_multiple < config.minimum_breakout_atr_multiple:
                blocking.append("breakout_distance_too_small")
            if distance_multiple > config.maximum_breakout_atr_multiple:
                blocking.append("possible_false_breakout")
        if spread is None:
            blocking.append("order_book_unavailable")
        elif spread > config.maximum_spread_percentage:
            blocking.append("spread_too_wide")
        if (
            context.candles_since_last_entry is not None
            and context.candles_since_last_entry < config.cooldown_candles
        ):
            blocking.append("cooldown_active")

        eligible = direction is not None and not blocking
        trade_request = (
            self._trade_request(context, direction, current_atr, config)
            if eligible and direction is not None
            else None
        )
        reason_codes = tuple(
            ([f"breakout_{direction}"] if direction is not None else [])
            + (["entry_conditions_passed"] if eligible else blocking)
        )
        explanation = (
            "تم تأكيد الاختراق بالحجم والمسافة المقبولة؛ الطلب جاهز لمدير الأوامر."
            if eligible
            else self._explanation(blocking)
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
                "channel_high": channel_high,
                "channel_low": channel_low,
                "current_close": current_close,
                "atr": current_atr,
                "breakout_distance": breakout_distance,
                "breakout_atr_multiple": distance_multiple,
                "current_volume": current_volume,
                "average_volume": average_volume,
                "required_volume": average_volume * config.volume_multiplier,
                "spread_percentage": spread,
                "confirmation_closes": config.confirmation_closes,
                "require_signal_reset": config.require_signal_reset,
                "previous_breakout_direction": previous_breakout_direction,
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
        config: RangeBreakoutConfig,
    ) -> StrategyTradeRequest:
        if direction == "long":
            take_profit = context.last_price + (
                current_atr * config.take_profit_atr_multiple
            )
            stop_loss_value = context.last_price - (
                current_atr * config.stop_loss_atr_multiple
            )
        else:
            take_profit = context.last_price - (
                current_atr * config.take_profit_atr_multiple
            )
            stop_loss_value = context.last_price + (
                current_atr * config.stop_loss_atr_multiple
            )
        trailing_stop = None
        if config.trailing_stop_atr_multiple is not None:
            trailing_distance = current_atr * config.trailing_stop_atr_multiple
            trailing_stop = (
                context.last_price - trailing_distance
                if direction == "long"
                else context.last_price + trailing_distance
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
            reason_code="range_breakout_confirmed",
        )

    @staticmethod
    def _explanation(blocking: list[str]) -> str:
        labels = {
            "inside_channel": "السعر ما زال داخل القناة السابقة.",
            "long_direction_disabled": "اختراق صاعد لكن الشراء معطل.",
            "short_direction_disabled": "اختراق هابط لكن البيع معطل.",
            "signal_not_reset": "الاختراق السابق ما زال ممتداً؛ يجب إعادة الدخول في القناة قبل إشارة جديدة.",
            "volume_confirmation_missing": "الحجم لا يؤكد الاختراق.",
            "breakout_distance_too_small": "مسافة الاختراق أقل من الحد المطلوب.",
            "possible_false_breakout": "مسافة الاختراق كبيرة وقد تشير إلى اختراق زائف.",
            "order_book_unavailable": "أفضل عرض وطلب غير متاحين.",
            "spread_too_wide": "الفارق السعري أوسع من الحد المسموح.",
            "cooldown_active": "فترة التهدئة بعد آخر دخول ما زالت فعالة.",
        }
        return " ".join(labels.get(reason, reason) for reason in blocking)


class RangeBreakoutScanner:
    type_id = "range_breakout"

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate:
        config = RangeBreakoutConfig.model_validate(configuration)
        result = RangeBreakoutEvaluator().evaluate(context, configuration)
        analysis = result.analysis
        channel_high = self._decimal(analysis.get("channel_high"))
        channel_low = self._decimal(analysis.get("channel_low"))
        current_close = self._decimal(analysis.get("current_close"))
        breakout_multiple = self._decimal(analysis.get("breakout_atr_multiple"))
        current_volume = self._decimal(analysis.get("current_volume"))
        required_volume = self._decimal(analysis.get("required_volume"))
        spread = self._decimal(analysis.get("spread_percentage"))
        current_atr = self._decimal(analysis.get("atr"))

        score = Decimal("0")
        if channel_high is not None and channel_low is not None and current_close is not None:
            score += Decimal("20")
            long_distance = (
                abs(channel_high - current_close) / current_close * Decimal("100")
                if current_close > 0
                else None
            )
            short_distance = (
                abs(current_close - channel_low) / current_close * Decimal("100")
                if current_close > 0
                else None
            )
        else:
            long_distance = None
            short_distance = None

        preferred_signal = "none"
        allowed_distances: list[tuple[str, Decimal]] = []
        if long_distance is not None and config.direction != "short_only":
            allowed_distances.append(("long", long_distance))
        if short_distance is not None and config.direction != "long_only":
            allowed_distances.append(("short", short_distance))
        nearest_boundary = None
        if allowed_distances:
            preferred_signal, nearest_boundary = min(
                allowed_distances,
                key=lambda item: item[1],
            )
            score += proximity_score(nearest_boundary, Decimal("1"), 25)

        if breakout_multiple is not None and result.signal != "none":
            if (
                config.minimum_breakout_atr_multiple
                <= breakout_multiple
                <= config.maximum_breakout_atr_multiple
            ):
                score += Decimal("20")
            else:
                score += ratio_score(
                    breakout_multiple,
                    config.minimum_breakout_atr_multiple or Decimal("0.1"),
                    10,
                )
        if required_volume is not None and required_volume > 0:
            score += ratio_score(current_volume, required_volume, 15)
        elif current_volume is not None and current_volume > 0:
            score += Decimal("15")
        if current_atr is not None and current_atr > 0:
            score += Decimal("5")
        score += inverse_ratio_score(spread, config.maximum_spread_percentage, 10)
        if result.eligible:
            score += Decimal("5")

        explanation = (
            result.explanation_ar
            if result.eligible
            else "تم ترتيب العقد حسب قربه من القناة السابقة وجودة الحجم وATR والفارق السعري واحتمال الاختراق."
        )
        return make_candidate(
            context=context,
            result=result,
            score=score,
            minimum_backtest_candles=minimum_backtest_candles,
            signal=result.signal if result.signal != "none" else preferred_signal,
            explanation_ar=explanation,
            metrics={
                "channel_high": channel_high,
                "channel_low": channel_low,
                "current_close": current_close,
                "nearest_boundary_percentage": nearest_boundary,
                "breakout_atr_multiple": breakout_multiple,
                "current_volume": current_volume,
                "required_volume": required_volume,
                "spread_percentage": spread,
                "atr": current_atr,
            },
        )

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))


STRATEGY_TYPE = StrategyTypeMetadata(
    type_id="range_breakout",
    display_name_ar="اختراق نطاق التداول",
    display_name_en="Trading Range Breakout",
    description_ar=(
        "يبني قناة من الشموع المكتملة السابقة فقط، ثم يتحقق من الإغلاق والحجم "
        "والمسافة وATR والسيولة قبل إنشاء طلب تداول."
    ),
    description_en=(
        "Builds a channel only from prior completed candles, then validates close "
        "confirmation, volume, ATR distance, spread, and cooldown."
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
    configuration_schema=RangeBreakoutConfig.model_json_schema(),
    candidate_metrics=(
        StrategyFieldMetadata(
            key="nearest_boundary_percentage",
            label_ar="المسافة من أقرب حد",
            label_en="Nearest boundary distance",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="breakout_atr_multiple",
            label_ar="مسافة الاختراق بالنسبة إلى ATR",
            label_en="Breakout distance / ATR",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="current_volume",
            label_ar="الحجم الحالي",
            label_en="Current volume",
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
    summary_metrics=(
        StrategyFieldMetadata(
            key="channel_high",
            label_ar="قمة القناة",
            label_en="Channel high",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="channel_low",
            label_ar="قاع القناة",
            label_en="Channel low",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="breakout_atr_multiple",
            label_ar="مسافة الاختراق بالنسبة إلى ATR",
            label_en="Breakout distance / ATR",
            value_type="decimal",
        ),
    ),
    live_analysis_fields=(
        StrategyFieldMetadata(
            key="current_volume",
            label_ar="الحجم الحالي",
            label_en="Current volume",
            value_type="decimal",
        ),
        StrategyFieldMetadata(
            key="required_volume",
            label_ar="الحجم المطلوب",
            label_en="Required volume",
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
    chart_overlays=(
        "channel_high",
        "channel_low",
        "entry",
        "take_profit",
        "stop_loss",
        "trailing_stop",
    ),
    status_badges=("breakout_status", "volume_confirmation", "entry_eligibility"),
    important_warnings_ar=(
        "الشمعة التي تؤكد الاختراق لا تدخل في حساب قناتها التاريخية.",
    ),
)

EVALUATOR_FACTORY = RangeBreakoutEvaluator
SCANNER_FACTORY = RangeBreakoutScanner
