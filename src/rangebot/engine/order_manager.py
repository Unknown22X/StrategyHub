"""Central preview, validation, and submission boundary for futures orders."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from typing import Literal
from uuid import uuid4

from pydantic_core import to_jsonable_python

from rangebot.domain.exchange import ExchangeEntryRequest, ExchangeOperationResult
from rangebot.domain.orders import (
    ExecutionEnvironment,
    FuturesContractRules,
    ManualOrderPreview,
    ManualOrderPreviewRequest,
    ManualOrderSubmissionRequest,
    ManualOrderSubmissionResult,
    OrderAccountContext,
    OrderOrigin,
    OrderSubmissionContext,
    OrderValidationIssue,
)
from rangebot.engine.market_data_manager import MarketDataManager


ContractRulesProvider = Callable[[str, ExecutionEnvironment], FuturesContractRules]
AccountContextProvider = Callable[
    [ExecutionEnvironment, OrderOrigin], OrderAccountContext
]
OrderExecutor = Callable[
    [ExecutionEnvironment, ExchangeEntryRequest], ExchangeOperationResult
]
OwnershipRecorder = Callable[
    [str, str, ExecutionEnvironment, ExchangeEntryRequest, OrderSubmissionContext], None
]


class OrderValidationError(RuntimeError):
    """Raised when an order cannot pass the central validation boundary."""

    def __init__(self, preview: ManualOrderPreview) -> None:
        self.preview = preview
        super().__init__("Manual order failed central validation.")


class StaleOrderPreviewError(RuntimeError):
    """Raised when the account, market, contract, or request changed after preview."""


class OrderManager:
    """The only engine component allowed to turn a manual request into submission."""

    def __init__(
        self,
        *,
        market_data: MarketDataManager,
        contract_rules: ContractRulesProvider,
        account_context: AccountContextProvider,
        executor: OrderExecutor,
        record_ownership: OwnershipRecorder | None = None,
    ) -> None:
        self._market_data = market_data
        self._contract_rules = contract_rules
        self._account_context = account_context
        self._executor = executor
        self._record_ownership = record_ownership

    def preview(
        self,
        request: ManualOrderPreviewRequest,
        *,
        context: OrderSubmissionContext | None = None,
    ) -> ManualOrderPreview:
        submission_context = context or OrderSubmissionContext()
        generated_at = datetime.now(UTC)
        market = self._market_data.snapshot(request.symbol)
        rules = self._contract_rules(request.symbol, request.environment)
        account = self._account_context(request.environment, submission_context.origin)
        if account.environment != request.environment:
            raise ValueError("Account context environment mismatch.")
        if rules.symbol != request.symbol:
            raise ValueError("Contract rules symbol mismatch.")

        issues: list[OrderValidationIssue] = []
        self._validate_authoritative_state(request, rules, account, market, issues)
        if request.environment == "paper" and request.order_type == "limit":
            if request.expires_at is None:
                issues.append(
                    OrderValidationIssue(
                        code="paper_limit_expiry_required",
                        message_ar="أمر Paper Limit يحتاج وقت انتهاء صريحاً.",
                        field="expires_at",
                    )
                )
            elif request.expires_at <= generated_at:
                issues.append(
                    OrderValidationIssue(
                        code="paper_limit_expiry_elapsed",
                        message_ar="وقت انتهاء أمر Paper Limit يجب أن يكون في المستقبل.",
                        field="expires_at",
                    )
                )

        reference_price = self._reference_price(
            request, market.best_bid, market.best_ask, market.last_price
        )
        raw_quantity = self._raw_quantity(request, account, rules, reference_price)
        estimated_quantity = self._round_down(raw_quantity, rules.quantity_step)
        notional = estimated_quantity * rules.contract_multiplier * reference_price
        estimated_margin = notional / Decimal(request.leverage)
        minimum_notional = max(
            rules.minimum_notional,
            rules.minimum_quantity * rules.contract_multiplier * reference_price,
        )
        approximate_minimum_margin = minimum_notional / Decimal(request.leverage)
        behavior = self._liquidity_behavior(
            request,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
        )
        fee_rate = rules.maker_fee_rate if behavior == "maker" else rules.taker_fee_rate
        opening_fee = notional * fee_rate
        limit_distance = (
            abs(request.limit_price - market.last_price)
            / market.last_price
            * Decimal("100")
            if request.limit_price is not None
            else None
        )
        take_profit: Decimal | None = None
        stop_loss: Decimal | None = None
        if estimated_quantity > 0:
            take_profit, stop_loss = self._protection_prices(
                direction=request.direction,
                entry_price=reference_price,
                base_quantity=estimated_quantity * rules.contract_multiplier,
                allocated_margin=estimated_margin,
                entry_fee=opening_fee,
                exit_fee_rate=rules.taker_fee_rate,
                explicit_take_profit=submission_context.take_profit_price,
                explicit_stop_loss=submission_context.stop_loss_price,
            )
        if submission_context.trailing_stop_price is not None:
            if request.order_type != "market":
                issues.append(
                    OrderValidationIssue(
                        code="trailing_stop_market_only",
                        message_ar="وقف التتبع التلقائي مدعوم حالياً لأوامر Market فقط.",
                        field="order_type",
                    )
                )
            elif (
                request.direction == "long"
                and submission_context.trailing_stop_price >= reference_price
            ) or (
                request.direction == "short"
                and submission_context.trailing_stop_price <= reference_price
            ):
                issues.append(
                    OrderValidationIssue(
                        code="invalid_trailing_stop_side",
                        message_ar="سعر وقف التتبع يجب أن يكون أسفل الدخول للشراء وأعلاه للبيع.",
                        field="trailing_stop_price",
                    )
                )
        liquidation = self._estimated_liquidation_price(
            request.direction,
            reference_price,
            request.leverage,
            rules.maintenance_rate,
        )

        self._validate_calculation(
            request=request,
            rules=rules,
            account=account,
            raw_quantity=raw_quantity,
            quantity=estimated_quantity,
            notional=notional,
            margin=estimated_margin,
            opening_fee=opening_fee,
            behavior=behavior,
            issues=issues,
        )

        fingerprint = self._fingerprint(
            request=request,
            context=submission_context,
            rules=rules,
            account=account,
            market_payload={
                "last_price": market.last_price,
                "mark_price": market.mark_price,
                "best_bid": market.best_bid,
                "best_ask": market.best_ask,
                "state": market.state,
                "sequence_gap": market.sequence_gap,
            },
        )
        uses_real_funds = request.environment == "live"
        return ManualOrderPreview(
            request=request,
            generated_at=generated_at,
            last_price=market.last_price,
            mark_price=market.mark_price,
            best_bid=market.best_bid,
            best_ask=market.best_ask,
            market_data_state=market.state,
            market_observed_at=market.observed_at,
            available_balance=account.available_balance,
            contract_multiplier=rules.contract_multiplier,
            quantity_step=rules.quantity_step,
            minimum_quantity=rules.minimum_quantity,
            minimum_notional=minimum_notional,
            approximate_minimum_margin=approximate_minimum_margin,
            maximum_leverage=rules.maximum_leverage,
            estimated_quantity=estimated_quantity,
            estimated_notional=notional,
            estimated_margin=estimated_margin,
            estimated_opening_fee=opening_fee,
            estimated_fee_rate=fee_rate,
            estimated_take_profit_price=take_profit,
            estimated_stop_loss_price=stop_loss,
            estimated_liquidation_price=liquidation,
            reference_price=reference_price,
            limit_distance_percentage=limit_distance,
            estimated_liquidity_behavior=behavior,
            supported_time_in_force=rules.supported_time_in_force,
            validation_issues=tuple(issues),
            can_submit=not issues,
            uses_real_funds=uses_real_funds,
            live_warning_ar=(
                "هذا أمر Live وسيستخدم أموالاً حقيقية." if uses_real_funds else None
            ),
            safety_fingerprint=fingerprint,
        )

    def submit(
        self,
        submission: ManualOrderSubmissionRequest,
        *,
        context: OrderSubmissionContext | None = None,
    ) -> ManualOrderSubmissionResult:
        submission_context = context or OrderSubmissionContext()
        preview = self.preview(submission.request, context=submission_context)
        if preview.safety_fingerprint != submission.preview_fingerprint:
            raise StaleOrderPreviewError(
                "Order preview is stale; generate a new preview."
            )
        if not preview.can_submit:
            raise OrderValidationError(preview)

        client_request_id = str(uuid4())
        request = submission.request
        exchange_request = ExchangeEntryRequest(
            symbol=request.symbol,
            direction=request.direction,
            order_type=request.order_type,
            quantity=preview.estimated_quantity,
            limit_price=request.limit_price,
            client_request_id=client_request_id,
            protections_enabled=not request.reduce_only,
            leverage=request.leverage,
            time_in_force=request.time_in_force,
            expires_at=request.expires_at,
            signal_zone=submission_context.signal_zone,
            signal_symbol=submission_context.signal_symbol,
            take_profit_price=preview.estimated_take_profit_price,
            stop_loss_price=preview.estimated_stop_loss_price,
            trailing_stop_price=submission_context.trailing_stop_price,
            trailing_stop_distance=(
                abs(preview.reference_price - submission_context.trailing_stop_price)
                if submission_context.trailing_stop_price is not None
                else None
            ),
            origin=submission_context.origin,
            reduce_only=request.reduce_only,
            strategy_type_id=submission_context.strategy_type_id,
            cycle_id=submission_context.cycle_id,
            order_role=submission_context.order_role,
            entry_level_id=submission_context.entry_level_id,
            order_generation=submission_context.order_generation,
        )
        result = self._executor(request.environment, exchange_request)
        if result.accepted and result.order_id and self._record_ownership is not None:
            self._record_ownership(
                result.order_id,
                client_request_id,
                request.environment,
                exchange_request,
                submission_context,
            )
        return ManualOrderSubmissionResult(
            accepted=result.accepted,
            environment=request.environment,
            origin=submission_context.origin,
            client_request_id=result.client_request_id,
            order_id=result.order_id,
            message_ar=result.message_ar,
            preview=preview,
        )

    def submit_automatic(
        self,
        request: ManualOrderPreviewRequest,
        *,
        origin: Literal[
            "automatic_strategy", "monitoring_conversion", "legacy_automatic"
        ],
        instance_id: str | None = None,
        run_id: str | None = None,
        signal_zone: str | None = None,
        signal_symbol: str | None = None,
        take_profit_price: Decimal | None = None,
        stop_loss_price: Decimal | None = None,
        trailing_stop_price: Decimal | None = None,
        reduce_only: bool = False,
        strategy_type_id: str | None = None,
        cycle_id: str | None = None,
        order_role: Literal["entry", "take_profit", "stop_loss"] | None = None,
        entry_level_id: str | None = None,
        order_generation: int = 0,
    ) -> ManualOrderSubmissionResult:
        """Generate and revalidate an internal automatic preview before submission."""
        context = OrderSubmissionContext(
            origin=origin,
            instance_id=instance_id,
            run_id=run_id,
            signal_zone=signal_zone,
            signal_symbol=signal_symbol,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            trailing_stop_price=trailing_stop_price,
            strategy_type_id=strategy_type_id,
            cycle_id=cycle_id,
            order_role=order_role,
            entry_level_id=entry_level_id,
            order_generation=order_generation,
        )
        preview = self.preview(request, context=context)
        return self.submit(
            ManualOrderSubmissionRequest(
                request=request,
                preview_fingerprint=preview.safety_fingerprint,
            ),
            context=context,
        )

    @staticmethod
    def _validate_authoritative_state(
        request: ManualOrderPreviewRequest,
        rules: FuturesContractRules,
        account: OrderAccountContext,
        market: object,
        issues: list[OrderValidationIssue],
    ) -> None:
        def add(code, message, field=None):
            if any(issue.code == code and issue.field == field for issue in issues):
                return
            issues.append(
                OrderValidationIssue(code=code, message_ar=message, field=field)
            )

        if not account.account_ready:
            add("account_not_ready", "حساب العقود غير جاهز للتداول.")
        if not account.adapter_mode_matches:
            add(
                "adapter_mode_mismatch",
                "وضع محرك Gate.io لا يطابق بيئة الأمر المطلوبة.",
                "environment",
            )
        if request.environment != "paper" and not account.credentials_configured:
            add("credentials_missing", "بيانات Gate.io غير محفوظة.")
        if not rules.active:
            add("contract_inactive", "العقد غير متاح للتداول حالياً.", "symbol")
        if rules.in_delisting:
            add("contract_delisting", "العقد في مرحلة إلغاء الإدراج.", "symbol")
        if request.leverage > rules.maximum_leverage:
            add(
                "leverage_above_contract_limit",
                "الرافعة المختارة تتجاوز حد العقد.",
                "leverage",
            )
        if not account.one_way_confirmed:
            add("one_way_not_confirmed", "وضع One-way غير مؤكّد بالمصالحة.")
        if not account.daily_risk_allowed:
            risk_messages = {
                "synchronization_incomplete": "مزامنة بيانات المخاطر غير مكتملة.",
                "risk_data_unavailable": "بيانات حقوق الملكية غير متاحة.",
                "daily_baseline_missing": "خط الأساس اليومي غير متاح بعد.",
                "daily_loss_limit_reached": "تم بلوغ حد خسارة حقوق الملكية اليومي.",
                "losing_trade_limit_reached": "تم بلوغ حد الصفقات الخاسرة اليومي.",
                "automatic_trade_limit_reached": "تم بلوغ حد الدخولات التلقائية اليومي.",
                "daily_risk_limit": "حد المخاطر اليومي يمنع دخولاً جديداً.",
            }
            reason_codes = account.risk_reason_codes
            if not reason_codes and account.reconciliation_ready:
                reason_codes = ("daily_risk_limit",)
            for code in reason_codes:
                add(code, risk_messages.get(code, "سياسة المخاطر تمنع دخولاً جديداً."))
        if account.emergency_stop:
            add("emergency_stop", "إيقاف الطوارئ مفعّل.")
        if not account.reconciliation_ready:
            readiness_messages = {
                "reconciliation_snapshot_missing": "لا توجد لقطة حساب موثوقة بعد.",
                "reconciliation_snapshot_stale": "لقطة الحساب قديمة وتحتاج تحديثاً.",
                "reconciliation_refreshing": "تحديث بيانات الحساب جارٍ في الخلفية.",
                "reconciliation_timeout": "انتهت مهلة تحديث بيانات الحساب.",
                "reconciliation_failed": "فشل تحديث بيانات الحساب من Gate.io.",
                "cross_margin_not_confirmed": "وضع Cross Margin غير مؤكّد.",
                "risk_data_unavailable": "بيانات المخاطر غير متاحة.",
                "daily_baseline_missing": "خط الأساس اليومي للمخاطر غير متاح.",
                "private_stream_not_ready": "Private WebSocket غير جاهز.",
                "rest_snapshot_not_ready": "لقطة REST للحساب غير مكتملة.",
                "unmanaged_exchange_state": "توجد حالة Gate.io غير مُدارة.",
                "reconciliation_not_ready": "المصالحة غير مكتملة.",
            }
            reason_codes = account.reconciliation_reason_codes or (
                "reconciliation_not_ready",
            )
            for code in reason_codes:
                add(code, readiness_messages.get(code, "المصالحة غير مكتملة."))
        if not account.protection_ready:
            add("protection_not_ready", "حماية المراكز غير جاهزة.")

        state = getattr(market, "state")
        if state != "fresh":
            add(f"market_data_{state}", "بيانات السوق ليست حديثة.")
        if getattr(market, "sequence_gap"):
            add("market_sequence_gap", "يوجد انقطاع في تسلسل بيانات السوق.")
        best_bid = getattr(market, "best_bid")
        best_ask = getattr(market, "best_ask")
        if (
            rules.maximum_spread_percentage is not None
            and best_bid is not None
            and best_ask is not None
            and best_ask >= best_bid
        ):
            midpoint = (best_ask + best_bid) / Decimal("2")
            spread = (
                (best_ask - best_bid) / midpoint * Decimal("100")
                if midpoint > 0
                else Decimal("0")
            )
            if spread > rules.maximum_spread_percentage:
                add("spread_too_wide", "الفارق السعري أوسع من الحد المسموح.")
        if request.time_in_force not in rules.supported_time_in_force:
            add(
                "unsupported_time_in_force",
                "خيار مدة الأمر غير مدعوم لهذا العقد.",
                "time_in_force",
            )
        if (
            (request.direction == "short" and account.existing_position_quantity > 0)
            or (request.direction == "long" and account.existing_position_quantity < 0)
            and not request.reduce_only
        ):
            add(
                "one_way_position_conflict",
                "يوجد مركز معاكس في وضع One-way.",
                "direction",
            )

    @staticmethod
    def _validate_calculation(
        *,
        request: ManualOrderPreviewRequest,
        rules: FuturesContractRules,
        account: OrderAccountContext,
        raw_quantity: Decimal,
        quantity: Decimal,
        notional: Decimal,
        margin: Decimal,
        opening_fee: Decimal,
        behavior: str,
        issues: list[OrderValidationIssue],
    ) -> None:
        def add(code, message, field=None):
            issues.append(
                OrderValidationIssue(code=code, message_ar=message, field=field)
            )

        if request.size_mode == "quantity" and raw_quantity != quantity:
            add(
                "quantity_precision",
                "الكمية لا تطابق خطوة كمية العقد.",
                "quantity",
            )
        if quantity <= 0:
            add("quantity_zero", "الكمية بعد التقريب تساوي صفراً.", "quantity")
        if quantity < rules.minimum_quantity:
            add(
                "minimum_quantity",
                "الكمية أقل من الحد الأدنى للعقد.",
                "quantity",
            )
        maximum = (
            rules.maximum_market_quantity
            if request.order_type == "market"
            and rules.maximum_market_quantity is not None
            else rules.maximum_quantity
        )
        if maximum is not None and quantity > maximum:
            add(
                "maximum_quantity",
                "الكمية تتجاوز الحد الأقصى للعقد.",
                "quantity",
            )
        if not request.reduce_only and margin + opening_fee > account.available_balance:
            add(
                "insufficient_available_balance",
                "الرصيد المتاح لا يغطي الهامش والرسوم المقدرة.",
            )
        if notional <= 0:
            add("notional_zero", "القيمة الاسمية غير صالحة.")
        if request.reduce_only:
            position_quantity = abs(account.existing_position_quantity)
            expected_position_side = (
                account.existing_position_quantity > 0
                if request.direction == "short"
                else account.existing_position_quantity < 0
            )
            if not expected_position_side:
                add(
                    "reduce_only_position_missing",
                    "A reduce-only exit requires a matching open position.",
                    "reduce_only",
                )
            elif quantity > position_quantity:
                add(
                    "reduce_only_quantity_exceeds_position",
                    "A reduce-only exit cannot exceed the current position.",
                    "quantity",
                )
        if request.limit_price is not None and not OrderManager._is_step_aligned(
            request.limit_price, rules.price_step
        ):
            add(
                "limit_price_precision",
                "سعر Limit لا يطابق خطوة سعر العقد.",
                "limit_price",
            )
        if request.time_in_force == "poc" and behavior == "taker":
            add(
                "post_only_would_cross",
                "أمر POC سيُنفذ فوراً كمستفيد سيولة.",
                "limit_price",
            )

    @staticmethod
    def _raw_quantity(
        request: ManualOrderPreviewRequest,
        account: OrderAccountContext,
        rules: FuturesContractRules,
        reference_price: Decimal,
    ) -> Decimal:
        if request.size_mode == "quantity":
            assert request.quantity is not None
            return request.quantity
        if request.size_mode == "margin":
            assert request.margin_amount is not None
            margin = request.margin_amount
        else:
            assert request.balance_percentage is not None
            margin = (
                account.available_balance * request.balance_percentage / Decimal("100")
            )
        return (
            margin
            * Decimal(request.leverage)
            / (rules.contract_multiplier * reference_price)
        )

    @staticmethod
    def _reference_price(
        request: ManualOrderPreviewRequest,
        best_bid: Decimal | None,
        best_ask: Decimal | None,
        last_price: Decimal,
    ) -> Decimal:
        if request.limit_price is not None:
            return request.limit_price
        if request.direction == "long" and best_ask is not None:
            return best_ask
        if request.direction == "short" and best_bid is not None:
            return best_bid
        return last_price

    @staticmethod
    def _liquidity_behavior(
        request: ManualOrderPreviewRequest,
        *,
        best_bid: Decimal | None,
        best_ask: Decimal | None,
    ) -> str:
        if request.order_type == "market":
            return "taker"
        if request.limit_price is None or best_bid is None or best_ask is None:
            return "unknown"
        if request.direction == "long":
            return "taker" if request.limit_price >= best_ask else "maker"
        return "taker" if request.limit_price <= best_bid else "maker"

    @staticmethod
    def _protection_prices(
        *,
        direction: str,
        entry_price: Decimal,
        base_quantity: Decimal,
        allocated_margin: Decimal,
        entry_fee: Decimal,
        exit_fee_rate: Decimal,
        explicit_take_profit: Decimal | None,
        explicit_stop_loss: Decimal | None,
    ) -> tuple[Decimal, Decimal]:
        if (explicit_take_profit is None) != (explicit_stop_loss is None):
            raise ValueError("Take-profit and stop-loss must be supplied together.")
        if explicit_take_profit is not None and explicit_stop_loss is not None:
            take_profit, stop_loss = explicit_take_profit, explicit_stop_loss
        else:
            if base_quantity <= 0:
                raise ValueError(
                    "Protection calculation requires positive base quantity."
                )
            target = allocated_margin * Decimal("0.30")
            maximum_loss = allocated_margin * Decimal("0.10")
            if direction == "long":
                take_profit = (target + entry_fee + base_quantity * entry_price) / (
                    base_quantity * (Decimal("1") - exit_fee_rate)
                )
                stop_loss = (base_quantity * entry_price + entry_fee - maximum_loss) / (
                    base_quantity * (Decimal("1") - exit_fee_rate)
                )
            else:
                take_profit = (base_quantity * entry_price - entry_fee - target) / (
                    base_quantity * (Decimal("1") + exit_fee_rate)
                )
                stop_loss = (base_quantity * entry_price - entry_fee + maximum_loss) / (
                    base_quantity * (Decimal("1") + exit_fee_rate)
                )
        valid = (
            take_profit > entry_price > stop_loss
            if direction == "long"
            else take_profit < entry_price < stop_loss
        )
        if not valid:
            raise ValueError(
                "Protection prices are invalid for the requested direction."
            )
        return take_profit, stop_loss

    @staticmethod
    def _estimated_liquidation_price(
        direction: str,
        entry_price: Decimal,
        leverage: int,
        maintenance_rate: Decimal,
    ) -> Decimal | None:
        leverage_fraction = Decimal("1") / Decimal(leverage)
        if direction == "long":
            result = entry_price * (Decimal("1") - leverage_fraction + maintenance_rate)
        else:
            result = entry_price * (Decimal("1") + leverage_fraction - maintenance_rate)
        return result if result > 0 else None

    @staticmethod
    def _round_down(value: Decimal, step: Decimal) -> Decimal:
        return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

    @staticmethod
    def _is_step_aligned(value: Decimal, step: Decimal) -> bool:
        return value == OrderManager._round_down(value, step)

    @staticmethod
    def _fingerprint(
        *,
        request: ManualOrderPreviewRequest,
        context: OrderSubmissionContext,
        rules: FuturesContractRules,
        account: OrderAccountContext,
        market_payload: dict[str, object],
    ) -> str:
        payload = {
            "request": request.model_dump(mode="json"),
            "context": context.model_dump(mode="json"),
            "rules": rules.model_dump(mode="json"),
            "account": account.model_dump(
                mode="json",
                exclude={"snapshot_age_seconds"},
            ),
            "market": to_jsonable_python(market_payload),
        }
        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
