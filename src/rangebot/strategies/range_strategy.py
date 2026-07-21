"""Existing Range Strategy adapted to the common evaluator contract."""

from decimal import Decimal
from typing import Any

from rangebot.domain.analysis import (
    Candle,
    RangeAnalysisConfig,
    evaluate_range,
)
from rangebot.domain.discovery import StrategyScanCandidate
from rangebot.domain.strategy import StrategyFieldMetadata, StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
    StrategyTradeRequest,
)
from rangebot.strategies._common import (
    blocked_result,
    engine_blocking_reasons,
    spread_percentage,
)
from rangebot.strategies._scanning import (
    inverse_ratio_score,
    make_candidate,
    proximity_score,
)


class RangeStrategyEvaluator:
    """Preserve the existing Range calculation while returning common metadata."""

    type_id = "range"
    configuration_model = RangeAnalysisConfig

    def evaluate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
    ) -> StrategyEvaluationResult:
        config = RangeAnalysisConfig.model_validate(configuration)
        source_candles = tuple(
            sorted(
                (
                    candle
                    for candle in context.candles
                    if candle.opened_at <= context.evaluated_at
                ),
                key=lambda candle: candle.opened_at,
            )
        )
        engine_reasons = engine_blocking_reasons(context)
        if engine_reasons:
            return blocked_result(
                self.type_id,
                context,
                engine_reasons,
                used_closed_candles=sum(candle.closed for candle in source_candles),
            )

        result = evaluate_range(
            config,
            [
                Candle(
                    opened_at=candle.opened_at,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                )
                for candle in source_candles
            ],
            context.last_price,
            context.evaluated_at,
        )
        signal = (
            "long"
            if result.long_eligible
            else "short"
            if result.short_eligible
            else "none"
        )
        eligible = signal != "none"
        failed_conditions = tuple(
            condition.name for condition in result.conditions if not condition.passed
        )
        reason_codes = (
            ("entry_conditions_passed",)
            if eligible
            else tuple(result.blocking_reasons) + failed_conditions
        )
        explanation = " ".join(
            condition.arabic_explanation for condition in result.conditions
        )
        trade_request = (
            StrategyTradeRequest(
                symbol=context.symbol,
                direction=signal,
                reference_price=context.last_price,
                reason_code="range_entry_eligible",
            )
            if eligible and signal in {"long", "short"}
            else None
        )
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal=signal,
            eligible=eligible,
            reason_codes=reason_codes,
            explanation_ar=explanation,
            analysis={
                "history_status": result.history_status,
                "opening_price": result.opening_price,
                "range_high": result.high,
                "range_low": result.low,
                "range_percentage": result.range_percentage,
                "long_proximity_percentage": result.long_proximity_percentage,
                "short_proximity_percentage": result.short_proximity_percentage,
                "long_eligible": result.long_eligible,
                "short_eligible": result.short_eligible,
                "blocking_reasons": result.blocking_reasons,
            },
            used_closed_candles=sum(candle.closed for candle in source_candles),
            protective_actions_available=result.protective_actions_available,
            trade_request=trade_request,
        )


