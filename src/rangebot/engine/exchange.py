"""Gate.io adapter boundary and durable safety policy for exchange-backed modes."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import json
import os
from time import time
from typing import Any, Callable, Protocol

import httpx

from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOpenOrderSnapshot,
    ExchangeOperationResult,
    ExchangePositionSnapshot,
    ExchangeSnapshot,
    ExchangeTrailingStopRequest,
    MarketEntryGuardRequest,
    MarketEntryGuardResult,
    MarketGuardQuoteRequest,
    ModeState,
    OrderBookLevel,
    TradingMode,
)
from rangebot.domain.trades import TradeFillCreate
from rangebot.engine.credentials import load_gate_credentials


def _decimal_value(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else default))
    except Exception:
        return Decimal(default)


def _optional_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _utc_timestamp(value: object) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    try:
        timestamp = float(str(value))
    except (TypeError, ValueError):
        return None
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    try:
        return datetime.fromtimestamp(timestamp, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _gate_trade_fill(mode: TradingMode, item: dict[str, object]) -> TradeFillCreate | None:
    trade_id = item.get("id", item.get("trade_id"))
    contract = str(item.get("contract", "")).strip()
    price = _decimal_value(item.get("price"))
    signed_size = _decimal_value(item.get("size"))
    occurred_at = _utc_timestamp(item.get("create_time", item.get("create_time_ms")))
    if trade_id in (None, "") or not contract or price <= 0 or signed_size == 0 or occurred_at is None:
        return None
    quantity = abs(signed_size)
    close_quantity = min(abs(_decimal_value(item.get("close_size"))), quantity)
    effect = (
        "open"
        if close_quantity == 0
        else "close"
        if close_quantity >= quantity
        else "mixed"
    )
    role_value = str(item.get("role", "unknown")).lower()
    role = role_value if role_value in {"maker", "taker"} else "unknown"
    return TradeFillCreate(
        environment=mode,
        external_trade_id=str(trade_id),
        order_id=(str(item["order_id"]) if item.get("order_id") not in (None, "") else None),
        contract=contract,
        side="buy" if signed_size > 0 else "sell",
        position_effect=effect,
        quantity=quantity,
        price=price,
        fee=-_decimal_value(item.get("fee")),
        role=role,
        close_quantity=close_quantity,
        trade_value=abs(_decimal_value(item.get("trade_value"), str(quantity * price))),
        occurred_at=occurred_at,
        source="gate_rest",
    )


def _position_snapshot(item: dict[str, object]) -> ExchangePositionSnapshot | None:
    signed_size = _decimal_value(item.get("size"))
    if signed_size == 0:
        return None
    leverage = _optional_decimal(item.get("lever"))
    if leverage in (None, Decimal("0")):
        leverage = _optional_decimal(item.get("leverage"))
    if leverage in (None, Decimal("0")):
        leverage = _optional_decimal(item.get("cross_leverage_limit"))
    return ExchangePositionSnapshot(
        contract=str(item.get("contract", "")),
        side="long" if signed_size > 0 else "short",
        quantity=abs(signed_size),
        entry_price=_optional_decimal(item.get("entry_price")),
        mark_price=_optional_decimal(item.get("mark_price")),
        value=abs(_decimal_value(item.get("value"))),
        margin=abs(
            _decimal_value(
                item.get("initial_margin", item.get("margin", "0"))
            )
        ),
        unrealized_pnl=_decimal_value(item.get("unrealised_pnl")),
        realized_pnl=_decimal_value(item.get("realised_pnl")),
        liquidation_price=_optional_decimal(item.get("liq_price")),
        leverage=leverage,
        pending_orders=int(item.get("pending_orders") or 0),
        opened_at=_utc_timestamp(item.get("open_time")),
        updated_at=_utc_timestamp(item.get("update_time")),
    )


def _order_snapshot(item: dict[str, object]) -> ExchangeOpenOrderSnapshot:
    signed_size = _decimal_value(item.get("size"))
    quantity = abs(signed_size)
    left = abs(_decimal_value(item.get("left"), str(quantity)))
    price = _optional_decimal(item.get("price"))
    text = str(item.get("text", ""))
    return ExchangeOpenOrderSnapshot(
        order_id=str(item.get("id", "")),
        contract=str(item.get("contract", "")),
        side="long" if signed_size >= 0 else "short",
        order_type="market" if price in (None, Decimal("0")) else "limit",
        price=None if price == 0 else price,
        quantity=quantity,
        filled_quantity=max(Decimal("0"), quantity - left),
        status=str(item.get("status", "open")),
        reduce_only=bool(item.get("is_reduce_only", item.get("reduce_only", False))),
        created_at=_utc_timestamp(
            item.get("create_time_ms", item.get("create_time"))
        ),
        managed_by_rangebot=text.startswith("t-rangebot-"),
    )


def guard_market_entry(request: MarketEntryGuardRequest) -> MarketEntryGuardResult:
    """Reject stale, thin, or >0.30% adverse market execution before submission."""
    now = datetime.now(UTC)
    levels = request.asks if request.direction == "long" else request.bids
    if now - request.last_price_observed_at > timedelta(seconds=1):
        return MarketEntryGuardResult(
            allowed=False, reason_ar="سعر Last أقدم من ثانية واحدة."
        )
    if not levels or any(
        now - level.observed_at > timedelta(seconds=1) for level in levels
    ):
        return MarketEntryGuardResult(
            allowed=False, reason_ar="لقطة دفتر الأوامر قديمة أو غير متاحة."
        )
    remaining = request.quantity
    total = Decimal("0")
    for level in levels:
        taken = min(remaining, level.quantity)
        total += taken * level.price
        remaining -= taken
        if remaining == 0:
            break
    if remaining != 0:
        return MarketEntryGuardResult(
            allowed=False, reason_ar="سيولة دفتر الأوامر غير كافية."
        )
    expected = total / request.quantity
    deviation = abs(expected - request.last_price) / request.last_price * Decimal("100")
    if deviation > Decimal("0.30"):
        return MarketEntryGuardResult(
            allowed=False,
            expected_price=expected,
            deviation_percentage=deviation,
            reason_ar="الانحراف المتوقع يتجاوز 0.30٪.",
        )
    return MarketEntryGuardResult(
        allowed=True, expected_price=expected, deviation_percentage=deviation
    )


class GateIoAdapter(Protocol):
    """Gateway seam; implementations keep Gate payloads and authentication private."""

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot: ...

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult: ...

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult: ...

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult: ...

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult: ...

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult: ...

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult: ...

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest: ...

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult: ...


class UnavailableGateIoAdapter:
    """Safe default: no exchange state is trusted until a real adapter is configured."""

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            reconciliation_error="Gate.io adapter غير مهيأ؛ لم تُجرَ مصالحة.",
            one_way_confirmed=False,
            cross_margin_confirmed=False,
            market_ready=False,
            history_ready=False,
            protection_ready=False,
        )

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        return self._unavailable(request.client_request_id)

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("cancel-managed-entry")

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("close-managed-position")

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("ensure-protection")

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult:
        del mode
        return self._unavailable(request.client_request_id)

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult:
        del mode
        return self._unavailable(f"cancel-trail-{order_id}")

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        raise RuntimeError("Market guard quote is unavailable.")

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult:
        return self._unavailable(f"set-{protection}-protection")

    @staticmethod
    def _unavailable(client_request_id: str) -> ExchangeOperationResult:
        return ExchangeOperationResult(
            accepted=False,
            client_request_id=client_request_id,
            message_ar="لا يوجد adapter Gate.io مهيأ؛ لم يُرسل أي أمر.",
        )


class MockGateIoAdapter:
    """Deterministic local futures lifecycle simulator for automated safety tests."""

    def __init__(self) -> None:
        self.position_quantity = Decimal("0")
        self.liquidation_price: Decimal | None = None
        self.pending_request_id: str | None = None
        self.pending_limit_price: Decimal | None = None
        self.pending_symbol: str | None = None
        self.pending_direction: str | None = None
        self.protection_confirmed = True
        self.tp_enabled = True
        self.sl_enabled = True
        self.take_profit_quantity = Decimal("0")
        self.stop_loss_quantity = Decimal("0")
        self.take_profit_price: Decimal | None = None
        self.stop_loss_price: Decimal | None = None
        self.trailing_stop_distance: Decimal | None = None
        self.trailing_order_id: str | None = None
        self.subscription_confirmed = True
        self.rest_snapshot_confirmed = True
        self.websocket_price_updates = 2
        self.market_observed_at = datetime.now(UTC)
        self.submissions: dict[str, ExchangeOperationResult] = {}
        self.automatic_intent = False
        self.active_contract: str | None = "BTC_USDT"
        self.risk_ready = True
        self.daily_baseline_ready = True
        self.one_way_confirmed = True
        self.cross_margin_confirmed = True
        self.leverage_confirmed = 5
        self.unmanaged_position = False
        self.unmanaged_order_ids: set[str] = set()
        self.used_signals: set[tuple[str, str]] = set()
        self.cooldown_complete = True
        self.closure_reason: str | None = None
        self.manual_close_plan: list[Decimal] = [Decimal("0")]

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=Decimal("1000"),
            position_quantity=self.position_quantity,
            liquidation_price=self.liquidation_price,
            managed_order_ids=(self.pending_request_id,)
            if self.pending_request_id
            else (),
            unmanaged_state=self.unmanaged_position or bool(self.unmanaged_order_ids),
            one_way_confirmed=self.one_way_confirmed,
            cross_margin_confirmed=self.cross_margin_confirmed,
            leverage_confirmed=self.leverage_confirmed,
            market_ready=True,
            history_ready=True,
            risk_ready=self.risk_ready,
            active_contract_ready=self.active_contract is not None,
            daily_baseline_ready=self.daily_baseline_ready,
            protection_ready=self.protection_confirmed,
            trailing_protection_ready=(
                self.trailing_order_id is not None
                if self.trailing_stop_distance is not None
                else None
            ),
            trailing_order_ids=(self.trailing_order_id,) if self.trailing_order_id else (),
            tp_enabled=self.tp_enabled,
            sl_enabled=self.sl_enabled,
            subscription_confirmed=self.subscription_confirmed,
            rest_snapshot_confirmed=self.rest_snapshot_confirmed,
            websocket_price_updates=self.websocket_price_updates,
            market_observed_at=self.market_observed_at,
        )

    def protection_orders(self) -> tuple[dict[str, Any], ...]:
        """Return sanitized managed protection contracts for assertions/UI state."""
        orders: list[dict[str, Any]] = []
        if self.tp_enabled and self.take_profit_quantity:
            orders.append(
                {
                    "kind": "tp",
                    "order_type": "limit",
                    "trigger_source": "last_price",
                    "reduce_only": True,
                    "quantity": str(self.take_profit_quantity),
                    "price": str(self.take_profit_price),
                }
            )
        if self.sl_enabled and self.stop_loss_quantity:
            orders.append(
                {
                    "kind": "sl",
                    "order_type": "stop_market",
                    "trigger_source": "mark_price",
                    "reduce_only": True,
                    "quantity": str(self.stop_loss_quantity),
                    "price": str(self.stop_loss_price),
                }
            )
        return tuple(orders)

    def export_state(self) -> dict[str, Any]:
        """Serialize restart-critical mock state without secrets or transport data."""
        return {
            "position_quantity": str(self.position_quantity),
            "liquidation_price": (
                str(self.liquidation_price)
                if self.liquidation_price is not None
                else None
            ),
            "pending_request_id": self.pending_request_id,
            "pending_limit_price": (
                str(self.pending_limit_price)
                if self.pending_limit_price is not None
                else None
            ),
            "pending_symbol": self.pending_symbol,
            "pending_direction": self.pending_direction,
            "protection_confirmed": self.protection_confirmed,
            "tp_enabled": self.tp_enabled,
            "sl_enabled": self.sl_enabled,
            "take_profit_quantity": str(self.take_profit_quantity),
            "stop_loss_quantity": str(self.stop_loss_quantity),
            "take_profit_price": (
                str(self.take_profit_price) if self.take_profit_price else None
            ),
            "stop_loss_price": (
                str(self.stop_loss_price) if self.stop_loss_price else None
            ),
            "trailing_stop_distance": (
                str(self.trailing_stop_distance)
                if self.trailing_stop_distance is not None
                else None
            ),
            "trailing_order_id": self.trailing_order_id,
            "automatic_intent": self.automatic_intent,
            "active_contract": self.active_contract,
            "risk_ready": self.risk_ready,
            "daily_baseline_ready": self.daily_baseline_ready,
            "used_signals": sorted([list(signal) for signal in self.used_signals]),
            "cooldown_complete": self.cooldown_complete,
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "MockGateIoAdapter":
        adapter = cls()
        adapter.position_quantity = Decimal(state["position_quantity"])
        adapter.liquidation_price = (
            Decimal(state["liquidation_price"])
            if state.get("liquidation_price") is not None
            else None
        )
        adapter.pending_request_id = state["pending_request_id"]
        adapter.pending_limit_price = (
            Decimal(state["pending_limit_price"])
            if state["pending_limit_price"] is not None
            else None
        )
        adapter.pending_symbol = state.get("pending_symbol")
        adapter.pending_direction = state.get("pending_direction")
        adapter.protection_confirmed = bool(state["protection_confirmed"])
        adapter.tp_enabled = bool(state.get("tp_enabled", True))
        adapter.sl_enabled = bool(state.get("sl_enabled", True))
        adapter.take_profit_quantity = Decimal(state["take_profit_quantity"])
        adapter.stop_loss_quantity = Decimal(state["stop_loss_quantity"])
        adapter.take_profit_price = (
            Decimal(str(state["take_profit_price"]))
            if state.get("take_profit_price")
            else None
        )
        adapter.stop_loss_price = (
            Decimal(str(state["stop_loss_price"]))
            if state.get("stop_loss_price")
            else None
        )
        adapter.trailing_stop_distance = (
            Decimal(str(state["trailing_stop_distance"]))
            if state.get("trailing_stop_distance") is not None
            else None
        )
        adapter.trailing_order_id = state.get("trailing_order_id")
        adapter.automatic_intent = bool(state["automatic_intent"])
        adapter.active_contract = state["active_contract"]
        adapter.risk_ready = bool(state.get("risk_ready", True))
        adapter.daily_baseline_ready = bool(state.get("daily_baseline_ready", True))
        adapter.used_signals = {
            (str(signal[0]), str(signal[1])) for signal in state["used_signals"]
        }
        adapter.cooldown_complete = bool(state["cooldown_complete"])
        adapter.begin_reconnect()
        return adapter

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        prior = self.submissions.get(request.client_request_id)
        if prior is not None:
            return prior
        if self.position_quantity != 0 or self.pending_request_id is not None:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="يوجد مركز أو أمر دخول مُدار قائم.",
            )
        if request.order_type == "limit":
            if request.limit_price is None:
                return ExchangeOperationResult(
                    accepted=False,
                    client_request_id=request.client_request_id,
                    message_ar="سعر Limit مطلوب.",
                )
            self.pending_request_id = request.client_request_id
            self.pending_limit_price = request.limit_price
            self.pending_symbol = request.symbol
            self.pending_direction = request.direction
            result = ExchangeOperationResult(
                accepted=True,
                client_request_id=request.client_request_id,
                order_id=f"mock-{request.client_request_id}",
                message_ar="تم تسجيل أمر Limit المُدار.",
            )
            self.submissions[request.client_request_id] = result
            return result
        self.position_quantity = request.quantity
        self.liquidation_price = (
            Decimal("80") if request.direction == "long" else Decimal("120")
        )
        self.protection_confirmed = request.protections_enabled
        self.take_profit_quantity = (
            request.quantity
            if request.protections_enabled and self.tp_enabled
            else Decimal("0")
        )
        self.stop_loss_quantity = (
            request.quantity
            if request.protections_enabled and self.sl_enabled
            else Decimal("0")
        )
        entry_price = Decimal("100")
        if request.take_profit_price is not None and request.stop_loss_price is not None:
            self.take_profit_price = request.take_profit_price
            self.stop_loss_price = request.stop_loss_price
        else:
            tp_delta = request.take_profit_percentage / Decimal("100")
            sl_delta = request.stop_loss_percentage / Decimal("100")
            if request.direction == "long":
                self.take_profit_price = entry_price * (Decimal("1") + tp_delta)
                self.stop_loss_price = entry_price * (Decimal("1") - sl_delta)
            else:
                self.take_profit_price = entry_price * (Decimal("1") - tp_delta)
                self.stop_loss_price = entry_price * (Decimal("1") + sl_delta)
        self.trailing_stop_distance = request.trailing_stop_distance
        self.trailing_order_id = (
            f"mock-trail-{request.client_request_id}"
            if request.trailing_stop_distance is not None
            else None
        )
        result = ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=f"mock-{request.client_request_id}",
            message_ar="تمت تعبئة محاكاة الأمر المُدار.",
        )
        self.submissions[request.client_request_id] = result
        return result

    def settle_limit(
        self, quantity: Decimal, average_fill_price: Decimal | None = None
    ) -> str:
        """Apply expiry or a partial/full managed Limit fill in the local simulator."""
        if self.pending_request_id is None:
            raise LookupError("No managed Limit entry is pending.")
        if quantity < 0:
            raise ValueError("Limit fill quantity cannot be negative.")
        if quantity == 0:
            if self.pending_symbol and self.pending_direction:
                self.used_signals.add((self.pending_symbol, self.pending_direction))
            self.pending_request_id = None
            self.pending_limit_price = None
            self.pending_symbol = None
            self.pending_direction = None
            return "expired"
        self.position_quantity = quantity
        self.liquidation_price = (
            average_fill_price * Decimal("0.8")
            if average_fill_price is not None
            else self.pending_limit_price * Decimal("0.8")
            if self.pending_limit_price is not None
            else None
        )
        self.take_profit_quantity = quantity
        self.stop_loss_quantity = quantity
        self.protection_confirmed = True
        self.pending_request_id = None
        self.pending_limit_price = None
        self.pending_symbol = None
        self.pending_direction = None
        return "partial_filled" if average_fill_price is not None else "filled"

    def inject_unmanaged_state(
        self, *, position: bool = False, order_ids: tuple[str, ...] = ()
    ) -> None:
        self.unmanaged_position = position
        self.unmanaged_order_ids.update(order_ids)

    def clear_unmanaged_state(self) -> None:
        self.unmanaged_position = False
        self.unmanaged_order_ids.clear()

    def apply_partial_fill(self, quantity: Decimal) -> None:
        if quantity <= 0 or quantity > self.position_quantity:
            raise ValueError("Partial fill must be within the managed position.")
        self.position_quantity = quantity
        self.protection_confirmed = True
        self.take_profit_quantity = quantity
        self.stop_loss_quantity = quantity

    def reconcile_external_position(self, quantity: Decimal) -> str:
        """Model external closure/reduction without adopting an unmanaged order."""
        if quantity < 0 or quantity > self.position_quantity:
            raise ValueError("External position quantity is invalid.")
        if quantity == 0:
            self.position_quantity = Decimal("0")
            self.liquidation_price = None
            self.take_profit_quantity = Decimal("0")
            self.stop_loss_quantity = Decimal("0")
            self.protection_confirmed = True
            self.closure_reason = "External Gate.io Closure"
            return "external_closed"
        self.position_quantity = quantity
        self.take_profit_quantity = quantity
        self.stop_loss_quantity = quantity
        self.protection_confirmed = True
        return "external_reduced"

    def cancel_protection_externally(self) -> None:
        self.protection_confirmed = False

    def restore_protection(self) -> None:
        if self.position_quantity == 0:
            return
        self.take_profit_quantity = self.position_quantity
        self.stop_loss_quantity = self.position_quantity
        self.protection_confirmed = True

    def protection_triggered_close(self, remaining_fill_plan: list[Decimal]) -> str:
        """Repeat reduce-only closing until zero; never cross through zero."""
        for remaining in remaining_fill_plan:
            if remaining < 0 or remaining > self.position_quantity:
                raise ValueError(
                    "Protection close cannot reverse or increase a position."
                )
            self.position_quantity = remaining
            if remaining:
                self.take_profit_quantity = remaining
                self.stop_loss_quantity = remaining
        if self.position_quantity != 0:
            raise RuntimeError("Protection close remains incomplete.")
        self.liquidation_price = None
        self.take_profit_quantity = Decimal("0")
        self.stop_loss_quantity = Decimal("0")
        self.protection_confirmed = True
        self.cooldown_complete = False
        self.closure_reason = "Protection Triggered Closure"
        return "closed"

    def begin_reconnect(self) -> None:
        self.subscription_confirmed = False
        self.rest_snapshot_confirmed = False
        self.websocket_price_updates = 0

    def confirm_reconnect(self, websocket_updates: int = 2) -> None:
        self.subscription_confirmed = True
        self.rest_snapshot_confirmed = True
        self.websocket_price_updates = websocket_updates
        self.market_observed_at = datetime.now(UTC)

    def start_automatic(self, active_contract: str = "BTC_USDT") -> None:
        snapshot = self.reconcile("testnet")
        if entry_blocks(snapshot, False) or not self.risk_ready:
            raise RuntimeError(
                "Automatic trading cannot start until readiness is complete."
            )
        self.active_contract = active_contract
        self.automatic_intent = True

    def may_resume_automatic(self) -> bool:
        snapshot = self.reconcile("testnet")
        return (
            self.automatic_intent
            and self.active_contract is not None
            and self.risk_ready
            and self.protection_confirmed
            and not entry_blocks(snapshot, False)
        )

    def consume_automatic_signal(self, symbol: str, direction: str) -> None:
        signal = (symbol, direction)
        if signal in self.used_signals:
            raise RuntimeError(
                "Used Signal cannot enter again before Directional Reset."
            )
        if symbol != self.active_contract or not self.may_resume_automatic():
            raise RuntimeError("Automatic entry readiness is incomplete.")
        self.used_signals.add(signal)

    def directional_reset(self, symbol: str, direction: str) -> None:
        if not self.cooldown_complete or self.position_quantity != 0:
            raise RuntimeError(
                "Directional Reset requires zero position and completed cooldown."
            )
        self.used_signals.discard((symbol, direction))

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        self.pending_request_id = None
        self.pending_limit_price = None
        self.pending_symbol = None
        self.pending_direction = None
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="cancel",
            message_ar="تم إلغاء أمر الدخول المُدار.",
        )

    @staticmethod
    def automatic_limit_price(
        direction: str, current_price: Decimal, offset_percentage: Decimal
    ) -> Decimal:
        multiplier = offset_percentage / Decimal("100")
        if direction == "long":
            return current_price * (Decimal("1") - multiplier)
        if direction == "short":
            return current_price * (Decimal("1") + multiplier)
        raise ValueError("Unknown entry direction.")

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        self.take_profit_quantity = Decimal("0")
        self.stop_loss_quantity = Decimal("0")
        for remaining in self.manual_close_plan:
            if remaining < 0 or remaining > self.position_quantity:
                raise ValueError("Managed close cannot reverse or increase a position.")
            self.position_quantity = remaining
        if self.position_quantity != 0:
            return ExchangeOperationResult(
                accepted=False,
                pending_unknown=True,
                client_request_id="close",
                message_ar="تعذر إغلاق كامل الكمية المُدارة.",
            )
        self.liquidation_price = None
        self.protection_confirmed = True
        self.take_profit_quantity = Decimal("0")
        self.stop_loss_quantity = Decimal("0")
        self.trailing_stop_distance = None
        self.trailing_order_id = None
        self.cooldown_complete = False
        self.closure_reason = "Manual Close Position"
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="close",
            message_ar="تم إغلاق المركز المُدار بالكامل.",
        )

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        self.protection_confirmed = self.position_quantity == 0 or (
            self.protection_confirmed
            and (
                not self.tp_enabled
                or self.take_profit_quantity == self.position_quantity
            )
            and (
                not self.sl_enabled or self.stop_loss_quantity == self.position_quantity
            )
        )
        return ExchangeOperationResult(
            accepted=self.protection_confirmed,
            client_request_id="protection",
            message_ar="تم التحقق من حماية المركز المُدار.",
        )

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult:
        del mode
        if self.position_quantity == 0:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="لا يوجد مركز محاكاة يحتاج وقف تتبع.",
            )
        self.trailing_stop_distance = request.trailing_stop_distance
        self.trailing_order_id = f"mock-trail-{request.client_request_id}"
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=self.trailing_order_id,
            message_ar="تم إنشاء أو استعادة وقف التتبع المحاكى.",
        )

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult:
        del mode
        if self.trailing_order_id not in {None, order_id}:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=f"cancel-trail-{order_id}",
                message_ar="معرّف وقف التتبع المحاكى لا يطابق الحماية المُدارة.",
            )
        self.trailing_stop_distance = None
        self.trailing_order_id = None
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=f"cancel-trail-{order_id}",
            message_ar="تم إلغاء وقف التتبع المحاكى.",
        )

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        now = datetime.now(UTC)
        level = OrderBookLevel(
            price=Decimal("100.10"), quantity=request.quantity, observed_at=now
        )
        return MarketEntryGuardRequest(
            direction=request.direction,
            quantity=request.quantity,
            last_price=Decimal("100"),
            last_price_observed_at=now,
            asks=[level] if request.direction == "long" else [],
            bids=[level] if request.direction == "short" else [],
        )

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult:
        if protection == "tp":
            self.tp_enabled = enabled
            self.take_profit_quantity = (
                self.position_quantity if enabled else Decimal("0")
            )
        elif protection == "sl":
            self.sl_enabled = enabled
            self.stop_loss_quantity = (
                self.position_quantity if enabled else Decimal("0")
            )
        else:
            raise ValueError("Unknown protection type.")
        self.protection_confirmed = True
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=f"set-{protection}",
            message_ar="تم تحديث إعداد الحماية المُدار.",
        )


@dataclass(frozen=True)
class GateIoV4Endpoints:
    """Explicit Gate.io endpoints; credentials come from protected runtime storage."""

    testnet_base_url: str = "https://api-testnet.gateapi.io/api/v4"
    live_base_url: str = "https://api.gateio.ws/api/v4"


@dataclass(frozen=True)
class GateIoConfiguration:
    """Private engine configuration; UI/API models never expose these values."""

    mode: TradingMode
    key: str
    secret: str
    base_url: str

    @classmethod
    def from_environment(cls, mode: TradingMode) -> "GateIoConfiguration":
        prefix = "GATE_TESTNET" if mode == "testnet" else "GATE_LIVE"
        key = os.environ.get(f"{prefix}_KEY", "")
        secret = os.environ.get(f"{prefix}_SECRET", "")
        if not key or not secret:
            raise ValueError(f"{prefix} credentials are not configured.")
        endpoints = GateIoV4Endpoints()
        return cls(
            mode=mode,
            key=key,
            secret=secret,
            base_url=endpoints.testnet_base_url
            if mode == "testnet"
            else endpoints.live_base_url,
        )

    def redacted_description(self) -> str:
        return f"{self.mode} Gate.io configuration ({self.key[:3]}…[REDACTED])"


class HttpxGateTransport:
    """Private signed HTTP transport; constructed only by explicit runtime opt-in."""

    def __call__(
        self,
        method: str,
        url: str,
        query: str,
        headers: dict[str, str],
        body: str,
    ) -> dict[str, Any]:
        full_url = f"{url}?{query}" if query else url
        response = httpx.request(
            method,
            full_url,
            headers=headers,
            content=body or None,
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()


def configured_gate_adapter(
    mode: TradingMode, *, enable_network: bool, enable_order_submission: bool = False
) -> GateIoAdapter:
    """Build a read-only-capable adapter; order submission always starts disabled."""
    try:
        configuration = GateIoConfiguration.from_environment(mode)
    except ValueError:
        stored = load_gate_credentials(mode)
        if stored is None:
            return UnavailableGateIoAdapter()
        configuration = GateIoConfiguration(
            mode=mode,
            key=stored.api_key,
            secret=stored.api_secret,
            base_url=(
                "https://api-testnet.gateapi.io/api/v4"
                if mode == "testnet"
                else "https://api.gateio.ws/api/v4"
            ),
        )
    return GateIoV4Adapter(
        configuration,
        transport=HttpxGateTransport() if enable_network else None,
        allow_network=enable_network,
        allow_order_submission=enable_order_submission,
    )


class GateIoV4Adapter:
    """Signed Gate v4 futures adapter; network/order access is explicitly opt-in."""

    def __init__(
        self,
        configuration: GateIoConfiguration,
        transport: Callable[[str, str, str, dict[str, str], str], dict[str, Any]]
        | None = None,
        allow_network: bool = False,
        allow_order_submission: bool = False,
    ) -> None:
        self._configuration = configuration
        self._transport = transport
        self._allow_network = allow_network
        self._allow_order_submission = allow_order_submission
        self._managed_order_ids: tuple[str, ...] = ()
        self._managed_trailing_order_ids: tuple[str, ...] = ()
        self._managed_contract: str | None = None
        self._managed_position_size = Decimal("0")

    def signed_headers(
        self, method: str, path: str, query: str, body: str, timestamp: str
    ) -> dict[str, str]:
        payload_hash = hashlib.sha512(body.encode("utf-8")).hexdigest()
        signing_string = "\n".join(
            (method.upper(), f"/api/v4{path}", query, payload_hash, timestamp)
        )
        signature = hmac.new(
            self._configuration.secret.encode("utf-8"),
            signing_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "KEY": self._configuration.key,
            "Timestamp": timestamp,
            "SIGN": signature,
        }

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        self._require_mode(mode)
        account = self._request("GET", "/futures/usdt/accounts", "", "")
        positions = self._request("GET", "/futures/usdt/positions", "", "")
        orders = self._request("GET", "/futures/usdt/orders", "status=open", "")
        price_orders = self._request(
            "GET", "/futures/usdt/price_orders", "status=open&limit=100", ""
        )
        trailing_reconciliation_ready = True
        try:
            trail_payload = self._request(
                "GET",
                "/futures/usdt/autoorder/v1/trail/list",
                "is_finished=false&page_num=1&page_size=100",
                "",
            )
            trail_orders = _gate_trail_order_rows(trail_payload)
        except Exception:
            trail_orders = []
            trailing_reconciliation_ready = False
        position_snapshots = tuple(
            snapshot
            for item in positions
            if (snapshot := _position_snapshot(item)) is not None
        )
        order_snapshots = tuple(_order_snapshot(item) for item in orders)
        position_quantity = sum(
            (item.quantity for item in position_snapshots), Decimal("0")
        )
        liquidation_price = next(
            (
                item.liquidation_price
                for item in position_snapshots
                if item.liquidation_price is not None
            ),
            None,
        )
        total_balance = _decimal_value(account.get("total"))
        unrealized_pnl = _decimal_value(
            account.get("cross_unrealised_pnl", account.get("unrealised_pnl", "0"))
        )
        margin_balance = _optional_decimal(account.get("cross_margin_balance"))
        total_equity = margin_balance or total_balance + unrealized_pnl
        history = account.get("history")
        account_history = history if isinstance(history, dict) else {}
        realized_pnl_total = _decimal_value(account_history.get("pnl"))
        fees_total = _decimal_value(account_history.get("fee"))
        funding_total = _decimal_value(account_history.get("fund"))
        net_pnl_total = realized_pnl_total + fees_total + funding_total
        open_exposure = sum(
            (item.value for item in position_snapshots), Decimal("0")
        )
        position_margin = sum(
            (item.margin for item in position_snapshots), Decimal("0")
        ) or _decimal_value(account.get("position_margin"))
        order_margin = _decimal_value(
            account.get("cross_order_margin", account.get("order_margin", "0"))
        )
        used_margin = position_margin + order_margin
        margin_usage_percentage = (
            used_margin / total_equity * Decimal("100")
            if total_equity > 0
            else Decimal("0")
        )
        leverage_value = account.get("leverage")
        leverage = (
            int(leverage_value)
            if leverage_value in (1, 5, 10, "1", "5", "10")
            else None
        )
        managed_orders = tuple(
            str(item["id"])
            for item in orders
            if str(item.get("text", "")).startswith("t-rangebot-")
        )
        managed_trailing_orders = tuple(
            item
            for item in trail_orders
            if str(item.get("text", "")).startswith("t-rbtrail-")
            and str(item.get("status", "open")) == "open"
        )
        managed_trailing_order_ids = tuple(
            str(item["id"])
            for item in managed_trailing_orders
            if item.get("id") is not None
        )
        managed_contracts = {
            str(item.get("contract"))
            for item in orders
            if str(item.get("text", "")).startswith("t-rangebot-")
        }
        managed_contracts.update(
            str(item.get("contract"))
            for item in managed_trailing_orders
            if item.get("contract")
        )
        protection_contracts = {
            str(initial.get("contract"))
            for item in price_orders
            if isinstance(item, dict)
            and item.get("status") in {"open", "inactive"}
            and isinstance((initial := item.get("initial")), dict)
            and initial.get("contract")
        }
        managed_contracts.update(protection_contracts)
        if managed_contracts:
            self._managed_contract = next(iter(managed_contracts))
        self._managed_order_ids = managed_orders
        self._managed_trailing_order_ids = managed_trailing_order_ids
        matching_positions = [
            item
            for item in positions
            if self._managed_contract is not None
            and str(item.get("contract")) == self._managed_contract
        ]
        self._managed_position_size = sum(
            (Decimal(str(item.get("size", "0"))) for item in matching_positions),
            Decimal("0"),
        )
        unmanaged_positions = bool(positions) and not matching_positions
        protection_ready = all(
            _gate_position_has_tp_sl(item, price_orders)
            for item in matching_positions
            if Decimal(str(item.get("size", "0"))) != 0
        )
        if not matching_positions:
            protection_ready = not positions
        trailing_protection_ready: bool | None = None
        active_matching_positions = [
            position
            for position in matching_positions
            if Decimal(str(position.get("size", "0"))) != 0
        ]
        if managed_trailing_order_ids:
            trailing_protection_ready = bool(active_matching_positions) and all(
                any(
                    str(order.get("contract", "")) == str(position.get("contract", ""))
                    and bool(order.get("reduce_only", False))
                    and bool(order.get("position_related", False))
                    for order in managed_trailing_orders
                )
                for position in active_matching_positions
            )
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=_decimal_value(
                account.get("cross_available", account.get("available", "0"))
            ),
            total_futures_balance=total_balance,
            total_futures_equity=total_equity,
            unrealized_pnl=unrealized_pnl,
            position_margin=position_margin,
            order_margin=order_margin,
            used_margin=used_margin,
            margin_usage_percentage=margin_usage_percentage,
            realized_pnl_total=realized_pnl_total,
            fees_total=fees_total,
            funding_total=funding_total,
            net_pnl_total=net_pnl_total,
            open_exposure=open_exposure,
            position_quantity=position_quantity,
            liquidation_price=liquidation_price,
            positions=position_snapshots,
            open_orders=order_snapshots,
            managed_order_ids=managed_orders,
            unmanaged_state=unmanaged_positions
            or any(
                not str(item.get("text", "")).startswith("t-rangebot-")
                for item in orders
            ),
            one_way_confirmed=account.get("position_mode") in ("single", "one_way"),
            cross_margin_confirmed=account.get("margin_mode") == "cross",
            leverage_confirmed=leverage,
            market_ready=False,
            history_ready=False,
            protection_ready=protection_ready,
            trailing_protection_ready=trailing_protection_ready,
            trailing_reconciliation_ready=trailing_reconciliation_ready,
            trailing_order_ids=managed_trailing_order_ids,
        )

    def recent_trade_fills(self, mode: TradingMode) -> tuple[TradeFillCreate, ...]:
        """Return a bounded, sanitized Gate trade page for idempotent local ingestion."""
        self._require_mode(mode)
        rows = self._request(
            "GET",
            "/futures/usdt/my_trades",
            "limit=1000",
            "",
        )
        if not isinstance(rows, list):
            raise RuntimeError("Gate.io returned an invalid trade-history response.")
        fills: list[TradeFillCreate] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            fill = _gate_trade_fill(mode, row)
            if fill is not None:
                fills.append(fill)
        return tuple(fills)

    def submit_entry(
        self, mode: TradingMode, request: ExchangeEntryRequest
    ) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="إرسال أوامر Gate.io معطّل افتراضياً.",
            )
        if request.order_type == "limit" and request.limit_price is None:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="سعر Limit مطلوب ولا يمكن تغييره ضمنياً.",
            )
        if request.trailing_stop_price is not None and (
            request.order_type != "market" or request.trailing_stop_distance is None
        ):
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="وقف التتبع يتطلب أمر Market ومسافة تتبع صريحة.",
            )
        signed_quantity = (
            request.quantity if request.direction == "long" else -request.quantity
        )
        if request.protections_enabled and (
            request.take_profit_price is None or request.stop_loss_price is None
        ):
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="لا يمكن فتح مركز Gate.io من دون سعري TP وSL صريحين.",
            )
        payload = {
            "contract": request.symbol,
            "size": str(signed_quantity),
            "price": (
                "0" if request.order_type == "market" else str(request.limit_price)
            ),
            "tif": (
                request.time_in_force
                if request.order_type == "limit"
                else request.time_in_force
                if request.time_in_force in {"ioc", "fok"}
                else "ioc"
            ),
            "text": f"t-rangebot-{request.client_request_id}",
            "reduce_only": False,
        }
        if request.protections_enabled:
            payload["tpsl_tp_trigger_price"] = str(request.take_profit_price)
            payload["tpsl_sl_trigger_price"] = str(request.stop_loss_price)
        result = self._request(
            "POST",
            "/futures/usdt/orders",
            "",
            json.dumps(payload, separators=(",", ":")),
        )
        self._managed_contract = request.symbol
        if result.get("id") is not None:
            self._managed_order_ids = (str(result["id"]),)
        trailing_warning = False
        if request.trailing_stop_price is not None and request.trailing_stop_distance is not None:
            try:
                trail_id = self._submit_trailing_order(
                    symbol=request.symbol,
                    direction=request.direction,
                    quantity=request.quantity,
                    trailing_stop_distance=request.trailing_stop_distance,
                    client_request_id=request.client_request_id,
                )
                if trail_id is not None:
                    self._managed_trailing_order_ids = (trail_id,)
            except Exception:
                trailing_warning = True
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=str(result.get("id")),
            pending_unknown=trailing_warning,
            message_ar=(
                "تم قبول أمر الدخول وتأكيد TP/SL، لكن وقف التتبع يحتاج مصالحة."
                if trailing_warning
                else "تم قبول الأمر المُدار مع حماية TP/SL ووقف التتبع."
                if request.trailing_stop_price is not None
                else "تم قبول أمر مُدار."
            ),
        )

    def _submit_trailing_order(
        self,
        *,
        symbol: str,
        direction: str,
        quantity: Decimal,
        trailing_stop_distance: Decimal,
        client_request_id: str,
    ) -> str | None:
        close_amount = -quantity if direction == "long" else quantity
        trail_text = f"t-rbtrail-{client_request_id.replace('-', '')[:16]}"
        payload = {
            "contract": symbol,
            "amount": str(close_amount),
            "activation_price": "0",
            "is_gte": direction == "long",
            "price_type": 3,
            "price_offset": str(trailing_stop_distance),
            "reduce_only": True,
            "position_related": True,
            "text": trail_text,
            "pos_margin_mode": "cross",
            "position_mode": "single",
        }
        response = self._request(
            "POST",
            "/futures/usdt/autoorder/v1/trail/create",
            "",
            json.dumps(payload, separators=(",", ":")),
        )
        if isinstance(response, dict):
            if response.get("id") is not None:
                return str(response["id"])
            data = response.get("data")
            if isinstance(data, dict):
                order = data.get("order")
                if isinstance(order, dict) and order.get("id") is not None:
                    return str(order["id"])
        return None

    def ensure_trailing_protection(
        self, mode: TradingMode, request: ExchangeTrailingStopRequest
    ) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return self._orders_disabled(request.client_request_id)
        try:
            trail_id = self._submit_trailing_order(
                symbol=request.symbol,
                direction=request.direction,
                quantity=request.quantity,
                trailing_stop_distance=request.trailing_stop_distance,
                client_request_id=request.client_request_id,
            )
        except Exception as error:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar=f"تعذر استعادة وقف التتبع: {type(error).__name__}.",
            )
        if trail_id is None:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request.client_request_id,
                message_ar="لم تُرجع Gate.io معرّفاً لوقف التتبع.",
            )
        self._managed_trailing_order_ids = (trail_id,)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=trail_id,
            message_ar="تم إنشاء أو استعادة وقف التتبع في Gate.io.",
        )

    def cancel_trailing_protection(
        self, mode: TradingMode, order_id: str
    ) -> ExchangeOperationResult:
        self._require_mode(mode)
        request_id = f"cancel-trail-{order_id}"
        if not self._allow_order_submission:
            return self._orders_disabled(request_id)
        payload_id: int | str = int(order_id) if order_id.isdigit() else order_id
        try:
            self._request(
                "POST",
                "/futures/usdt/autoorder/v1/trail/stop",
                "",
                json.dumps({"id": payload_id}, separators=(",", ":")),
            )
        except Exception as error:
            return ExchangeOperationResult(
                accepted=False,
                client_request_id=request_id,
                message_ar=f"تعذر إلغاء وقف التتبع: {type(error).__name__}.",
            )
        self._managed_trailing_order_ids = tuple(
            managed_id
            for managed_id in self._managed_trailing_order_ids
            if managed_id != order_id
        )
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request_id,
            message_ar="تم إلغاء وقف التتبع المُدار في Gate.io.",
        )

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return self._orders_disabled("cancel")
        open_orders = self._request(
            "GET", "/futures/usdt/orders", "status=open", ""
        )
        if not isinstance(open_orders, list):
            raise RuntimeError("Gate.io returned an invalid open-order response.")
        discovered_ids = {
            str(item["id"])
            for item in open_orders
            if isinstance(item, dict)
            and item.get("id") is not None
            and str(item.get("text", "")).startswith("t-rangebot-")
            and not bool(item.get("reduce_only", False))
        }
        managed_ids = tuple(sorted(set(self._managed_order_ids) | discovered_ids))
        for order_id in managed_ids:
            self._request("DELETE", f"/futures/usdt/orders/{order_id}", "", "")
        self._managed_order_ids = ()
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="cancel",
            message_ar="تم إلغاء الأوامر المُدارة.",
        )

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return self._orders_disabled("close")
        if self._managed_contract is None or self._managed_position_size == 0:
            return ExchangeOperationResult(
                accepted=True,
                client_request_id="close",
                message_ar="لا يوجد مركز مُدار مفتوح.",
            )
        self.cancel_managed_entry(mode)
        payload = {
            "contract": self._managed_contract,
            "size": str(-self._managed_position_size),
            "price": "0",
            "tif": "ioc",
            "text": "t-rangebot-close",
            "reduce_only": True,
        }
        result = self._request(
            "POST",
            "/futures/usdt/orders",
            "",
            json.dumps(payload, separators=(",", ":")),
        )
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="close",
            order_id=str(result.get("id")),
            message_ar="تم إرسال إغلاق reduce-only للمركز المُدار.",
        )

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return self._orders_disabled("protection")
        snapshot = self.reconcile(mode)
        if snapshot.position_quantity == 0:
            return ExchangeOperationResult(
                accepted=True,
                client_request_id="protection",
                message_ar="لا يوجد مركز يحتاج حماية.",
            )
        return ExchangeOperationResult(
            accepted=snapshot.protection_ready,
            client_request_id="protection",
            message_ar=(
                "حالة TP وSL مؤكدة من أوامر Gate.io المحفزة."
                if snapshot.protection_ready
                else "حماية TP أو SL غير مكتملة في Gate.io."
            ),
        )

    def market_guard_quote(
        self, mode: TradingMode, request: MarketGuardQuoteRequest
    ) -> MarketEntryGuardRequest:
        self._require_mode(mode)
        contract = request.symbol
        ticker = self._request(
            "GET", "/futures/usdt/tickers", f"contract={contract}", ""
        )
        book = self._request(
            "GET", "/futures/usdt/order_book", f"contract={contract}&limit=50", ""
        )
        ticker_item = ticker[0] if isinstance(ticker, list) else ticker
        now = datetime.now(UTC)
        return MarketEntryGuardRequest(
            direction=request.direction,
            quantity=request.quantity,
            last_price=Decimal(str(ticker_item["last"])),
            last_price_observed_at=now,
            asks=[
                OrderBookLevel(
                    price=Decimal(str(level["p"])),
                    quantity=Decimal(str(level["s"])),
                    observed_at=now,
                )
                for level in book.get("asks", [])
            ],
            bids=[
                OrderBookLevel(
                    price=Decimal(str(level["p"])),
                    quantity=Decimal(str(level["s"])),
                    observed_at=now,
                )
                for level in book.get("bids", [])
            ],
        )

    def set_protection_enabled(
        self, mode: TradingMode, protection: str, enabled: bool
    ) -> ExchangeOperationResult:
        return ExchangeOperationResult(
            accepted=False,
            client_request_id=f"set-{protection}",
            message_ar="تعديل حماية Gate.io يتطلب تحققاً خارجياً.",
        )

    @staticmethod
    def _orders_disabled(client_request_id: str) -> ExchangeOperationResult:
        return ExchangeOperationResult(
            accepted=False,
            client_request_id=client_request_id,
            message_ar="إرسال أوامر Gate.io معطّل افتراضياً.",
        )

    def _request(self, method: str, path: str, query: str, body: str) -> dict[str, Any]:
        if not self._allow_network or self._transport is None:
            raise RuntimeError("Gate.io network access is disabled.")
        timestamp = str(int(time()))
        return self._transport(
            method,
            f"{self._configuration.base_url}{path}",
            query,
            self.signed_headers(method, path, query, body, timestamp),
            body,
        )

    def _require_mode(self, mode: TradingMode) -> None:
        if mode != self._configuration.mode:
            raise ValueError("Gate.io adapter mode mismatch.")


def _gate_trail_order_rows(payload: object) -> list[dict[str, Any]]:
    """Normalize Gate trail-list envelopes without exposing raw payloads."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    orders = payload.get("orders")
    if isinstance(orders, list):
        return [item for item in orders if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("orders"), list):
        return [item for item in data["orders"] if isinstance(item, dict)]
    return []


