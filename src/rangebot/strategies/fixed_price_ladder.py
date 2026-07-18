"""Fixed Price Ladder futures strategy.

This module contains the strategy's validated configuration and deterministic
execution calculations.  It deliberately has no Gate.io or transport imports:
the small order-planner boundary below only calls the central Order Manager
provided by the engine.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_DOWN, Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from rangebot.domain.orders import (
    ExecutionEnvironment,
    FuturesContractRules,
    ManualOrderPreviewRequest,
)
from rangebot.domain.strategy import StrategyFieldMetadata, StrategyTypeMetadata
from rangebot.domain.strategy_runtime import (
    StrategyEvaluationContext,
    StrategyEvaluationResult,
)
from rangebot.strategies._common import blocked_result, engine_blocking_reasons


HUNDRED = Decimal("100")
ZERO = Decimal("0")

BudgetBasis = Literal["margin_budget", "notional_budget"]
AllocationMethod = Literal["equal", "custom_weights", "custom_amounts"]
PlacementMode = Literal["all_at_once", "sequential"]
TakeProfitMode = Literal[
    "price_percentage_from_average",
    "roi_percentage_on_used_margin",
    "exact_target_price",
]
FeeHandling = Literal["gross_before_fees", "net_after_estimated_trading_fees"]
StopLossMode = Literal[
    "disabled",
    "exact_price",
    "percentage_below_average",
    "percentage_below_lowest_entry",
    "maximum_loss_percentage_on_used_margin",
]
CyclePolicy = Literal["one_shot", "repeat_same_ladder", "manual_restart"]


class FixedPriceLadderLevel(BaseModel):
    """One user-authored limit-entry level."""

    model_config = ConfigDict(extra="forbid")

    level_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    enabled: bool = True
    price: Decimal = Field(gt=0)
    allocation_amount: Decimal | None = Field(default=None, gt=0)
    allocation_weight: Decimal | None = Field(default=None, gt=0, le=HUNDRED)
    display_order: int = Field(ge=0)


class FixedPriceLadderConfig(BaseModel):
    """Validated version-one configuration for a long USDT futures ladder."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="Fixed Price Ladder", min_length=1, max_length=200)
    contract_symbol: str = Field(pattern=r"^[A-Z0-9]+_[A-Z0-9]+$")
    enabled: bool = True
    environment: ExecutionEnvironment = "paper"
    direction: Literal["long_only"] = "long_only"
    margin_mode: Literal["isolated"] = "isolated"
    position_mode: Literal["one_way"] = "one_way"
    leverage: int = Field(default=1, ge=1, le=1000)
    total_budget: Decimal = Field(gt=0)
    budget_basis: BudgetBasis = "margin_budget"
    allocation_method: AllocationMethod = "equal"
    levels: list[FixedPriceLadderLevel] = Field(min_length=2, max_length=20)
    placement_mode: PlacementMode = "all_at_once"
    post_only: bool = False
    allow_immediate_fill: bool = False
    take_profit_mode: TakeProfitMode = "price_percentage_from_average"
    take_profit_value: Decimal = Field(gt=0)
    take_profit_fee_handling: FeeHandling = "gross_before_fees"
    exit_order_type: Literal["reduce_only_limit"] = "reduce_only_limit"
    stop_loss_mode: StopLossMode = "disabled"
    stop_loss_value: Decimal | None = Field(default=None, gt=0)
    cycle_policy: CyclePolicy = "one_shot"
    repeat_enabled: bool = False
    cooldown_seconds: int = Field(default=0, ge=0, le=31_536_000)
    safety_reserve: Decimal = Field(default=ZERO, ge=0)

    @model_validator(mode="after")
    def validate_ladder(self) -> "FixedPriceLadderConfig":
        enabled_levels = [level for level in self.levels if level.enabled]
        if len(enabled_levels) < 2:
            raise ValueError("At least two enabled ladder levels are required.")
        prices = [level.price for level in enabled_levels]
        if len(set(prices)) != len(prices):
            raise ValueError("Enabled ladder prices must be unique.")
        if prices != sorted(prices, reverse=True):
            raise ValueError("Long ladder prices must be arranged highest to lowest.")

        if self.allocation_method == "custom_weights":
            if any(level.allocation_weight is None for level in enabled_levels):
                raise ValueError("Every enabled level needs an allocation weight.")
            weight_total = sum(
                (level.allocation_weight or ZERO for level in enabled_levels), ZERO
            )
            if weight_total != HUNDRED:
                raise ValueError("Custom allocation weights must total 100%.")
        elif self.allocation_method == "custom_amounts":
            if any(level.allocation_amount is None for level in enabled_levels):
                raise ValueError("Every enabled level needs an allocation amount.")
            amount_total = sum(
                (level.allocation_amount or ZERO for level in enabled_levels), ZERO
            )
            if amount_total != self.total_budget:
                raise ValueError("Custom allocation amounts must equal total_budget.")

        if self.stop_loss_mode == "disabled" and self.stop_loss_value is not None:
            raise ValueError("A disabled stop-loss cannot have a value.")
        if self.stop_loss_mode != "disabled" and self.stop_loss_value is None:
            raise ValueError("An enabled stop-loss needs a value.")
        if self.cycle_policy == "repeat_same_ladder" and not self.repeat_enabled:
            raise ValueError("repeat_same_ladder requires repeat_enabled=true.")
        if self.cycle_policy != "repeat_same_ladder" and self.repeat_enabled:
            raise ValueError("repeat_enabled is only valid for repeat_same_ladder.")
        return self


class LadderValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    level_id: str | None = None


class FixedPriceLadderLevelPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    level_id: str
    display_order: int
    price: Decimal
    allocation: Decimal
    allocated_margin: Decimal
    notional_value: Decimal
    contract_quantity: Decimal
    underlying_quantity: Decimal
    estimated_entry_fee: Decimal
    cumulative_filled_quantity: Decimal
    projected_average_entry: Decimal | None
    projected_take_profit_price: Decimal | None
    projected_stop_loss_price: Decimal | None
    projected_position_value: Decimal
    projected_liquidation_price: Decimal | None
    liquidation_distance: Decimal | None
    issues: tuple[LadderValidationIssue, ...] = ()


class FixedPriceLadderPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_symbol: str
    environment: ExecutionEnvironment
    total_budget: Decimal
    budget_basis: BudgetBasis
    total_allocated_margin: Decimal
    total_estimated_fee_reserve: Decimal
    safety_reserve: Decimal
    total_required_balance: Decimal
    available_balance: Decimal | None
    market_price: Decimal | None
    contract_multiplier: Decimal
    quantity_step: Decimal
    minimum_quantity: Decimal
    price_tick: Decimal
    leverage: int
    margin_mode: str
    current_liquidation_price: Decimal | None
    levels: tuple[FixedPriceLadderLevelPreview, ...]
    issues: tuple[LadderValidationIssue, ...]
    warnings: tuple[str, ...]
    can_activate: bool