class RangeStrategyScanner:
    type_id = "range"

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, Any],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate:
        config = RangeAnalysisConfig.model_validate(configuration)
        result = RangeStrategyEvaluator().evaluate(context, configuration)
        analysis = result.analysis
        range_percentage = self._decimal(analysis.get("range_percentage"))
        long_proximity = self._decimal(analysis.get("long_proximity_percentage"))
        short_proximity = self._decimal(analysis.get("short_proximity_percentage"))
        spread = spread_percentage(context)

        score = Decimal("0")
        if analysis.get("history_status") == "ready":
            score += Decimal("20")
        score += self._range_fit_score(config, range_percentage)

        allowed_proximities: list[tuple[str, Decimal]] = []
        if long_proximity is not None and config.direction != "short_only":
            allowed_proximities.append(("long", long_proximity))
        if short_proximity is not None and config.direction != "long_only":
            allowed_proximities.append(("short", short_proximity))
        preferred_direction = "none"
        nearest_proximity = None
        if allowed_proximities:
            preferred_direction, nearest_proximity = min(
                allowed_proximities,
                key=lambda item: item[1],
            )
            score += proximity_score(nearest_proximity, config.proximity_percentage, 25)
        score += inverse_ratio_score(spread, Decimal("0.20"), 10)
        if result.eligible:
            score += Decimal("10")

        explanation = (
            result.explanation_ar
            if result.eligible
            else "تم ترتيب العقد حسب تطابق عرض النطاق وقرب السعر من أحد الحدين والسيولة الحالية."
        )
        return make_candidate(
            context=context,
            result=result,
            score=score,
            minimum_backtest_candles=minimum_backtest_candles,
            signal=result.signal if result.signal != "none" else preferred_direction,
            explanation_ar=explanation,
            metrics={
                "range_percentage": range_percentage,
                "range_high": analysis.get("range_high"),
                "range_low": analysis.get("range_low"),
                "long_proximity_percentage": long_proximity,
                "short_proximity_percentage": short_proximity,
                "nearest_proximity_percentage": nearest_proximity,
                "spread_percentage": spread,
                "history_status": analysis.get("history_status"),
            },
        )

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))

    @staticmethod
    def _range_fit_score(
        config: RangeAnalysisConfig,
        range_percentage: Decimal | None,
    ) -> Decimal:
        if range_percentage is None:
            return Decimal("0")
        if config.range_mode == "exact":
            tolerance = max(config.tolerance_percentage_points, Decimal("0.1"))
            distance = abs(range_percentage - config.target_range_percentage)
            return max(
                Decimal("0"),
                Decimal("35") * (
                    Decimal("1") - min(distance / (tolerance * Decimal("3")), Decimal("1"))
                ),
            )
        if config.minimum_range_percentage <= range_percentage <= config.maximum_range_percentage:
            return Decimal("35")
        boundary = (
            config.minimum_range_percentage
            if range_percentage < config.minimum_range_percentage
            else config.maximum_range_percentage
        )
        width = max(
            config.maximum_range_percentage - config.minimum_range_percentage,
            Decimal("1"),
        )
        distance = abs(range_percentage - boundary)
        return max(
            Decimal("0"),
            Decimal("35") * (
                Decimal("1") - min(distance / (width * Decimal("2")), Decimal("1"))
            ),
        )


STRATEGY_TYPE = StrategyTypeMetadata(
    type_id="range",
    display_name_ar="استراتيجية النطاق",
    display_name_en="Range Strategy",
    description_ar=(
        "تراقب اتساع النطاق وقرب السعر من الحد الأدنى أو الأعلى وتشرح سبب "
        "السماح بالدخول أو منعه."
    ),
    description_en=(
        "Evaluates range width and price proximity to the range boundaries, "
        "with explicit entry eligibility reasons."
    ),
    version="1",
    supports_long=True,
    supports_short=True,
    supported_timeframes=(5, 15, 60, 1440),
    required_market_data_feeds=(
        "candlesticks",
        "last_price",
        "mark_price",
        "best_bid_ask",
    ),
    implementation_status="working",
    evaluation_cadence="market_update",
    supports_scanning=True,
    supports_backtesting=True,
    minimum_backtest_candles=200,
    configuration_schema=RangeAnalysisConfig.model_json_schema(),
    candidate_metrics=(
        StrategyFieldMetadata(
            key="range_percentage",
            label_ar="عرض النطاق",
            label_en="Range width",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="nearest_proximity_percentage",
            label_ar="أقرب مسافة من الحد",
            label_en="Nearest boundary distance",
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
            key="range_percentage",
            label_ar="النطاق الحالي",
            label_en="Current range",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="signal_state",
            label_ar="حالة الإشارة",
            label_en="Signal state",
            value_type="status",
        ),
    ),
    live_analysis_fields=(
        StrategyFieldMetadata(
            key="long_proximity_percentage",
            label_ar="المسافة من القاع",
            label_en="Distance from low",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="short_proximity_percentage",
            label_ar="المسافة من القمة",
            label_en="Distance from high",
            value_type="decimal",
            unit="percent",
        ),
        StrategyFieldMetadata(
            key="blocking_reasons",
            label_ar="أسباب منع الدخول",
            label_en="Entry blocking reasons",
            value_type="list",
        ),
    ),
    recommended_widgets=(
        "active_strategy",
        "strategy_chart",
        "decision_explanation",
        "risk_status",
    ),
    chart_overlays=("range_high", "range_low", "entry", "take_profit", "stop_loss"),
    status_badges=("history_status", "entry_eligibility", "direction"),
    important_warnings_ar=(
        "لا يُسمح بالدخول عند نقص السجل أو قدم بيانات السوق.",
    ),
)

EVALUATOR_FACTORY = RangeStrategyEvaluator
SCANNER_FACTORY = RangeStrategyScanner
