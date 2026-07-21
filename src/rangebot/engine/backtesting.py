"""Deterministic, exchange-neutral strategy backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP, localcontext
from typing import Any, Protocol

from rangebot.domain.backtesting import (
    BacktestAssessment,
    BacktestCandidate,
    BacktestDecision,
    BacktestEquityPoint,
    BacktestFill,
    BacktestMetrics,
    BacktestOrder,
    BacktestPortfolioRequest,
    BacktestResult,
    BacktestSpec,
    BacktestTrade,
)
from rangebot.domain.orders import FuturesContractRules
from rangebot.domain.strategy_runtime import (
    NormalizedCandle,
    StrategyEvaluationContext,
    StrategyTradeRequest,
)
from rangebot.engine.strategy_registry import StrategyRegistry


HUNDRED = Decimal("100")
TEN_THOUSAND = Decimal("10000")
ZERO = Decimal("0")


class FundingCostProvider(Protocol):
    """Reusable seam for historical funding costs without coupling to Gate transport."""

    warning_ar: str | None

    def cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal: ...


class ZeroFundingCostProvider:
    warning_ar = "لم تتوفر بيانات تمويل تاريخية؛ تم احتساب التمويل بقيمة صفر."

    def cost(
        self,
        *,
        symbol: str,
        direction: str,
        notional: Decimal,
        entered_at: datetime,
        exited_at: datetime,
    ) -> Decimal:
        del symbol, direction, notional, entered_at, exited_at
        return ZERO


@dataclass
class _PendingSignal:
    signal_at: datetime
    request: StrategyTradeRequest


@dataclass
class _OpenPosition:
    direction: str
    signal_at: datetime
    entered_at: datetime
    entry_price: Decimal
    quantity: Decimal
    allocated_margin: Decimal
    leverage: int
    entry_fee: Decimal
    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    trailing_stop_price: Decimal | None
    trailing_distance: Decimal | None
    bars_held: int = 0


@dataclass
class _PortfolioOrder:
    log_index: int
    submitted_index: int
    margin: Decimal
    allocation_percentage: Decimal
    request: StrategyTradeRequest


@dataclass
class _PortfolioPosition:
    symbol: str
    direction: str
    signal_at: datetime
    entered_at: datetime
    entry_explanation_ar: str
    fills: list[BacktestFill]
    allocated_margin: Decimal
    entry_fees: Decimal
    average_entry: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    initial_take_profit: Decimal | None
    take_profit_percentage: Decimal | None
    exit_eligible_from: datetime
    bars_held: int = 0
    time_exit_pending: bool = False


class BacktestEngine:
    """Run strategy evaluators over completed candles without look-ahead execution."""

    def __init__(
        self,
        registry: StrategyRegistry,
        funding_costs: FundingCostProvider | None = None,
    ) -> None:
        self._registry = registry
        self._funding_costs = funding_costs or ZeroFundingCostProvider()

    def run(
        self,
        spec: BacktestSpec,
        candles: tuple[NormalizedCandle, ...] | list[NormalizedCandle],
    ) -> BacktestResult:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self._run(spec, candles)

    def run_portfolio(
        self,
        request: BacktestPortfolioRequest,
        candles_by_symbol: dict[str, tuple[NormalizedCandle, ...] | list[NormalizedCandle]],
        contract_rules: dict[str, FuturesContractRules] | None = None,
        higher_timeframe_candles: dict[
            str, dict[int, tuple[NormalizedCandle, ...] | list[NormalizedCandle]]
        ] | None = None,
    ) -> BacktestResult:
        """Run manual symbols or historical scanner replay through one simulator."""
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self._run_portfolio(
                request, candles_by_symbol, contract_rules or {},
                higher_timeframe_candles or {},
            )

    def _run_portfolio(
        self,
        request: BacktestPortfolioRequest,
        candles_by_symbol: dict[str, tuple[NormalizedCandle, ...] | list[NormalizedCandle]],
        contract_rules: dict[str, FuturesContractRules],
        higher_timeframe_candles: dict[
            str, dict[int, tuple[NormalizedCandle, ...] | list[NormalizedCandle]]
        ],
    ) -> BacktestResult:
        self._registry.validate_configuration(
            request.strategy_type_id, request.configuration
        )
        metadata = self._registry.get(request.strategy_type_id)
        if not metadata.supports_backtesting:
            raise ValueError("Strategy is not ready for backtesting.")
        if request.timeframe_minutes not in metadata.supported_timeframes:
            raise ValueError("Requested timeframe is not supported by the strategy.")

        series: dict[str, tuple[NormalizedCandle, ...]] = {}
        for symbol in request.symbols:
            ordered = tuple(sorted(candles_by_symbol.get(symbol, ()), key=lambda item: item.opened_at))
            if not ordered:
                raise ValueError(f"Missing historical data for {symbol}.")
            if any(not candle.closed for candle in ordered):
                raise ValueError("Backtest accepts completed candles only.")
            if any(
                current.opened_at <= previous.opened_at
                for previous, current in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("Backtest candles must have unique increasing timestamps.")
            series[symbol] = ordered

        evaluator = self._registry.evaluator(request.strategy_type_id)
        scanner = None
        if request.mode == "historical_scanner":
            try:
                scanner = self._registry.scanner(request.strategy_type_id)
            except LookupError as error:
                raise ValueError(
                    "Historical scanner mode requires a registered scanner."
                ) from error

        expected_interval_seconds = request.timeframe_minutes * 60
        for symbol, candles in series.items():
            if any(
                int((current.opened_at - previous.opened_at).total_seconds())
                != expected_interval_seconds
                for previous, current in zip(candles, candles[1:], strict=False)
            ):
                raise ValueError(f"Historical candles contain a timeframe gap for {symbol}.")
            rules = contract_rules.get(symbol)
            if rules is not None and request.settings.leverage > rules.maximum_leverage:
                raise ValueError(
                    f"Requested leverage exceeds the contract maximum for {symbol}."
                )

        all_open_times = sorted(
            {
                candle.opened_at
                for candles in series.values()
                for candle in candles
                if request.start <= candle.closed_at <= request.end
            }
        )
        if not all_open_times:
            raise ValueError("No completed candles overlap the requested period.")

        cash = request.settings.initial_balance
        peak_equity = cash
        pending: dict[str, _PortfolioOrder] = {}
        positions: dict[str, _PortfolioPosition] = {}
        last_exit_index: dict[str, int] = {}
        orders: list[BacktestOrder] = []
        fills: list[BacktestFill] = []
        trades: list[BacktestTrade] = []
        candidates: list[BacktestCandidate] = []
        decisions: list[BacktestDecision] = []
        equity_curve: list[BacktestEquityPoint] = []
        warnings: list[str] = []
        if request.universe_quality != "exact_historical":
            warnings.append(
                "الكون التاريخي تقريبي وقد يعاني من تحيز العملات الباقية حالياً."
            )
        if self._funding_costs.warning_ar:
            warnings.append(self._funding_costs.warning_ar)
        order_counter = 0
        fill_counter = 0
        decision_counter = 0
        active_candle_bars = 0
        last_event_candle_by_symbol: dict[str, NormalizedCandle] = {}

        index_by_symbol_time = {
            symbol: {candle.opened_at: index for index, candle in enumerate(candles)}
            for symbol, candles in series.items()
        }

        for event_index, opened_at in enumerate(all_open_times):
            current_by_symbol = {
                symbol: candles[index_by_symbol_time[symbol][opened_at]]
                for symbol, candles in series.items()
                if opened_at in index_by_symbol_time[symbol]
            }
            last_event_candle_by_symbol.update(current_by_symbol)

            # Protective exits at the open take precedence over averaging orders.
            # A position cannot add DCA exposure after price has already gapped
            # through its market stop.
            for symbol in list(positions):
                candle = current_by_symbol.get(symbol)
                position = positions[symbol]
                if candle is None or candle.opened_at < position.exit_eligible_from:
                    continue
                match = (
                    ("time_exit", candle.open, False)
                    if position.time_exit_pending
                    else self._portfolio_exit_match(
                        position,
                        candle,
                        request.settings.ambiguity_policy,
                        stop_order_type=request.execution.stop_loss_order_type,
                        lower_timeframe_candles=self._lower_timeframe_slice(
                            higher_timeframe_candles.get(symbol, {}),
                            request.timeframe_minutes,
                            candle,
                        ),
                    )
                )
                if match is None or match[1] != candle.open:
                    continue
                position.bars_held += 1
                reason, trigger_price, ambiguous = match
                order_counter, fill_counter, cash = self._close_portfolio_position(
                    request, position, candle, reason, trigger_price, ambiguous,
                    contract_rules.get(symbol), orders, fills, trades,
                    order_counter, fill_counter, cash,
                )
                positions.pop(symbol)
                last_exit_index[symbol] = event_index
                for pending_id in [
                    key for key, value in pending.items()
                    if orders[value.log_index].symbol == symbol
                ]:
                    state = pending.pop(pending_id)
                    orders[state.log_index] = orders[state.log_index].model_copy(
                        update={"status": "canceled"}
                    )

            # Orders submitted after a prior close can first interact with this candle.
            for order_id in list(pending):
                state = pending[order_id]
                order = orders[state.log_index]
                candle = current_by_symbol.get(order.symbol)
                if candle is None or candle.opened_at < order.eligible_from:
                    continue
                elapsed = event_index - state.submitted_index
                if order.expires_after_candle is not None and elapsed > order.expires_after_candle:
                    orders[state.log_index] = order.model_copy(update={"status": "expired"})
                    del pending[order_id]
                    continue
                fill_match = self._entry_fill_price(order, candle, request.settings)
                if fill_match is None:
                    continue
                fill_price, filled_at_open = fill_match
                rules = contract_rules.get(order.symbol)
                multiplier = rules.contract_multiplier if rules else Decimal("1")
                fill_price = self._round_execution_price(
                    fill_price, rules, order.direction, entering=True
                )
                affordable_quantity = (
                    state.margin * Decimal(request.settings.leverage)
                    / (fill_price * multiplier)
                )
                quantity = min(
                    self._round_quantity(order.quantity, rules),
                    self._round_quantity(affordable_quantity, rules),
                )
                rejection = self._quantity_rejection(quantity, fill_price, rules)
                if (
                    rejection is None
                    and request.settings.maximum_volume_participation_percentage is not None
                    and quantity
                    > candle.volume
                    * request.settings.maximum_volume_participation_percentage
                    / HUNDRED
                ):
                    rejection = "maximum_volume_participation"
                if rejection is not None:
                    orders[state.log_index] = order.model_copy(
                        update={"status": "rejected", "quantity": quantity, "rejection_reason": rejection}
                    )
                    del pending[order_id]
                    continue
                maker = order.order_type == "limit" and fill_price == order.requested_price
                fee_rate = request.settings.maker_fee_rate if maker else request.settings.taker_fee_rate
                notional = fill_price * quantity * multiplier
                actual_margin = notional / Decimal(request.settings.leverage)
                fee = notional * fee_rate
                if cash < actual_margin + fee:
                    orders[state.log_index] = order.model_copy(
                        update={"status": "rejected", "rejection_reason": "insufficient_available_balance"}
                    )
                    del pending[order_id]
                    continue
                cash -= actual_margin + fee
                fill_counter += 1
                fill = BacktestFill(
                    fill_id=f"fill-{fill_counter}",
                    order_id=order.order_id,
                    symbol=order.symbol,
                    role=order.role,
                    filled_at=candle.opened_at if filled_at_open else candle.closed_at,
                    price=fill_price,
                    quantity=quantity,
                    fee=fee,
                    slippage_amount=(
                        abs(
                            fill_price
                            - (candle.open if order.order_type == "market" else fill_price)
                        )
                        * quantity
                        * multiplier
                    ),
                    maker=maker,
                )
                fills.append(fill)
                orders[state.log_index] = order.model_copy(update={"status": "filled", "quantity": quantity})
                del pending[order_id]
                position = positions.get(order.symbol)
                if position is None:
                    stop_loss = state.request.stop_loss_price or self._percentage_level(
                        fill_price,
                        request.execution.stop_loss_percentage or request.settings.default_stop_loss_percentage,
                        state.request.direction,
                        favorable=False,
                    )
                    take_profit = state.request.take_profit_price
                    target_percentage: Decimal | None = None
                    if request.execution.take_profit_percentage is not None or take_profit is None:
                        target_percentage = (
                            request.execution.take_profit_percentage
                            or request.settings.default_take_profit_percentage
                        )
                        take_profit = self._percentage_level(
                            fill_price,
                            target_percentage,
                            state.request.direction,
                            favorable=True,
                        )
                    position = _PortfolioPosition(
                        symbol=order.symbol,
                        direction=order.direction,
                        signal_at=order.submitted_at,
                        entered_at=fill.filled_at,
                        entry_explanation_ar="تم تنفيذ الإشارة بعد إغلاق الشمعة وعلى أول سعر مؤهل لاحق.",
                        fills=[fill],
                        allocated_margin=actual_margin,
                        entry_fees=fee,
                        average_entry=fill_price,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        initial_take_profit=take_profit,
                        take_profit_percentage=target_percentage,
                        exit_eligible_from=(
                            candle.opened_at if filled_at_open else candle.closed_at
                        ),
                    )
                    positions[order.symbol] = position
                    decision_counter += 1
                    decisions.append(BacktestDecision(
                        decision_id=f"decision-{decision_counter}", occurred_at=fill.filled_at,
                        symbol=order.symbol, event="entered", qualified=True, selected=True,
                        reason_codes=("order_filled",), explanation_ar=position.entry_explanation_ar,
                        available_candle_count=index_by_symbol_time[order.symbol][opened_at] + 1,
                    ))
                    self._submit_dca_orders(
                        request, position, state, event_index, candle, rules,
                        orders, pending, order_counter,
                    )
                    order_counter = len(orders)
                else:
                    old_notional = position.average_entry * sum(item.quantity for item in position.fills)
                    new_notional = fill.price * fill.quantity
                    position.fills.append(fill)
                    position.average_entry = (old_notional + new_notional) / sum(item.quantity for item in position.fills)
                    position.allocated_margin += actual_margin
                    position.entry_fees += fee
                    if (
                        request.execution.recalculate_target_after_dca
                        and position.take_profit_percentage is not None
                    ):
                        position.take_profit = self._percentage_level(
                            position.average_entry, position.take_profit_percentage,
                            position.direction, favorable=True,
                        )

            # Existing positions now interact with the candle's open/high/low.
            for symbol in list(positions):
                candle = current_by_symbol.get(symbol)
                if candle is None:
                    continue
                position = positions[symbol]
                if candle.opened_at < position.exit_eligible_from:
                    continue
                position.bars_held += 1
                match = (
                    ("time_exit", candle.open, False)
                    if position.time_exit_pending
                    else self._portfolio_exit_match(
                        position,
                        candle,
                        request.settings.ambiguity_policy,
                        stop_order_type=request.execution.stop_loss_order_type,
                        lower_timeframe_candles=self._lower_timeframe_slice(
                            higher_timeframe_candles.get(symbol, {}),
                            request.timeframe_minutes,
                            candle,
                        ),
                    )
                )
                if match is not None:
                    reason, trigger_price, ambiguous = match
                    order_counter, fill_counter, cash = self._close_portfolio_position(
                        request, position, candle, reason, trigger_price, ambiguous,
                        contract_rules.get(symbol), orders, fills, trades,
                        order_counter, fill_counter, cash,
                    )
                    positions.pop(symbol)
                    last_exit_index[symbol] = event_index
                    for pending_id in [key for key, value in pending.items() if orders[value.log_index].symbol == symbol]:
                        state = pending.pop(pending_id)
                        orders[state.log_index] = orders[state.log_index].model_copy(update={"status": "canceled"})
                elif (
                    request.execution.time_exit_candles is not None
                    and position.bars_held >= request.execution.time_exit_candles
                ):
                    # The rule becomes known only after this candle; execution starts next open.
                    position.time_exit_pending = True

            # Close-time scanner and strategy evaluation. Nothing created here can fill now.
            evaluations: list[tuple[int, str, Any, Any, int, dict[str, Any], tuple[str, ...], str]] = []
            if event_index % request.scan_frequency_candles == 0:
                for symbol in sorted(current_by_symbol):
                    candle = current_by_symbol[symbol]
                    if not (request.start <= candle.closed_at <= request.end):
                        continue
                    history = tuple(item for item in series[symbol] if item.closed_at <= candle.closed_at)
                    context = StrategyEvaluationContext(
                        symbol=symbol, evaluated_at=candle.closed_at,
                        timeframe_minutes=request.timeframe_minutes, candles=history,
                        higher_timeframe_candles={
                            timeframe: tuple(
                                item for item in values
                                if item.closed and item.closed_at <= candle.closed_at
                            )
                            for timeframe, values in higher_timeframe_candles.get(symbol, {}).items()
                        },
                        last_price=candle.close, mark_price=candle.close,
                        best_bid=candle.close, best_ask=candle.close,
                        market_data_state="fresh", reconciliation_ready=True,
                        emergency_stop=False,
                    )
                    result = evaluator.evaluate(context, request.configuration | request.parameter_overrides)
                    score = int(result.analysis.get("score", 0)) if isinstance(result.analysis, dict) else 0
                    qualified = result.eligible
                    factors = dict(result.analysis)
                    reason_codes = tuple(result.reason_codes)
                    explanation = result.explanation_ar
                    if scanner is not None:
                        scan_result = scanner.scan_candidate(
                            context, request.configuration | request.parameter_overrides,
                            minimum_backtest_candles=metadata.minimum_backtest_candles,
                        )
                        score = scan_result.score
                        factors = dict(scan_result.metrics)
                        reason_codes = tuple(scan_result.reason_codes)
                        explanation = scan_result.explanation_ar
                        qualified = scan_result.eligible_now
                    if qualified and not result.eligible:
                        rejection = "entry_trigger_not_met"
                    else:
                        rejection = None
                    evaluations.append((score, symbol, result, qualified, len(history), factors, reason_codes, explanation if rejection is None else f"{explanation} لم يتحقق محفز الدخول بعد."))

            evaluations.sort(key=lambda item: (-item[0], item[1]))
            qualified_rank = 0
            for rank, (score, symbol, result, qualified, history_count, factors, reason_codes, explanation) in enumerate(evaluations, start=1):
                if qualified:
                    qualified_rank += 1
                selected = False
                rejection: str | None = None
                if not qualified:
                    rejection = "scanner_conditions_failed" if request.mode == "historical_scanner" else "entry_conditions_failed"
                elif not result.eligible or result.trade_request is None:
                    rejection = "entry_trigger_not_met"
                elif symbol in positions or any(orders[state.log_index].symbol == symbol for state in pending.values()):
                    rejection = "existing_symbol_exposure"
                elif event_index - last_exit_index.get(symbol, -10**9) <= request.execution.cooldown_candles:
                    rejection = "cooldown_active"
                elif len(positions) + self._pending_entry_symbols(pending, orders) >= request.settings.maximum_positions:
                    rejection = "maximum_open_positions"
                elif (
                    request.mode == "historical_scanner"
                    and qualified_rank > request.maximum_candidates
                ):
                    rejection = "candidate_rank_below_limit"
                else:
                    rules = contract_rules.get(symbol)
                    reserved = sum(value.margin for value in pending.values())
                    available_after_reservations = cash - reserved
                    margin = self._position_margin(
                        request, available_after_reservations, result.trade_request
                    )
                    first_allocation = request.execution.dca_allocations[0] / HUNDRED
                    margin *= first_allocation
                    requested_price = result.trade_request.reference_price if result.trade_request.order_type == "limit" else None
                    sizing_price = requested_price or current_by_symbol[symbol].close
                    multiplier = rules.contract_multiplier if rules else Decimal("1")
                    quantity = self._round_quantity(
                        margin * Decimal(request.settings.leverage)
                        / (sizing_price * multiplier),
                        rules,
                    )
                    estimated_fee = margin * Decimal(request.settings.leverage) * request.settings.taker_fee_rate
                    exposure = (
                        sum(item.allocated_margin for item in positions.values())
                        + reserved
                        + margin
                    )
                    exposure_cap = (
                        request.settings.initial_balance
                        * request.settings.maximum_allocation_percentage
                        / HUNDRED
                    )
                    if exposure > exposure_cap:
                        rejection = "portfolio_exposure_limit"
                    elif available_after_reservations < margin + estimated_fee:
                        rejection = "insufficient_available_balance"
                    else:
                        order_counter += 1
                        order_id = f"order-{order_counter}"
                        order = BacktestOrder(
                            order_id=order_id, symbol=symbol, role="entry",
                            direction=result.trade_request.direction,
                            order_type=result.trade_request.order_type,
                            submitted_at=current_by_symbol[symbol].closed_at,
                            eligible_from=self._next_open(series[symbol], current_by_symbol[symbol].opened_at),
                            requested_price=self._round_price(requested_price, rules, result.trade_request.direction) if requested_price else None,
                            quantity=quantity, status="submitted",
                            expires_after_candle=request.execution.entry_expiration_candles,
                        )
                        orders.append(order)
                        pending[order_id] = _PortfolioOrder(
                            log_index=len(orders) - 1, submitted_index=event_index,
                            margin=margin, allocation_percentage=request.execution.dca_allocations[0],
                            request=result.trade_request,
                        )
                        selected = True
                candidates.append(BacktestCandidate(
                    occurred_at=current_by_symbol[symbol].closed_at, symbol=symbol,
                    score=score, rank=rank, qualified=qualified, selected=selected,
                    factor_values=factors, reason_codes=reason_codes,
                    explanation_ar=explanation, rejection_reason=rejection,
                ))
                decision_counter += 1
                decisions.append(BacktestDecision(
                    decision_id=f"decision-{decision_counter}",
                    occurred_at=current_by_symbol[symbol].closed_at, symbol=symbol,
                    event="selected" if selected else "rejected" if rejection else "evaluated",
                    qualified=qualified, selected=selected, reason_codes=reason_codes,
                    explanation_ar=explanation if selected or rejection is None else f"{explanation} سبب عدم الاختيار: {rejection}.",
                    available_candle_count=history_count,
                ))

            invested = sum(position.allocated_margin for position in positions.values())
            equity = cash + invested
            for symbol, position in positions.items():
                candle = current_by_symbol.get(symbol)
                if candle is not None:
                    quantity = sum(item.quantity for item in position.fills)
                    multiplier = (
                        contract_rules[symbol].contract_multiplier
                        if symbol in contract_rules else Decimal("1")
                    )
                    gross = (
                        (candle.close - position.average_entry) * quantity * multiplier
                        if position.direction == "long"
                        else (position.average_entry - candle.close) * quantity * multiplier
                    )
                    equity += (
                        gross
                        - candle.close * quantity * multiplier
                        * request.settings.taker_fee_rate
                    )
            peak_equity = max(peak_equity, equity)
            if request.start <= max(item.closed_at for item in current_by_symbol.values()) <= request.end:
                active_candle_bars += len(positions)
                equity_curve.append(BacktestEquityPoint(
                    occurred_at=max(item.closed_at for item in current_by_symbol.values()),
                    equity=equity, drawdown_percentage=self._drawdown(peak_equity, equity),
                    cash=cash, invested_capital=invested,
                ))

        # Expire pending entries and close remaining positions at the last available close.
        for state in pending.values():
            orders[state.log_index] = orders[state.log_index].model_copy(update={"status": "expired"})
        for symbol, position in list(positions.items()):
            candle = last_event_candle_by_symbol[symbol]
            order_counter, fill_counter, cash = self._close_portfolio_position(
                request, position, candle, "end_of_data", candle.close, False,
                contract_rules.get(symbol), orders, fills, trades,
                order_counter, fill_counter, cash,
            )

        if equity_curve:
            peak_equity = max(peak_equity, cash)
            equity_curve[-1] = equity_curve[-1].model_copy(update={
                "equity": cash, "cash": cash, "invested_capital": ZERO,
                "drawdown_percentage": self._drawdown(peak_equity, cash),
            })
        metrics = self._portfolio_metrics(
            request.settings.initial_balance, cash, trades, equity_curve,
            fills, active_candle_bars, len(all_open_times) * request.settings.maximum_positions,
        )
        if metrics.ambiguous_trades:
            warnings.append(
                f"سُجلت {metrics.ambiguous_trades} صفقة ذات ترتيب وقف/هدف غامض داخل الشمعة."
            )
        if (
            metrics.ambiguous_trades
            and request.settings.ambiguity_policy == "lower_timeframe"
        ):
            warnings.append(
                "لم تتوفر بيانات إطار أدنى لحسم كل الحالات؛ استُخدم الترتيب المحافظ."
            )
        spec = BacktestSpec(
            strategy_type_id=request.strategy_type_id,
            symbol=request.symbols[0],
            timeframe_minutes=request.timeframe_minutes,
            configuration=request.configuration | request.parameter_overrides,
            settings=request.settings,
        )
        return BacktestResult(
            spec=spec, started_at=all_open_times[0],
            ended_at=max(candle.closed_at for values in series.values() for candle in values if candle.opened_at in set(all_open_times)),
            candle_count=sum(
                1 for values in series.values() for candle in values
                if request.start <= candle.closed_at <= request.end
            ),
            trades=tuple(trades), equity_curve=tuple(equity_curve), metrics=metrics,
            assessment=self._assessment(metrics, request.settings.minimum_trades_for_assessment),
            warnings=tuple(dict.fromkeys(warnings)), portfolio_request=request,
            candidates=tuple(candidates), decisions=tuple(decisions),
            orders=tuple(orders), fills=tuple(fills),
        )

    @staticmethod
    def _next_open(candles: tuple[NormalizedCandle, ...], opened_at: datetime) -> datetime:
        for candle in candles:
            if candle.opened_at > opened_at:
                return candle.opened_at
        current = next(candle for candle in candles if candle.opened_at == opened_at)
        return current.closed_at

    @staticmethod
    def _pending_entry_symbols(
        pending: dict[str, _PortfolioOrder], orders: list[BacktestOrder]
    ) -> int:
        return len(
            {
                orders[state.log_index].symbol
                for state in pending.values()
                if orders[state.log_index].role == "entry"
            }
        )

    @classmethod
    def _entry_fill_price(
        cls,
        order: BacktestOrder,
        candle: NormalizedCandle,
        settings: Any,
    ) -> tuple[Decimal, bool] | None:
        if order.order_type == "market":
            return (
                cls._adverse_price(
                    order.direction, candle.open,
                    settings.slippage_basis_points
                    + settings.spread_basis_points / Decimal("2"),
                    entering=True,
                ),
                True,
            )
        limit = order.requested_price
        if limit is None:
            return None
        if order.direction == "long":
            if candle.open <= limit:
                return candle.open, True
            return (limit, False) if candle.low <= limit else None
        if candle.open >= limit:
            return candle.open, True
        return (limit, False) if candle.high >= limit else None

    @staticmethod
    def _round_quantity(
        quantity: Decimal, rules: FuturesContractRules | None
    ) -> Decimal:
        if rules is None:
            return quantity
        return (quantity / rules.quantity_step).to_integral_value(
            rounding=ROUND_DOWN
        ) * rules.quantity_step

    @staticmethod
    def _round_price(
        price: Decimal | None,
        rules: FuturesContractRules | None,
        direction: str,
    ) -> Decimal | None:
        if price is None or rules is None:
            return price
        rounding = ROUND_DOWN if direction == "long" else ROUND_UP
        return (price / rules.price_step).to_integral_value(rounding=rounding) * rules.price_step

    @staticmethod
    def _round_execution_price(
        price: Decimal,
        rules: FuturesContractRules | None,
        direction: str,
        *,
        entering: bool,
    ) -> Decimal:
        if rules is None:
            return price
        increases = (direction == "long" and entering) or (
            direction == "short" and not entering
        )
        rounding = ROUND_UP if increases else ROUND_DOWN
        return (
            (price / rules.price_step).to_integral_value(rounding=rounding)
            * rules.price_step
        )

    @staticmethod
    def _quantity_rejection(
        quantity: Decimal,
        price: Decimal,
        rules: FuturesContractRules | None,
    ) -> str | None:
        if quantity <= ZERO:
            return "rounded_quantity_zero"
        if rules is None:
            return None
        if not rules.active or rules.in_delisting:
            return "symbol_not_trading"
        if quantity < rules.minimum_quantity:
            return "minimum_quantity"
        if rules.maximum_quantity is not None and quantity > rules.maximum_quantity:
            return "maximum_quantity"
        notional = quantity * price * rules.contract_multiplier
        if notional < rules.minimum_notional:
            return "minimum_notional"
        return None

    @staticmethod
    def _position_margin(
        request: BacktestPortfolioRequest,
        available_cash: Decimal,
        trade_request: StrategyTradeRequest,
    ) -> Decimal:
        settings = request.settings
        if settings.position_sizing_mode == "percentage_available":
            margin = available_cash * settings.position_size_percentage / HUNDRED
        elif settings.position_sizing_mode == "percentage_starting":
            margin = settings.initial_balance * settings.position_size_percentage / HUNDRED
        elif settings.position_sizing_mode == "risk_based":
            stop = trade_request.stop_loss_price
            if stop is not None:
                distance_fraction = (
                    abs(trade_request.reference_price - stop)
                    / trade_request.reference_price
                )
            elif request.execution.stop_loss_percentage is not None:
                distance_fraction = request.execution.stop_loss_percentage / HUNDRED
            else:
                raise ValueError("Risk-based sizing requires a deterministic stop loss.")
            if distance_fraction <= ZERO:
                raise ValueError("Risk-based sizing requires non-zero entry-to-stop distance.")
            risk_capital = settings.initial_balance * settings.risk_percentage / HUNDRED
            margin = risk_capital / distance_fraction / Decimal(settings.leverage)
        else:
            margin = settings.margin_per_trade
        allocation_cap = settings.initial_balance * settings.maximum_allocation_percentage / HUNDRED
        return min(margin, allocation_cap)

    def _submit_dca_orders(
        self,
        request: BacktestPortfolioRequest,
        position: _PortfolioPosition,
        initial_state: _PortfolioOrder,
        event_index: int,
        candle: NormalizedCandle,
        rules: FuturesContractRules | None,
        orders: list[BacktestOrder],
        pending: dict[str, _PortfolioOrder],
        order_counter: int,
    ) -> None:
        if not request.execution.dca_enabled:
            return
        total_margin = initial_state.margin / (
            initial_state.allocation_percentage / HUNDRED
        )
        for level, allocation in enumerate(
            request.execution.dca_allocations[1:], start=1
        ):
            distance = request.execution.dca_spacing_percentage * Decimal(level) / HUNDRED
            if position.direction == "long":
                price = position.average_entry * (Decimal("1") - distance)
            else:
                price = position.average_entry * (Decimal("1") + distance)
            price = self._round_price(price, rules, position.direction) or price
            margin = total_margin * allocation / HUNDRED
            quantity = self._round_quantity(
                margin * Decimal(request.settings.leverage)
                / (price * (rules.contract_multiplier if rules else Decimal("1"))),
                rules,
            )
            order_counter += 1
            order_id = f"order-{order_counter}"
            order = BacktestOrder(
                order_id=order_id, symbol=position.symbol, role="dca",
                direction=position.direction, order_type="limit",
                submitted_at=candle.opened_at,
                eligible_from=candle.closed_at,
                requested_price=price, quantity=quantity, status="submitted",
                expires_after_candle=request.execution.entry_expiration_candles,
            )
            # A DCA created after an open fill cannot inspect this candle's earlier low/high.
            orders.append(order)
            pending[order_id] = _PortfolioOrder(
                log_index=len(orders) - 1, submitted_index=event_index,
                margin=margin, allocation_percentage=allocation,
                request=initial_state.request,
            )

    @staticmethod
    def _portfolio_exit_match(
        position: _PortfolioPosition,
        candle: NormalizedCandle,
        policy: str,
        *,
        stop_order_type: str = "market",
        lower_timeframe_candles: tuple[NormalizedCandle, ...] = (),
    ) -> tuple[str, Decimal, bool] | None:
        stop = position.stop_loss
        target = position.take_profit
        if position.direction == "long":
            gap_stop = stop is not None and candle.open <= stop
            gap_target = target is not None and candle.open >= target
            stop_hit = stop is not None and candle.low <= stop
            target_hit = target is not None and candle.high >= target
        else:
            gap_stop = stop is not None and candle.open >= stop
            gap_target = target is not None and candle.open <= target
            stop_hit = stop is not None and candle.high >= stop
            target_hit = target is not None and candle.low <= target
        if gap_stop:
            if stop_order_type == "limit":
                # A stop-limit beyond the market is not guaranteed to fill.
                # It fills only if this candle later trades back to its limit.
                returned_to_limit = (
                    stop is not None
                    and (
                        (position.direction == "long" and candle.high >= stop)
                        or (position.direction == "short" and candle.low <= stop)
                    )
                )
                return ("stop_loss", stop, bool(target_hit)) if returned_to_limit else None
            return "stop_loss", candle.open, bool(target_hit)
        if gap_target:
            return "take_profit", candle.open, bool(stop_hit)
        if stop_hit and target_hit:
            if policy == "lower_timeframe" and lower_timeframe_candles:
                for lower_candle in lower_timeframe_candles:
                    resolved = BacktestEngine._portfolio_exit_match(
                        position,
                        lower_candle,
                        "conservative",
                        stop_order_type=stop_order_type,
                    )
                    if resolved is not None:
                        return resolved
            if policy == "optimistic":
                return "take_profit", target, True
            return "stop_loss", stop, True
        if stop_hit:
            return "stop_loss", stop, False
        if target_hit:
            return "take_profit", target, False
        return None

    @staticmethod
    def _lower_timeframe_slice(
        by_timeframe: dict[int, tuple[NormalizedCandle, ...] | list[NormalizedCandle]],
        signal_timeframe_minutes: int,
        candle: NormalizedCandle,
    ) -> tuple[NormalizedCandle, ...]:
        return tuple(
            sorted(
                (
                    item
                    for timeframe, values in by_timeframe.items()
                    if timeframe < signal_timeframe_minutes
                    for item in values
                    if item.closed
                    and candle.opened_at <= item.opened_at
                    and item.closed_at <= candle.closed_at
                ),
                key=lambda item: item.opened_at,
            )
        )

    def _close_portfolio_position(
        self,
        request: BacktestPortfolioRequest,
        position: _PortfolioPosition,
        candle: NormalizedCandle,
        reason: str,
        trigger_price: Decimal,
        ambiguous: bool,
        rules: FuturesContractRules | None,
        orders: list[BacktestOrder],
        fills: list[BacktestFill],
        trades: list[BacktestTrade],
        order_counter: int,
        fill_counter: int,
        cash: Decimal,
    ) -> tuple[int, int, Decimal]:
        quantity = sum(item.quantity for item in position.fills)
        requested_type = (
            request.execution.take_profit_order_type
            if reason == "take_profit"
            else request.execution.stop_loss_order_type
            if reason == "stop_loss"
            else "market"
        )
        filled_at_open = trigger_price == candle.open
        market_execution = requested_type == "market"
        exit_price = (
            self._adverse_price(
                position.direction, trigger_price,
                request.settings.slippage_basis_points
                + request.settings.spread_basis_points / Decimal("2"),
                entering=False,
            )
            if market_execution
            else trigger_price
        )
        exit_price = self._round_execution_price(
            exit_price, rules, position.direction, entering=False
        )
        order_counter += 1
        order_id = f"order-{order_counter}"
        role = "take_profit" if reason == "take_profit" else "stop_loss" if reason == "stop_loss" else "time_exit"
        filled_at = candle.opened_at if filled_at_open else candle.closed_at
        orders.append(BacktestOrder(
            order_id=order_id, symbol=position.symbol, role=role,
            direction=position.direction, order_type=requested_type,
            submitted_at=filled_at, eligible_from=filled_at,
            requested_price=None if market_execution else trigger_price,
            quantity=quantity, status="filled",
        ))
        multiplier = rules.contract_multiplier if rules else Decimal("1")
        exit_notional = exit_price * quantity * multiplier
        fee_rate = (
            request.settings.taker_fee_rate
            if market_execution or filled_at_open
            else request.settings.maker_fee_rate
        )
        exit_fee = exit_notional * fee_rate
        fill_counter += 1
        exit_fill = BacktestFill(
            fill_id=f"fill-{fill_counter}", order_id=order_id,
            symbol=position.symbol, role=role, filled_at=filled_at,
            price=exit_price, quantity=quantity, fee=exit_fee,
            slippage_amount=abs(exit_price - trigger_price) * quantity * multiplier,
            maker=not market_execution and not filled_at_open,
        )
        fills.append(exit_fill)
        gross = (
            (exit_price - position.average_entry) * quantity * multiplier
            if position.direction == "long"
            else (position.average_entry - exit_price) * quantity * multiplier
        )
        funding = self._funding_costs.cost(
            symbol=position.symbol, direction=position.direction,
            notional=position.average_entry * quantity * multiplier,
            entered_at=position.entered_at, exited_at=filled_at,
        )
        fees = position.entry_fees + exit_fee
        net = gross - fees - funding
        risk_amount = (
            abs(position.average_entry - position.stop_loss) * quantity * multiplier
            if position.stop_loss is not None else ZERO
        )
        trades.append(BacktestTrade(
            trade_number=len(trades) + 1, symbol=position.symbol,
            direction=position.direction, signal_at=position.signal_at,
            entered_at=position.entered_at, exited_at=filled_at,
            entry_price=position.average_entry, average_entry_price=position.average_entry,
            exit_price=exit_price, quantity=quantity,
            allocated_margin=position.allocated_margin,
            leverage=request.settings.leverage, gross_pnl=gross,
            fees=fees, funding=funding, net_pnl=net,
            return_on_margin_percentage=net / position.allocated_margin * HUNDRED,
            exit_reason=reason,
            bars_held=max(1, position.bars_held), entry_fills=tuple(position.fills),
            stop_loss_price=position.stop_loss, take_profit_price=position.take_profit,
            result_r=net / risk_amount if risk_amount > ZERO else None,
            slippage=sum((item.slippage_amount for item in position.fills), ZERO) + exit_fill.slippage_amount,
            ambiguous=ambiguous, entry_explanation_ar=position.entry_explanation_ar,
        ))
        return order_counter, fill_counter, cash + position.allocated_margin + gross - exit_fee - funding

    @staticmethod
    def _portfolio_metrics(
        starting_balance: Decimal,
        ending_balance: Decimal,
        trades: list[BacktestTrade],
        equity_curve: list[BacktestEquityPoint],
        fills: list[BacktestFill],
        active_bars: int,
        possible_bars: int,
    ) -> BacktestMetrics:
        winners = [item for item in trades if item.net_pnl > ZERO]
        losers = [item for item in trades if item.net_pnl < ZERO]
        gross_profit = sum((item.net_pnl for item in winners), ZERO)
        gross_loss = sum((item.net_pnl for item in losers), ZERO)
        gross_pnl = sum((item.gross_pnl for item in trades), ZERO)
        total = len(trades)
        winning_streak = losing_streak = max_winning = max_losing = 0
        for trade in trades:
            if trade.net_pnl > ZERO:
                winning_streak += 1
                losing_streak = 0
            elif trade.net_pnl < ZERO:
                losing_streak += 1
                winning_streak = 0
            else:
                winning_streak = losing_streak = 0
            max_winning = max(max_winning, winning_streak)
            max_losing = max(max_losing, losing_streak)
        r_values = [item.result_r for item in trades if item.result_r is not None]
        holding = [Decimal(str((item.exited_at - item.entered_at).total_seconds())) for item in trades]
        return BacktestMetrics(
            starting_balance=starting_balance, ending_balance=ending_balance,
            ending_equity=ending_balance, net_profit=ending_balance - starting_balance,
            return_percentage=(ending_balance - starting_balance) / starting_balance * HUNDRED,
            gross_return_percentage=gross_pnl / starting_balance * HUNDRED,
            total_trades=total, winning_trades=len(winners), losing_trades=len(losers),
            win_rate_percentage=Decimal(len(winners)) / Decimal(total) * HUNDRED if total else ZERO,
            gross_profit=gross_profit, gross_loss=gross_loss,
            fees=sum((item.fees for item in trades), ZERO),
            total_fees=sum((item.fees for item in trades), ZERO),
            funding=sum((item.funding for item in trades), ZERO),
            average_win=gross_profit / Decimal(len(winners)) if winners else ZERO,
            average_loss=gross_loss / Decimal(len(losers)) if losers else ZERO,
            profit_factor=gross_profit / abs(gross_loss) if gross_loss < ZERO else None,
            maximum_drawdown_percentage=max((item.drawdown_percentage for item in equity_curve), default=ZERO),
            maximum_losing_streak=max_losing, maximum_winning_streak=max_winning,
            consecutive_losses=max_losing,
            long_net_pnl=sum((item.net_pnl for item in trades if item.direction == "long"), ZERO),
            short_net_pnl=sum((item.net_pnl for item in trades if item.direction == "short"), ZERO),
            largest_winner_share_percentage=max((item.net_pnl for item in winners), default=ZERO) / gross_profit * HUNDRED if gross_profit > ZERO else None,
            expectancy=sum((item.net_pnl for item in trades), ZERO) / Decimal(total) if total else ZERO,
            average_r=sum(r_values, ZERO) / Decimal(len(r_values)) if r_values else None,
            largest_win=max((item.net_pnl for item in trades), default=ZERO),
            largest_loss=min((item.net_pnl for item in trades), default=ZERO),
            total_slippage=sum((item.slippage_amount for item in fills), ZERO),
            average_holding_seconds=sum(holding, ZERO) / Decimal(len(holding)) if holding else ZERO,
            exposure_percentage=Decimal(active_bars) / Decimal(possible_bars) * HUNDRED if possible_bars else ZERO,
            ambiguous_trades=sum(item.ambiguous for item in trades),
        )

    def _run(
        self,
        spec: BacktestSpec,
        candles: tuple[NormalizedCandle, ...] | list[NormalizedCandle],
    ) -> BacktestResult:
        self._registry.validate_configuration(
            spec.strategy_type_id,
            spec.configuration,
        )
        evaluator = self._registry.evaluator(spec.strategy_type_id)
        ordered = tuple(sorted(candles, key=lambda candle: candle.opened_at))
        if not ordered:
            raise ValueError("Backtest requires at least one candle.")
        if any(not candle.closed for candle in ordered):
            raise ValueError("Backtest accepts completed candles only.")
        if any(
            current.opened_at <= previous.opened_at
            for previous, current in zip(ordered, ordered[1:], strict=False)
        ):
            raise ValueError("Backtest candles must have unique increasing timestamps.")

        settings = spec.settings
        balance = settings.initial_balance
        peak_equity = balance
        pending: _PendingSignal | None = None
        position: _OpenPosition | None = None
        trades: list[BacktestTrade] = []
        equity_curve: list[BacktestEquityPoint] = []
        warnings: list[str] = []
        if self._funding_costs.warning_ar:
            warnings.append(self._funding_costs.warning_ar)
        candles_since_last_entry: int | None = None

        for index, candle in enumerate(ordered):
            if pending is not None and position is None:
                position, entry_warning = self._open_position(spec, pending, candle, balance)
                pending = None
                if entry_warning is not None:
                    if entry_warning not in warnings:
                        warnings.append(entry_warning)
                elif position is not None:
                    balance -= position.entry_fee
                    candles_since_last_entry = 0

            if position is not None:
                position.bars_held += 1
                exit_match = self._exit_match(position, candle)
                if exit_match is not None:
                    exit_reason, trigger_price = exit_match
                    trade = self._close_position(
                        spec,
                        position,
                        candle,
                        trigger_price,
                        exit_reason,
                        len(trades) + 1,
                    )
                    balance += trade.gross_pnl - (trade.fees - position.entry_fee) - trade.funding
                    trades.append(trade)
                    position = None
                    candles_since_last_entry = 0
                else:
                    self._ratchet_trailing_stop(position, candle)

            if position is None and index < len(ordered) - 1:
                context = self._evaluation_context(
                    spec,
                    ordered[: index + 1],
                    candle,
                    candles_since_last_entry,
                )
                result = evaluator.evaluate(context, spec.configuration)
                if result.eligible and result.trade_request is not None:
                    pending = _PendingSignal(
                        signal_at=candle.closed_at,
                        request=result.trade_request,
                    )

            if candles_since_last_entry is not None:
                candles_since_last_entry += 1

            equity = balance + self._unrealized_net(position, candle.close, settings.taker_fee_rate)
            peak_equity = max(peak_equity, equity)
            equity_curve.append(
                BacktestEquityPoint(
                    occurred_at=candle.closed_at,
                    equity=equity,
                    drawdown_percentage=self._drawdown(peak_equity, equity),
                )
            )

        if position is not None:
            last = ordered[-1]
            trade = self._close_position(
                spec,
                position,
                last,
                last.close,
                "end_of_data",
                len(trades) + 1,
            )
            balance += trade.gross_pnl - (trade.fees - position.entry_fee) - trade.funding
            trades.append(trade)
            peak_equity = max(peak_equity, balance)
            equity_curve[-1] = BacktestEquityPoint(
                occurred_at=last.closed_at,
                equity=balance,
                drawdown_percentage=self._drawdown(peak_equity, balance),
            )

        metrics = self._metrics(settings.initial_balance, balance, trades, equity_curve)
        assessment = self._assessment(metrics, settings.minimum_trades_for_assessment)
        if pending is not None:
            warnings.append("انتهت البيانات قبل تنفيذ آخر إشارة على شمعة لاحقة.")
        return BacktestResult(
            spec=spec,
            started_at=ordered[0].opened_at,
            ended_at=ordered[-1].closed_at,
            candle_count=len(ordered),
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            metrics=metrics,
            assessment=assessment,
            warnings=tuple(warnings),
        )

    @staticmethod
    def _evaluation_context(
        spec: BacktestSpec,
        candles: tuple[NormalizedCandle, ...],
        current: NormalizedCandle,
        candles_since_last_entry: int | None,
    ) -> StrategyEvaluationContext:
        return StrategyEvaluationContext(
            symbol=spec.symbol,
            evaluated_at=current.closed_at,
            timeframe_minutes=spec.timeframe_minutes,
            candles=candles,
            last_price=current.close,
            mark_price=current.close,
            best_bid=current.close,
            best_ask=current.close,
            market_data_state="fresh",
            reconciliation_ready=True,
            emergency_stop=False,
            candles_since_last_entry=candles_since_last_entry,
        )

    def _open_position(
        self,
        spec: BacktestSpec,
        pending: _PendingSignal,
        candle: NormalizedCandle,
        balance: Decimal,
    ) -> tuple[_OpenPosition | None, str | None]:
        settings = spec.settings
        entry_price = self._adverse_price(
            pending.request.direction,
            candle.open,
            settings.slippage_basis_points + settings.spread_basis_points / Decimal("2"),
            entering=True,
        )
        notional = settings.margin_per_trade * Decimal(settings.leverage)
        quantity = notional / entry_price
        entry_fee = notional * settings.taker_fee_rate
        if balance < settings.margin_per_trade + entry_fee:
            return None, "الرصيد غير كافٍ لتنفيذ إحدى إشارات الاختبار."

        take_profit = pending.request.take_profit_price
        stop_loss = pending.request.stop_loss_price
        if take_profit is None:
            take_profit = self._percentage_level(
                entry_price,
                settings.default_take_profit_percentage,
                pending.request.direction,
                favorable=True,
            )
        if stop_loss is None:
            stop_loss = self._percentage_level(
                entry_price,
                settings.default_stop_loss_percentage,
                pending.request.direction,
                favorable=False,
            )
        trailing_stop = pending.request.trailing_stop_price
        trailing_distance = None
        if trailing_stop is not None:
            trailing_distance = abs(entry_price - trailing_stop)
        return (
            _OpenPosition(
                direction=pending.request.direction,
                signal_at=pending.signal_at,
                entered_at=candle.opened_at,
                entry_price=entry_price,
                quantity=quantity,
                allocated_margin=settings.margin_per_trade,
                leverage=settings.leverage,
                entry_fee=entry_fee,
                take_profit_price=take_profit,
                stop_loss_price=stop_loss,
                trailing_stop_price=trailing_stop,
                trailing_distance=trailing_distance,
            ),
            None,
        )

    @staticmethod
    def _exit_match(
        position: _OpenPosition,
        candle: NormalizedCandle,
    ) -> tuple[str, Decimal] | None:
        stops: list[tuple[str, Decimal]] = []
        if position.stop_loss_price is not None:
            stops.append(("stop_loss", position.stop_loss_price))
        if position.trailing_stop_price is not None:
            stops.append(("trailing_stop", position.trailing_stop_price))

        if position.direction == "long":
            for reason, price in sorted(stops, key=lambda item: item[1], reverse=True):
                if candle.low <= price:
                    return reason, price
            if (
                position.take_profit_price is not None
                and candle.high >= position.take_profit_price
            ):
                return "take_profit", position.take_profit_price
        else:
            for reason, price in sorted(stops, key=lambda item: item[1]):
                if candle.high >= price:
                    return reason, price
            if (
                position.take_profit_price is not None
                and candle.low <= position.take_profit_price
            ):
                return "take_profit", position.take_profit_price
        return None

    @staticmethod
    def _ratchet_trailing_stop(
        position: _OpenPosition,
        candle: NormalizedCandle,
    ) -> None:
        if position.trailing_distance is None or position.trailing_stop_price is None:
            return
        if position.direction == "long":
            candidate = candle.high - position.trailing_distance
            position.trailing_stop_price = max(position.trailing_stop_price, candidate)
        else:
            candidate = candle.low + position.trailing_distance
            position.trailing_stop_price = min(position.trailing_stop_price, candidate)

    def _close_position(
        self,
        spec: BacktestSpec,
        position: _OpenPosition,
        candle: NormalizedCandle,
        trigger_price: Decimal,
        exit_reason: str,
        trade_number: int,
    ) -> BacktestTrade:
        exit_price = self._adverse_price(
            position.direction,
            trigger_price,
            spec.settings.slippage_basis_points
            + spec.settings.spread_basis_points / Decimal("2"),
            entering=False,
        )
        gross_pnl = (
            (exit_price - position.entry_price) * position.quantity
            if position.direction == "long"
            else (position.entry_price - exit_price) * position.quantity
        )
        exit_notional = exit_price * position.quantity
        exit_fee = exit_notional * spec.settings.taker_fee_rate
        funding = self._funding_costs.cost(
            symbol=spec.symbol,
            direction=position.direction,
            notional=position.entry_price * position.quantity,
            entered_at=position.entered_at,
            exited_at=candle.closed_at,
        )
        fees = position.entry_fee + exit_fee
        net_pnl = gross_pnl - fees - funding
        return BacktestTrade(
            trade_number=trade_number,
            direction=position.direction,
            signal_at=position.signal_at,
            entered_at=position.entered_at,
            exited_at=candle.closed_at,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            allocated_margin=position.allocated_margin,
            leverage=position.leverage,
            gross_pnl=gross_pnl,
            fees=fees,
            funding=funding,
            net_pnl=net_pnl,
            return_on_margin_percentage=(net_pnl / position.allocated_margin) * HUNDRED,
            exit_reason=exit_reason,
            bars_held=position.bars_held,
        )

    @staticmethod
    def _adverse_price(
        direction: str,
        price: Decimal,
        basis_points: Decimal,
        *,
        entering: bool,
    ) -> Decimal:
        fraction = basis_points / TEN_THOUSAND
        increases = (direction == "long" and entering) or (
            direction == "short" and not entering
        )
        return price * (Decimal("1") + fraction if increases else Decimal("1") - fraction)

    @staticmethod
    def _percentage_level(
        entry_price: Decimal,
        percentage: Decimal,
        direction: str,
        *,
        favorable: bool,
    ) -> Decimal:
        fraction = percentage / HUNDRED
        increases = (direction == "long" and favorable) or (
            direction == "short" and not favorable
        )
        return entry_price * (Decimal("1") + fraction if increases else Decimal("1") - fraction)

    @staticmethod
    def _unrealized_net(
        position: _OpenPosition | None,
        price: Decimal,
        fee_rate: Decimal,
    ) -> Decimal:
        if position is None:
            return ZERO
        gross = (
            (price - position.entry_price) * position.quantity
            if position.direction == "long"
            else (position.entry_price - price) * position.quantity
        )
        estimated_exit_fee = price * position.quantity * fee_rate
        return gross - estimated_exit_fee

    @staticmethod
    def _drawdown(peak: Decimal, equity: Decimal) -> Decimal:
        if peak <= ZERO or equity >= peak:
            return ZERO
        return ((peak - equity) / peak) * HUNDRED

    @staticmethod
    def _metrics(
        starting_balance: Decimal,
        ending_balance: Decimal,
        trades: list[BacktestTrade],
        equity_curve: list[BacktestEquityPoint],
    ) -> BacktestMetrics:
        winners = [trade for trade in trades if trade.net_pnl > ZERO]
        losers = [trade for trade in trades if trade.net_pnl < ZERO]
        gross_profit = sum((trade.net_pnl for trade in winners), ZERO)
        gross_loss = sum((trade.net_pnl for trade in losers), ZERO)
        total = len(trades)
        profit_factor = (
            gross_profit / abs(gross_loss)
            if gross_loss < ZERO
            else None
        )
        largest_winner_share = (
            max(trade.net_pnl for trade in winners) / gross_profit * HUNDRED
            if winners and gross_profit > ZERO
            else None
        )
        losing_streak = 0
        maximum_losing_streak = 0
        for trade in trades:
            if trade.net_pnl < ZERO:
                losing_streak += 1
                maximum_losing_streak = max(maximum_losing_streak, losing_streak)
            else:
                losing_streak = 0
        return BacktestMetrics(
            starting_balance=starting_balance,
            ending_balance=ending_balance,
            net_profit=ending_balance - starting_balance,
            return_percentage=((ending_balance - starting_balance) / starting_balance)
            * HUNDRED,
            total_trades=total,
            winning_trades=len(winners),
            losing_trades=len(losers),
            win_rate_percentage=(Decimal(len(winners)) / Decimal(total) * HUNDRED)
            if total
            else ZERO,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            fees=sum((trade.fees for trade in trades), ZERO),
            funding=sum((trade.funding for trade in trades), ZERO),
            average_win=gross_profit / Decimal(len(winners)) if winners else ZERO,
            average_loss=gross_loss / Decimal(len(losers)) if losers else ZERO,
            profit_factor=profit_factor,
            maximum_drawdown_percentage=max(
                (point.drawdown_percentage for point in equity_curve),
                default=ZERO,
            ),
            maximum_losing_streak=maximum_losing_streak,
            long_net_pnl=sum(
                (trade.net_pnl for trade in trades if trade.direction == "long"),
                ZERO,
            ),
            short_net_pnl=sum(
                (trade.net_pnl for trade in trades if trade.direction == "short"),
                ZERO,
            ),
            largest_winner_share_percentage=largest_winner_share,
        )

    @staticmethod
    def _assessment(
        metrics: BacktestMetrics,
        minimum_trades: int,
    ) -> BacktestAssessment:
        if metrics.total_trades < minimum_trades:
            return BacktestAssessment(
                label="insufficient_data",
                score=0,
                summary_ar="النتيجة غير كافية لاتخاذ قرار لأن عدد الصفقات قليل.",
                warnings=("عدد الصفقات أقل من الحد المطلوب للتقييم.",),
            )

        score = 10
        reasons: list[str] = []
        warnings: list[str] = []
        if metrics.net_profit > ZERO:
            score += 30
            reasons.append("صافي النتيجة بعد التكاليف موجب.")
        else:
            warnings.append("صافي النتيجة بعد التكاليف غير موجب.")
        if metrics.profit_factor is not None and metrics.profit_factor >= Decimal("1.3"):
            score += 20
            reasons.append("عامل الربح أعلى من 1.3.")
        elif metrics.profit_factor is None and metrics.gross_loss == ZERO and metrics.gross_profit > ZERO:
            score += 20
            reasons.append("لم تسجل العينة صفقة خاسرة.")
        else:
            warnings.append("عامل الربح لا يوفر هامش أمان كافياً.")
        if metrics.maximum_drawdown_percentage <= Decimal("15"):
            score += 20
            reasons.append("أقصى تراجع ضمن النطاق المحافظ.")
        elif metrics.maximum_drawdown_percentage > Decimal("35"):
            warnings.append("أقصى تراجع مرتفع جداً.")
        if metrics.win_rate_percentage >= Decimal("45"):
            score += 10
            reasons.append("نسبة الفوز لا تقل عن 45%. ")
        if (
            metrics.largest_winner_share_percentage is None
            or metrics.largest_winner_share_percentage <= Decimal("50")
        ):
            score += 10
            reasons.append("النتيجة لا تعتمد على صفقة رابحة واحدة بصورة مفرطة.")
        else:
            warnings.append("نسبة كبيرة من الربح جاءت من صفقة واحدة.")

        score = min(score, 100)
        weak = (
            metrics.net_profit <= ZERO
            or (
                metrics.profit_factor is not None
                and metrics.profit_factor < Decimal("1")
            )
            or metrics.maximum_drawdown_percentage > Decimal("35")
        )
        promising = (
            score >= 70
            and metrics.net_profit > ZERO
            and metrics.maximum_drawdown_percentage <= Decimal("20")
            and (
                metrics.profit_factor is None
                or metrics.profit_factor >= Decimal("1.2")
            )
        )
        label = "weak" if weak else "promising" if promising else "mixed"
        summary = {
            "promising": "النتيجة واعدة ضمن افتراضات الاختبار، لكنها لا تضمن أداءً مستقبلياً.",
            "mixed": "النتيجة مختلطة وتحتاج إلى فترات وإعدادات إضافية قبل التطبيق.",
            "weak": "النتيجة ضعيفة ضمن افتراضات الاختبار ولا تدعم تطبيق الإعداد الحالي.",
        }[label]
        return BacktestAssessment(
            label=label,
            score=score,
            summary_ar=summary,
            reasons=tuple(reasons),
            warnings=tuple(warnings),
        )
