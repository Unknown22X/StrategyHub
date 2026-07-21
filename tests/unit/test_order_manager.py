from datetime import UTC, datetime
from decimal import Decimal

import pytest

from rangebot.domain.exchange import ExchangeOperationResult
from rangebot.domain.market_data import MarketPriceUpdate
from rangebot.domain.orders import (
    FuturesContractRules,
    ManualOrderPreviewRequest,
    ManualOrderSubmissionRequest,
    OrderAccountContext,
    OrderSubmissionContext,
)
from rangebot.engine.market_data_manager import MarketDataManager
from rangebot.engine.order_manager import (
    OrderManager,
    OrderValidationError,
    StaleOrderPreviewError,
)


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _rules(**changes) -> FuturesContractRules:
    values = {
        "symbol": "BTC_USDT",
        "contract_multiplier": Decimal("0.001"),
        "quantity_step": Decimal("1"),
        "minimum_quantity": Decimal("1"),
        "maximum_quantity": Decimal("1000"),
        "maximum_market_quantity": Decimal("500"),
        "price_step": Decimal("0.1"),
        "maximum_leverage": 20,
        "maintenance_rate": Decimal("0.005"),
        "maker_fee_rate": Decimal("0.0002"),
        "taker_fee_rate": Decimal("0.0005"),
        "maximum_spread_percentage": Decimal("0.01"),
    }
    values.update(changes)
    return FuturesContractRules.model_validate(values)


def _account(**changes) -> OrderAccountContext:
    values = {
        "environment": "live",
        "credentials_configured": True,
        "available_balance": Decimal("1000"),
        "existing_position_quantity": Decimal("0"),
        "one_way_confirmed": True,
        "daily_risk_allowed": True,
        "emergency_stop": False,
        "reconciliation_ready": True,
        "protection_ready": True,
        "account_revision": "account-1",
    }
    values.update(changes)
    return OrderAccountContext.model_validate(values)


def _market() -> MarketDataManager:
    manager = MarketDataManager(clock=lambda: NOW)
    manager.apply_rest_snapshot(
        MarketPriceUpdate(
            symbol="BTC_USDT",
            last_price=Decimal("65000"),
            mark_price=Decimal("64990"),
            best_bid=Decimal("64999.5"),
            best_ask=Decimal("65000.5"),
            volume_24h=Decimal("100000000"),
            funding_rate=Decimal("0.0001"),
            observed_at=NOW,
            source="gate_rest",
            sequence=10,
        )
    )
    return manager


class Harness:
    def __init__(self) -> None:
        self.account = _account()
        self.rules = _rules()
        self.executed = []
        self.ownership = []
        self.account_origins = []
        self.manager = OrderManager(
            market_data=_market(),
            contract_rules=lambda symbol, environment: self.rules,
            account_context=self._account_context,
            executor=self._execute,
            record_ownership=lambda order_id, request_id, environment, request, context: self.ownership.append(
                (order_id, request_id, environment, request, context)
            ),
        )

    def _account_context(self, environment, origin):
        self.account_origins.append((environment, origin))
        return self.account

    def _execute(self, environment, request):
        self.executed.append((environment, request))
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id="gate-order-1",
            message_ar="accepted",
        )


def test_market_margin_preview_calculates_authoritative_live_values() -> None:
    harness = Harness()
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="long",
        order_type="market",
        size_mode="margin",
        margin_amount=Decimal("100"),
        leverage=5,
        time_in_force="ioc",
    )

    preview = harness.manager.preview(request)

    assert preview.can_submit is True
    assert preview.uses_real_funds is True
    assert preview.live_warning_ar
    assert preview.reference_price == Decimal("65000.5")
    assert preview.estimated_quantity == Decimal("7")
    assert preview.estimated_notional == Decimal("455.0035")
    assert preview.estimated_margin == Decimal("91.0007")
    assert preview.estimated_opening_fee == Decimal("0.22750175")
    assert preview.estimated_fee_rate == Decimal("0.0005")
    assert preview.estimated_take_profit_price > preview.reference_price
    assert preview.estimated_stop_loss_price < preview.reference_price
    assert preview.estimated_liquidity_behavior == "taker"
    assert preview.estimated_liquidation_price == Decimal("52325.4025")
    assert preview.mark_price == Decimal("64990")
    assert preview.best_bid == Decimal("64999.5")
    assert preview.best_ask == Decimal("65000.5")


def test_limit_preview_estimates_maker_and_rejects_crossing_post_only() -> None:
    harness = Harness()
    maker_request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="long",
        order_type="limit",
        size_mode="quantity",
        quantity=Decimal("10"),
        leverage=5,
        limit_price=Decimal("64990.0"),
        time_in_force="poc",
    )
    crossing_request = maker_request.model_copy(
        update={"limit_price": Decimal("65001.0")}
    )

    maker = harness.manager.preview(maker_request)
    crossing = harness.manager.preview(crossing_request)

    assert maker.can_submit is True
    assert maker.estimated_liquidity_behavior == "maker"
    assert maker.estimated_fee_rate == Decimal("0.0002")
    assert maker.limit_distance_percentage is not None
    assert crossing.can_submit is False
    assert crossing.estimated_liquidity_behavior == "taker"
    assert {issue.code for issue in crossing.validation_issues} == {
        "post_only_would_cross"
    }