class LadderFill(BaseModel):
    """An actual exchange fill, retained for audit and fee calculations."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fill_id: str = Field(min_length=1, max_length=200)
    level_id: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(gt=0)
    contract_quantity: Decimal = Field(gt=0)
    fee: Decimal = Field(default=ZERO, ge=0)
    funding: Decimal = ZERO


class LadderPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_quantity: Decimal
    underlying_quantity: Decimal
    filled_notional: Decimal
    weighted_average_entry: Decimal | None
    used_margin: Decimal
    entry_fees: Decimal
    known_funding: Decimal
    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None = None


def normalize_quantity_down(quantity: Decimal, step: Decimal) -> Decimal:
    """Round a futures contract quantity down so budget cannot be exceeded."""
    if quantity <= 0:
        return ZERO
    return (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step


def normalize_price_up(price: Decimal, tick: Decimal) -> Decimal:
    """Round a long profit/protection price upward to a valid tick."""
    return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def contract_quantity_for_margin(
    margin: Decimal,
    price: Decimal,
    leverage: int,
    contract_multiplier: Decimal,
    quantity_step: Decimal,
) -> Decimal:
    if min(margin, price, contract_multiplier) <= 0:
        return ZERO
    raw = margin * Decimal(leverage) / (price * contract_multiplier)
    return normalize_quantity_down(raw, quantity_step)


def weighted_average_entry(
    fills: Iterable[LadderFill], contract_multiplier: Decimal
) -> Decimal | None:
    """Calculate the average from actual underlying-equivalent fills."""
    total_underlying = ZERO
    total_quote_notional = ZERO
    for fill in fills:
        underlying = fill.contract_quantity * contract_multiplier
        total_underlying += underlying
        total_quote_notional += underlying * fill.price
    if total_underlying == 0:
        return None
    return total_quote_notional / total_underlying


def _allocation_units(config: FixedPriceLadderConfig) -> dict[str, Decimal]:
    enabled = [level for level in config.levels if level.enabled]
    if config.allocation_method == "equal":
        unit = config.total_budget / Decimal(len(enabled))
        return {level.level_id: unit for level in enabled}
    if config.allocation_method == "custom_weights":
        return {
            level.level_id: config.total_budget
            * (level.allocation_weight or ZERO)
            / HUNDRED
            for level in enabled
        }
    return {level.level_id: level.allocation_amount or ZERO for level in enabled}


def _margin_for_allocation(
    allocation: Decimal, config: FixedPriceLadderConfig
) -> Decimal:
    return (
        allocation
        if config.budget_basis == "margin_budget"
        else allocation / Decimal(config.leverage)
    )


def _gross_target_price(
    config: FixedPriceLadderConfig,
    average: Decimal,
    underlying_quantity: Decimal,
    used_margin: Decimal,
) -> Decimal:
    if config.take_profit_mode == "exact_target_price":
        return config.take_profit_value
    if config.take_profit_mode == "price_percentage_from_average":
        return average * (Decimal("1") + config.take_profit_value / HUNDRED)
    if underlying_quantity <= 0:
        raise ValueError("ROI target requires a positive position quantity.")
    return (
        average
        + (used_margin * config.take_profit_value / HUNDRED) / underlying_quantity
    )


def calculate_take_profit_price(
    config: FixedPriceLadderConfig,
    fills: Sequence[LadderFill],
    *,
    contract_multiplier: Decimal,
    price_tick: Decimal,
    exit_fee_rate: Decimal = ZERO,
) -> Decimal | None:
    """Calculate a long TP from actual fills, preserving the requested basis."""
    average = weighted_average_entry(fills, contract_multiplier)
    if average is None:
        return None
    underlying = sum(
        (fill.contract_quantity * contract_multiplier for fill in fills), ZERO
    )
    filled_notional = underlying * average
    used_margin = filled_notional / Decimal(config.leverage)
    gross_target = _gross_target_price(config, average, underlying, used_margin)
    if config.take_profit_fee_handling == "net_after_estimated_trading_fees":
        entry_fees = sum((fill.fee for fill in fills), ZERO)
        requested_gross_pnl = (gross_target - average) * underlying
        gross_target = (filled_notional + requested_gross_pnl + entry_fees) / (
            underlying * (Decimal("1") - exit_fee_rate)
        )
    return normalize_price_up(gross_target, price_tick)


def calculate_stop_loss_price(
    config: FixedPriceLadderConfig,
    fills: Sequence[LadderFill],
    *,
    contract_multiplier: Decimal,
    price_tick: Decimal,
) -> Decimal | None:
    """Calculate an optional long stop and round it down for protection."""
    if config.stop_loss_mode == "disabled" or not fills:
        return None
    average = weighted_average_entry(fills, contract_multiplier)
    if average is None:
        return None
    underlying = sum(
        (fill.contract_quantity * contract_multiplier for fill in fills), ZERO
    )
    value = config.stop_loss_value or ZERO
    if config.stop_loss_mode == "exact_price":
        raw = value
    elif config.stop_loss_mode == "percentage_below_lowest_entry":
        raw = min(fill.price for fill in fills) * (Decimal("1") - value / HUNDRED)
    elif config.stop_loss_mode == "maximum_loss_percentage_on_used_margin":
        used_margin = (underlying * average) / Decimal(config.leverage)
        raw = average - (used_margin * value / HUNDRED) / underlying
    else:
        raw = average * (Decimal("1") - value / HUNDRED)
    if raw <= 0:
        return None
    return (raw / price_tick).to_integral_value(rounding=ROUND_DOWN) * price_tick


def _liquidation_price(
    average: Decimal | None, config: FixedPriceLadderConfig, rules: FuturesContractRules
) -> Decimal | None:
    if average is None:
        return None
    result = average * (
        Decimal("1") - Decimal("1") / Decimal(config.leverage) + rules.maintenance_rate
    )
    return result if result > 0 else None


def build_ladder_preview(
    config: FixedPriceLadderConfig,
    rules: FuturesContractRules,
    *,
    available_balance: Decimal | None,
    market_price: Decimal | None,
    market_state: str = "fresh",
    best_ask: Decimal | None = None,
    unmanaged_position: bool = False,
    unmanaged_order: bool = False,
) -> FixedPriceLadderPreview:
    """Build the complete read-only activation preview and blocking reasons."""
    issues: list[LadderValidationIssue] = []
    warnings: list[str] = []
    if rules.symbol != config.contract_symbol:
        issues.append(
            LadderValidationIssue(
                code="contract_mismatch",
                message="Contract metadata does not match the configured symbol.",
            )
        )
    if not rules.active or rules.in_delisting:
        issues.append(
            LadderValidationIssue(
                code="contract_inactive", message="The futures contract is not active."
            )
        )
    if market_state != "fresh":
        issues.append(
            LadderValidationIssue(
                code="market_data_stale",
                message="Fresh market data is required before activation.",
            )
        )
    if config.leverage > rules.maximum_leverage:
        issues.append(
            LadderValidationIssue(
                code="leverage_above_contract_limit",
                message="Configured leverage exceeds the contract limit.",
            )
        )
    if config.leverage > 1:
        warnings.append(
            "Leverage above 1x magnifies profit and loss; it does not change a price-based TP target."
        )
    if unmanaged_position:
        issues.append(
            LadderValidationIssue(
                code="unmanaged_position",
                message="An unmanaged position already exists on this contract.",
            )
        )
    if unmanaged_order:
        issues.append(
            LadderValidationIssue(
                code="unmanaged_order",
                message="An unmanaged order already exists on this contract.",
            )
        )

    allocations = _allocation_units(config)
    previews: list[FixedPriceLadderLevelPreview] = []
    cumulative_fills: list[LadderFill] = []
    total_margin = ZERO
    total_fees = ZERO
    entry_fee_rate = rules.maker_fee_rate if config.post_only else rules.taker_fee_rate
    for level in sorted(
        (item for item in config.levels if item.enabled),
        key=lambda item: item.display_order,
    ):
        level_issues: list[LadderValidationIssue] = []
        if (
            level.price
            != (level.price / rules.price_step).to_integral_value() * rules.price_step
        ):
            level_issues.append(
                LadderValidationIssue(
                    code="invalid_price_tick",
                    message="Entry price does not align with the exchange price tick.",
                    level_id=level.level_id,
                )
            )
        if (
            best_ask is not None
            and level.price > best_ask
            and not config.allow_immediate_fill
        ):
            level_issues.append(
                LadderValidationIssue(
                    code="immediate_fill_not_allowed",
                    message="Entry is above the best ask; enable allow_immediate_fill explicitly to activate.",
                    level_id=level.level_id,
                )
            )
        allocation = allocations[level.level_id]
        margin = _margin_for_allocation(allocation, config)
        raw_quantity = (
            margin
            * Decimal(config.leverage)
            / (level.price * rules.contract_multiplier)
        )
        quantity = normalize_quantity_down(raw_quantity, rules.quantity_step)
        if quantity == 0:
            level_issues.append(
                LadderValidationIssue(
                    code="order_rounds_to_zero",
                    message="Rounded contract quantity is zero.",
                    level_id=level.level_id,
                )
            )
        elif quantity < rules.minimum_quantity:
            level_issues.append(
                LadderValidationIssue(
                    code="minimum_quantity",
                    message="Rounded quantity is below the exchange minimum.",
                    level_id=level.level_id,
                )
            )
        underlying = quantity * rules.contract_multiplier
        notional = underlying * level.price
        fee = notional * entry_fee_rate
        total_margin += notional / Decimal(config.leverage)
        total_fees += fee
        cumulative_fills.append(
            LadderFill(
                fill_id=f"preview-{level.level_id}",
                level_id=level.level_id,
                price=level.price,
                contract_quantity=quantity,
                fee=fee,
            )
        )
        average = weighted_average_entry(cumulative_fills, rules.contract_multiplier)
        tp = calculate_take_profit_price(
            config,
            cumulative_fills,
            contract_multiplier=rules.contract_multiplier,
            price_tick=rules.price_step,
            exit_fee_rate=rules.taker_fee_rate,
        )
        stop = calculate_stop_loss_price(
            config,
            cumulative_fills,
            contract_multiplier=rules.contract_multiplier,
            price_tick=rules.price_step,
        )
        liquidation = _liquidation_price(average, config, rules)
        projected_quantity = sum(
            (fill.contract_quantity for fill in cumulative_fills), ZERO
        )
        previews.append(
            FixedPriceLadderLevelPreview(
                level_id=level.level_id,
                display_order=level.display_order,
                price=level.price,
                allocation=allocation,
                allocated_margin=margin,
                notional_value=notional,
                contract_quantity=quantity,
                underlying_quantity=underlying,
                estimated_entry_fee=fee,
                cumulative_filled_quantity=projected_quantity,
                projected_average_entry=average,
                projected_take_profit_price=tp,
                projected_stop_loss_price=stop,
                projected_position_value=sum(
                    (
                        fill.contract_quantity * rules.contract_multiplier * fill.price
                        for fill in cumulative_fills
                    ),
                    ZERO,
                ),
                projected_liquidation_price=liquidation,
                liquidation_distance=(
                    average - liquidation
                    if average is not None and liquidation is not None
                    else None
                ),
                issues=tuple(level_issues),
            )
        )
        issues.extend(level_issues)

    exit_notional = sum(
        (preview.projected_position_value for preview in previews[-1:]), ZERO
    )
    total_fees += exit_notional * rules.taker_fee_rate
    required_balance = total_margin + total_fees + config.safety_reserve
    if available_balance is not None and required_balance > available_balance:
        issues.append(
            LadderValidationIssue(
                code="insufficient_balance",
                message="Available balance does not cover margin, estimated fees, and safety reserve.",
            )
        )
    if config.placement_mode == "sequential":
        warnings.append(
            "Sequential placement is represented in configuration; all-at-once is the production-safe default for this release."
        )
    return FixedPriceLadderPreview(
        contract_symbol=config.contract_symbol,
        environment=config.environment,
        total_budget=config.total_budget,
        budget_basis=config.budget_basis,
        total_allocated_margin=total_margin,
        total_estimated_fee_reserve=total_fees,
        safety_reserve=config.safety_reserve,
        total_required_balance=required_balance,
        available_balance=available_balance,
        market_price=market_price,
        contract_multiplier=rules.contract_multiplier,
        quantity_step=rules.quantity_step,
        minimum_quantity=rules.minimum_quantity,
        price_tick=rules.price_step,
        leverage=config.leverage,
        margin_mode=config.margin_mode,
        current_liquidation_price=(
            previews[-1].projected_liquidation_price if previews else None
        ),
        levels=tuple(previews),
        issues=tuple(issues),
        warnings=tuple(warnings),
        can_activate=not issues,
    )


class LadderOrderManager(Protocol):
    """Minimum central Order Manager surface used by this strategy."""

    def submit_automatic(
        self, request: ManualOrderPreviewRequest, **kwargs: Any
    ) -> Any: ...


@dataclass
class FixedPriceLadderRuntime:
    """Restart-friendly in-memory projection rebuilt from persisted fills."""

    config: FixedPriceLadderConfig
    rules: FuturesContractRules
    cycle_id: str
    fills: list[LadderFill] = field(default_factory=list)
    processed_fill_ids: set[str] = field(default_factory=set)
    tp_order_id: str | None = None
    tp_generation: int = 0
    lifecycle: str = "draft"

    def record_fill(self, fill: LadderFill) -> bool:
        if fill.fill_id in self.processed_fill_ids:
            return False
        if not any(
            level.level_id == fill.level_id and level.enabled
            for level in self.config.levels
        ):
            raise ValueError("Fill references an unknown or disabled ladder level.")
        self.processed_fill_ids.add(fill.fill_id)
        self.fills.append(fill)
        self.lifecycle = "active"
        return True

    def snapshot(self) -> LadderPositionSnapshot:
        underlying = sum(
            (
                fill.contract_quantity * self.rules.contract_multiplier
                for fill in self.fills
            ),
            ZERO,
        )
        notional = sum(
            (
                fill.contract_quantity * self.rules.contract_multiplier * fill.price
                for fill in self.fills
            ),
            ZERO,
        )
        average = weighted_average_entry(self.fills, self.rules.contract_multiplier)
        return LadderPositionSnapshot(
            contract_quantity=sum(
                (fill.contract_quantity for fill in self.fills), ZERO
            ),
            underlying_quantity=underlying,
            filled_notional=notional,
            weighted_average_entry=average,
            used_margin=notional / Decimal(self.config.leverage)
            if self.config.leverage
            else ZERO,
            entry_fees=sum((fill.fee for fill in self.fills), ZERO),
            known_funding=sum((fill.funding for fill in self.fills), ZERO),
            take_profit_price=calculate_take_profit_price(
                self.config,
                self.fills,
                contract_multiplier=self.rules.contract_multiplier,
                price_tick=self.rules.price_step,
                exit_fee_rate=self.rules.taker_fee_rate,
            ),
            stop_loss_price=calculate_stop_loss_price(
                self.config,
                self.fills,
                contract_multiplier=self.rules.contract_multiplier,
                price_tick=self.rules.price_step,
            ),
        )

    def mark_position_closed(self) -> None:
        self.lifecycle = (
            "completed" if self.config.cycle_policy == "one_shot" else "exiting"
        )
        self.tp_order_id = None


class FixedPriceLadderOrderPlanner:
    """Translate validated ladder intents into central Order Manager calls."""

    def __init__(self, runtime: FixedPriceLadderRuntime) -> None:
        self.runtime = runtime

    def submit_entries(
        self,
        order_manager: LadderOrderManager,
        *,
        instance_id: str,
        run_id: str | None = None,
    ) -> tuple[Any, ...]:
        if self.runtime.config.placement_mode == "sequential":
            levels = sorted(
                (level for level in self.runtime.config.levels if level.enabled),
                key=lambda level: level.display_order,
            )[:1]
        else:
            levels = sorted(
                (level for level in self.runtime.config.levels if level.enabled),
                key=lambda level: level.display_order,
            )
        allocations = _allocation_units(self.runtime.config)
        results: list[Any] = []
        for level in levels:
            allocation = _margin_for_allocation(
                allocations[level.level_id], self.runtime.config
            )
            request = ManualOrderPreviewRequest(
                environment=self.runtime.config.environment,
                symbol=self.runtime.config.contract_symbol,
                direction="long",
                order_type="limit",
                size_mode="margin",
                margin_amount=allocation,
                leverage=self.runtime.config.leverage,
                limit_price=level.price,
                time_in_force="poc" if self.runtime.config.post_only else "gtc",
            )
            results.append(
                order_manager.submit_automatic(
                    request,
                    origin="automatic_strategy",
                    instance_id=instance_id,
                    run_id=run_id,
                    strategy_type_id="fixed_price_ladder",
                    cycle_id=self.runtime.cycle_id,
                    order_role="entry",
                    entry_level_id=level.level_id,
                    order_generation=0,
                )
            )
        self.runtime.lifecycle = "waiting_for_entry"
        return tuple(results)

    def submit_or_replace_take_profit(
        self,
        order_manager: LadderOrderManager,
        *,
        instance_id: str,
        run_id: str | None = None,
        cancel_owned_order: Callable[[str], Any] | None = None,
    ) -> Any | None:
        snapshot = self.runtime.snapshot()
        if snapshot.contract_quantity <= 0 or snapshot.take_profit_price is None:
            return None
        if self.runtime.tp_order_id is not None:
            if cancel_owned_order is None:
                raise RuntimeError(
                    "An existing ladder TP must be cancelled through the central order manager before replacement."
                )
            cancel_owned_order(self.runtime.tp_order_id)
            self.runtime.tp_order_id = None
        self.runtime.tp_generation += 1
        request = ManualOrderPreviewRequest(
            environment=self.runtime.config.environment,
            symbol=self.runtime.config.contract_symbol,
            direction="short",
            order_type="limit",
            size_mode="quantity",
            quantity=snapshot.contract_quantity,
            leverage=self.runtime.config.leverage,
            limit_price=snapshot.take_profit_price,
            time_in_force="gtc",
            reduce_only=True,
        )
        result = order_manager.submit_automatic(
            request,
            origin="automatic_strategy",
            instance_id=instance_id,
            run_id=run_id,
            strategy_type_id="fixed_price_ladder",
            cycle_id=self.runtime.cycle_id,
            order_role="take_profit",
            order_generation=self.runtime.tp_generation,
            reduce_only=True,
        )
        order_id = getattr(result, "order_id", None)
        if order_id:
            self.runtime.tp_order_id = order_id
        self.runtime.lifecycle = "active"
        return result


class FixedPriceLadderEvaluator:
    """Validate ladder readiness without creating a one-order signal."""

    type_id = "fixed_price_ladder"
    configuration_model = FixedPriceLadderConfig

    def evaluate(
        self, context: StrategyEvaluationContext, configuration: dict[str, Any]
    ) -> StrategyEvaluationResult:
        config = FixedPriceLadderConfig.model_validate(configuration)
        reasons = list(engine_blocking_reasons(context))
        if context.symbol != config.contract_symbol:
            reasons.append("contract_symbol_mismatch")
        if reasons:
            return blocked_result(
                self.type_id,
                context,
                tuple(reasons),
                used_closed_candles=sum(candle.closed for candle in context.candles),
                analysis={"strategy_mode": "execution_lifecycle"},
            )
        return StrategyEvaluationResult(
            type_id=self.type_id,
            symbol=context.symbol,
            evaluated_at=context.evaluated_at,
            signal="ladder_ready",
            eligible=True,
            reason_codes=("ladder_configuration_valid",),
            explanation_ar="تم التحقق من إعدادات سلم العقود الآجلة؛ تنتظر دورة التنفيذ والمصالحة.",
            analysis={
                "strategy_mode": "execution_lifecycle",
                "direction": "long",
                "take_profit_mode": config.take_profit_mode,
                "level_count": len([level for level in config.levels if level.enabled]),
            },
            used_closed_candles=sum(candle.closed for candle in context.candles),
            protective_actions_available=True,
            trade_request=None,
        )


STRATEGY_TYPE = StrategyTypeMetadata(
    type_id="fixed_price_ladder",
    display_name_ar="سلم الأسعار الثابت",
    display_name_en="Fixed Price Ladder",
    description_ar="سلم دخول Long لعقود آجلة خطية مُسواة بـ USDT؛ لا يمنح ملكية أصل Spot، ويعيد حماية Take-profit على متوسط التعبئة الفعلي.",
    description_en="Long-only USDT-settled linear futures ladder with exact limit entries, actual-fill weighted average, and one reduce-only take-profit.",
    version="1",
    supports_monitoring=True,
    supports_automatic_trading=True,
    supports_long=True,
    supports_short=False,
    supported_directions=("long",),
    supported_timeframes=(1, 5, 15, 30, 60, 240, 1440),
    required_market_data_feeds=("last_price", "mark_price", "best_bid_ask"),
    implementation_status="working",
    evaluation_cadence="market_update",
    configuration_schema=FixedPriceLadderConfig.model_json_schema(),
    summary_metrics=(
        StrategyFieldMetadata(
            key="weighted_average_entry",
            label_ar="متوسط الدخول المرجح",
            label_en="Weighted average entry",
            value_type="decimal",
            unit="price",
        ),
        StrategyFieldMetadata(
            key="current_take_profit",
            label_ar="سعر جني الربح الحالي",
            label_en="Current take-profit",
            value_type="decimal",
            unit="price",
        ),
        StrategyFieldMetadata(
            key="filled_levels",
            label_ar="المستويات المعبأة",
            label_en="Filled levels",
            value_type="status",
        ),
    ),
    live_analysis_fields=(
        StrategyFieldMetadata(
            key="used_margin",
            label_ar="الهامش المستخدم",
            label_en="Used margin",
            value_type="decimal",
            unit="USDT",
        ),
        StrategyFieldMetadata(
            key="known_funding",
            label_ar="التمويل المعروف",
            label_en="Known funding",
            value_type="decimal",
            unit="USDT",
        ),
        StrategyFieldMetadata(
            key="reconciliation_state",
            label_ar="حالة المصالحة",
            label_en="Reconciliation state",
            value_type="status",
        ),
    ),
    recommended_widgets=(
        "active_strategy",
        "risk_status",
        "strategy_chart",
        "decision_explanation",
    ),
    chart_overlays=(
        "ladder_entries",
        "weighted_average_entry",
        "take_profit",
        "stop_loss",
    ),
    status_badges=("futures", "long_only", "isolated", "leverage"),
    important_warnings_ar=(
        "هذه الاستراتيجية تتداول عقوداً آجلة خطية USDT؛ لا يملك المستخدم رموز Spot.",
        "الرافعة تضخم الربح والخسارة وقد تؤدي إلى التصفية؛ التمويل المستقبلي قد يغيّر صافي النتيجة.",
        "لا تُرسل أوامر الخروج إلا بصيغة reduce-only لمنع فتح مركز Short بالخطأ.",
    ),
)

STRATEGY_TYPE = STRATEGY_TYPE.model_copy(
    update={
        "required_market_data_feeds": (
            "candlesticks",
            "last_price",
            "mark_price",
            "best_bid_ask",
        )
    }
)

EVALUATOR_FACTORY = FixedPriceLadderEvaluator
