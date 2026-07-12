"""Decimal-safe Paper Entry Preview calculations with no order authority."""

import hashlib
import json
from decimal import Decimal, ROUND_DOWN
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


FALLBACK_FEE_RATE = Decimal("0.001")


class EntryPreviewRequest(BaseModel):
    """Safety-critical inputs for one Paper entry preview."""

    model_config = ConfigDict(frozen=True)

    available_futures_balance: Decimal = Field(gt=0)
    allocation_percentage: Decimal
    safety_reserve_percentage: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    leverage: Literal[1, 5, 10]
    expected_entry_price: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    minimum_quantity: Decimal = Field(gt=0)
    entry_fee_rate: Decimal | None = Field(default=None, ge=0)
    exit_fee_rate: Decimal | None = Field(default=None, ge=0)
    direction: Literal["long", "short"]
    quote_revision: str = Field(min_length=1, max_length=200)

    @field_validator("allocation_percentage")
    @classmethod
    def validate_allocation_percentage(cls, value: Decimal) -> Decimal:
        if value not in {Decimal("25"), Decimal("50"), Decimal("75"), Decimal("100")}:
            raise ValueError("Allocation must be 25%, 50%, 75%, or 100%.")
        return value


class EntryPreview(BaseModel):
    """The complete Paper calculation presented before any confirmation."""

    model_config = ConfigDict(frozen=True)

    available_futures_balance: Decimal
    safety_reserve: Decimal
    allocation_budget: Decimal
    allocated_margin: Decimal
    notional_value: Decimal
    quantity: Decimal
    entry_fee: Decimal
    estimated_exit_fee: Decimal
    total_required: Decimal
    expected_entry_price: Decimal
    estimated_liquidation_price: Decimal | None
    estimated_liquidation_label: str
    take_profit_price: Decimal | None
    stop_loss_price: Decimal | None
    fee_source: Literal["configured", "fallback"]
    blocking_reasons: list[str]
    can_submit: bool
    safety_fingerprint: str


class PreviewValidationRequest(BaseModel):
    preview: EntryPreview
    current_request: EntryPreviewRequest


def create_entry_preview(request: EntryPreviewRequest) -> EntryPreview:
    """Calculate a conservative Paper sizing preview using Decimal throughout."""
    entry_fee_rate = request.entry_fee_rate or FALLBACK_FEE_RATE
    exit_fee_rate = request.exit_fee_rate or FALLBACK_FEE_RATE
    fee_source: Literal["configured", "fallback"] = (
        "configured" if request.entry_fee_rate is not None and request.exit_fee_rate is not None else "fallback"
    )
    reserve = request.available_futures_balance * request.safety_reserve_percentage / Decimal("100")
    allocation_budget = (request.available_futures_balance - reserve) * request.allocation_percentage / Decimal("100")
    allocated_margin_before_rounding = allocation_budget / (
        Decimal("1") + Decimal(request.leverage) * (entry_fee_rate + exit_fee_rate)
    )
    raw_quantity = (
        allocated_margin_before_rounding * Decimal(request.leverage) / request.expected_entry_price
    )
    quantity = _round_down(raw_quantity, request.quantity_step)
    notional_value = quantity * request.expected_entry_price
    allocated_margin = notional_value / Decimal(request.leverage)
    entry_fee = notional_value * entry_fee_rate
    estimated_exit_fee = notional_value * exit_fee_rate
    total_required = allocated_margin + entry_fee + estimated_exit_fee + reserve
    blocking_reasons: list[str] = []
    if quantity < request.minimum_quantity:
        blocking_reasons.append("minimum_quantity")
    if total_required > request.available_futures_balance:
        blocking_reasons.append("insufficient_available_futures_balance")
    if quantity == 0:
        blocking_reasons.append("rounded_quantity_zero")

    take_profit_price, stop_loss_price = _protection_preview(
        request.direction,
        request.expected_entry_price,
        quantity,
        allocated_margin,
        entry_fee,
        exit_fee_rate,
    )
    if take_profit_price is None or stop_loss_price is None:
        blocking_reasons.append("invalid_protection_preview")

    return EntryPreview(
        available_futures_balance=request.available_futures_balance,
        safety_reserve=reserve,
        allocation_budget=allocation_budget,
        allocated_margin=allocated_margin,
        notional_value=notional_value,
        quantity=quantity,
        entry_fee=entry_fee,
        estimated_exit_fee=estimated_exit_fee,
        total_required=total_required,
        expected_entry_price=request.expected_entry_price,
        estimated_liquidation_price=_estimated_liquidation(request),
        estimated_liquidation_label="Paper estimated liquidation",
        take_profit_price=take_profit_price,
        stop_loss_price=stop_loss_price,
        fee_source=fee_source,
        blocking_reasons=blocking_reasons,
        can_submit=not blocking_reasons,
        safety_fingerprint=_safety_fingerprint(request),
    )


def preview_is_current(preview: EntryPreview, current_request: EntryPreviewRequest) -> bool:
    """Reject a confirmation if any preview safety input changed."""
    return preview.safety_fingerprint == _safety_fingerprint(current_request)


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _estimated_liquidation(request: EntryPreviewRequest) -> Decimal:
    leverage_factor = Decimal("1") / Decimal(request.leverage)
    if request.direction == "long":
        return request.expected_entry_price * (Decimal("1") - leverage_factor)
    return request.expected_entry_price * (Decimal("1") + leverage_factor)


def _protection_preview(
    direction: Literal["long", "short"],
    entry_price: Decimal,
    quantity: Decimal,
    allocated_margin: Decimal,
    entry_fee: Decimal,
    exit_fee_rate: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    if quantity == 0:
        return None, None
    target = allocated_margin * Decimal("0.30")
    maximum_loss = allocated_margin * Decimal("0.10")
    if direction == "long":
        denominator = quantity * (Decimal("1") - exit_fee_rate)
        take_profit = (target + entry_fee + quantity * entry_price) / denominator
        stop_loss = (quantity * entry_price + entry_fee - maximum_loss) / denominator
    else:
        denominator = quantity * (Decimal("1") + exit_fee_rate)
        take_profit = (quantity * entry_price - entry_fee - target) / denominator
        stop_loss = (quantity * entry_price - entry_fee + maximum_loss) / denominator
    if stop_loss <= 0 or take_profit <= 0:
        return None, None
    return take_profit, stop_loss


def _safety_fingerprint(request: EntryPreviewRequest) -> str:
    serialized = json.dumps(request.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