def test_limit_order_with_trailing_stop_is_blocked_without_execution() -> None:
    harness = Harness()
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="long",
        order_type="limit",
        size_mode="quantity",
        quantity=Decimal("10"),
        leverage=5,
        limit_price=Decimal("64990.0"),
        time_in_force="gtc",
    )
    context = OrderSubmissionContext(
        origin="automatic_strategy",
        instance_id="trend-instance",
        run_id="trend-run",
        trailing_stop_price=Decimal("64000"),
    )

    preview = harness.manager.preview(request, context=context)

    assert preview.can_submit is False
    assert {issue.code for issue in preview.validation_issues} == {
        "trailing_stop_market_only"
    }
    with pytest.raises(OrderValidationError):
        harness.manager.submit(
            ManualOrderSubmissionRequest(
                request=request,
                preview_fingerprint=preview.safety_fingerprint,
            ),
            context=context,
        )
    assert harness.executed == []
    assert harness.ownership == []


def test_preview_reports_all_account_contract_and_precision_blockers() -> None:
    harness = Harness()
    harness.rules = _rules(
        active=False,
        in_delisting=True,
        maximum_leverage=3,
        supported_time_in_force=("gtc",),
    )
    harness.account = _account(
        credentials_configured=False,
        available_balance=Decimal("1"),
        existing_position_quantity=Decimal("2"),
        one_way_confirmed=False,
        daily_risk_allowed=False,
        emergency_stop=True,
        reconciliation_ready=False,
        protection_ready=False,
    )
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="short",
        order_type="limit",
        size_mode="quantity",
        quantity=Decimal("1.5"),
        leverage=5,
        limit_price=Decimal("64990.05"),
        time_in_force="ioc",
    )

    preview = harness.manager.preview(request)
    codes = {issue.code for issue in preview.validation_issues}

    assert preview.can_submit is False
    assert {
        "credentials_missing",
        "contract_inactive",
        "contract_delisting",
        "leverage_above_contract_limit",
        "one_way_not_confirmed",
        "daily_risk_limit",
        "emergency_stop",
        "reconciliation_not_ready",
        "protection_not_ready",
        "unsupported_time_in_force",
        "one_way_position_conflict",
        "quantity_precision",
        "limit_price_precision",
        "insufficient_available_balance",
    }.issubset(codes)


def test_balance_percentage_preview_and_submission_revalidate_before_execution() -> None:
    harness = Harness()
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="short",
        order_type="market",
        size_mode="balance_percentage",
        balance_percentage=Decimal("25"),
        leverage=10,
        time_in_force="fok",
    )
    preview = harness.manager.preview(request)

    submitted = harness.manager.submit(
        ManualOrderSubmissionRequest(
            request=request,
            preview_fingerprint=preview.safety_fingerprint,
        )
    )

    assert submitted.accepted is True
    assert submitted.origin == "manual"
    assert submitted.order_id == "gate-order-1"
    assert len(harness.executed) == 1
    environment, exchange_request = harness.executed[0]
    assert environment == "live"
    assert exchange_request.origin == "manual"
    assert exchange_request.time_in_force == "fok"
    assert exchange_request.quantity == preview.estimated_quantity
    assert exchange_request.take_profit_price == preview.estimated_take_profit_price
    assert exchange_request.stop_loss_price == preview.estimated_stop_loss_price
    assert len(harness.ownership) == 1
    order_id, request_id, ownership_environment, ownership_request, ownership_context = harness.ownership[0]
    assert order_id == "gate-order-1"
    assert request_id == exchange_request.client_request_id
    assert ownership_environment == "live"
    assert ownership_request.symbol == "BTC_USDT"
    assert ownership_request.direction == "short"
    assert ownership_context.origin == "manual"
    assert ownership_context.instance_id is None
    assert ownership_context.run_id is None

    harness.account = harness.account.model_copy(
        update={"account_revision": "account-2"}
    )
    with pytest.raises(StaleOrderPreviewError):
        harness.manager.submit(
            ManualOrderSubmissionRequest(
                request=request,
                preview_fingerprint=preview.safety_fingerprint,
            )
        )


def test_submission_never_calls_executor_when_central_validation_fails() -> None:
    harness = Harness()
    harness.account = _account(emergency_stop=True)
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="long",
        order_type="market",
        size_mode="quantity",
        quantity=Decimal("2"),
        leverage=5,
        time_in_force="ioc",
    )
    preview = harness.manager.preview(request)

    with pytest.raises(OrderValidationError):
        harness.manager.submit(
            ManualOrderSubmissionRequest(
                request=request,
                preview_fingerprint=preview.safety_fingerprint,
            )
        )

    assert harness.executed == []


def test_automatic_submission_uses_same_validation_with_strategy_ownership() -> None:
    harness = Harness()
    request = ManualOrderPreviewRequest(
        environment="live",
        symbol="BTC_USDT",
        direction="long",
        order_type="market",
        size_mode="quantity",
        quantity=Decimal("2"),
        leverage=5,
        time_in_force="ioc",
    )
    manual_preview = harness.manager.preview(request)

    submitted = harness.manager.submit_automatic(
        request,
        origin="automatic_strategy",
        instance_id="strategy-1",
        run_id="run-1",
        take_profit_price=Decimal("67000"),
        stop_loss_price=Decimal("63000"),
    )

    assert submitted.accepted is True
    assert submitted.origin == "automatic_strategy"
    assert submitted.preview.safety_fingerprint != manual_preview.safety_fingerprint
    assert harness.account_origins[-2:] == [
        ("live", "automatic_strategy"),
        ("live", "automatic_strategy"),
    ]
    assert harness.executed[-1][1].origin == "automatic_strategy"
    assert harness.executed[-1][1].take_profit_price == Decimal("67000")
    assert harness.executed[-1][1].stop_loss_price == Decimal("63000")
    ownership_context = harness.ownership[-1][4]
    assert ownership_context.origin == "automatic_strategy"
    assert ownership_context.instance_id == "strategy-1"
    assert ownership_context.run_id == "run-1"