def _gate_position_has_tp_sl(
    position: dict[str, Any], price_orders: object
) -> bool:
    if not isinstance(price_orders, list):
        return False
    contract = str(position.get("contract", ""))
    size = Decimal(str(position.get("size", "0")))
    if not contract or size == 0:
        return True
    required_rules = {1, 2}
    observed_rules: set[int] = set()
    expected_types = (
        {"close-long-order", "close-long-position", "plan-close-long-position"}
        if size > 0
        else {"close-short-order", "close-short-position", "plan-close-short-position"}
    )
    for item in price_orders:
        if not isinstance(item, dict) or item.get("status") not in {"open", "inactive"}:
            continue
        initial = item.get("initial")
        trigger = item.get("trigger")
        if not isinstance(initial, dict) or not isinstance(trigger, dict):
            continue
        if str(initial.get("contract", "")) != contract:
            continue
        if item.get("order_type") not in expected_types:
            continue
        try:
            observed_rules.add(int(trigger.get("rule")))
        except (TypeError, ValueError):
            continue
    return required_rules.issubset(observed_rules)


def entry_blocks(
    snapshot: ExchangeSnapshot | None,
    emergency_stop_or_mode: bool | TradingMode,
    *legacy_flags: bool,
) -> tuple[str, ...]:
    """Return Arabic operator reasons; accept the pre-refactor internal call shape."""
    emergency_stop = (
        legacy_flags[-1] if legacy_flags else bool(emergency_stop_or_mode)
    )
    reasons: list[str] = []
    if emergency_stop:
        reasons.append("الإيقاف الطارئ نشط ويمنع أي دخول جديد.")
    if snapshot is None:
        reasons.append("لم تكتمل المصالحة مع Gate.io.")
        return tuple(reasons)
    if snapshot.unmanaged_state:
        reasons.append(
            "توجد حالة Exchange غير مُدارة؛ عالجها في Gate.io ثم حدّث المصالحة."
        )
    if snapshot.position_quantity != Decimal("0"):
        reasons.append("يوجد مركز قائم؛ يمنع ذلك أي دخول جديد.")
    if snapshot.reconciliation_error:
        reasons.append("توجد مشكلة مصالحة تمنع الدخول الجديد.")
    if not snapshot.one_way_confirmed:
        reasons.append("لم يتم تأكيد وضع One-way.")
    if not snapshot.cross_margin_confirmed:
        reasons.append("لم يتم تأكيد Cross margin.")
    if snapshot.leverage_confirmed not in (1, 5, 10):
        reasons.append("لم يتم تأكيد الرافعة المالية المدعومة.")
    if not snapshot.market_ready or not snapshot.history_ready:
        reasons.append("بيانات السوق أو التاريخ غير جاهزة أو قديمة.")
    if not snapshot.risk_ready or not snapshot.daily_baseline_ready:
        reasons.append("حالة المخاطر اليومية أو خط الأساس غير جاهزة.")
    if not snapshot.active_contract_ready:
        reasons.append("لم يتم اختيار عقد تداول نشط.")
    if snapshot.market_observed_at is None or datetime.now(
        UTC
    ) - snapshot.market_observed_at > timedelta(seconds=10):
        reasons.append("آخر بيانات سوق أقدم من عشر ثوانٍ.")
    if not snapshot.subscription_confirmed or not snapshot.rest_snapshot_confirmed:
        reasons.append("لم يكتمل تأكيد اشتراك السوق ولقطة REST.")
    if snapshot.websocket_price_updates < 2:
        reasons.append("يلزم تحديثان أحدث من WebSocket بعد الاتصال.")
    if not snapshot.protection_ready:
        reasons.append("حماية المركز تحتاج إلى مصالحة أو استعادة.")
    return tuple(reasons)


def mode_state(
    mode: TradingMode,
    snapshot: ExchangeSnapshot | None,
    emergency_stop: bool,
) -> ModeState:
    reasons = entry_blocks(snapshot, emergency_stop)
    return ModeState(
        mode=mode,
        emergency_stop=emergency_stop,
        can_enter=not reasons,
        blocked_reasons_ar=reasons,
        snapshot=snapshot,
    )
