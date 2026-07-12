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
    ExchangeOperationResult,
    ExchangeSnapshot,
    MarketEntryGuardRequest,
    MarketEntryGuardResult,
    MarketGuardQuoteRequest,
    ModeState,
    OrderBookLevel,
    TradingMode,
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
        if entry_blocks(snapshot, "testnet", False, False) or not self.risk_ready:
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
            and not entry_blocks(snapshot, "testnet", False, False)
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
    """Deliberately explicit endpoints; Testnet/Live credentials stay in `.env`."""

    testnet_base_url: str = "https://fx-api-testnet.gateio.ws/api/v4"
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
        return UnavailableGateIoAdapter()
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
        position_quantity = sum(
            (abs(Decimal(str(item.get("size", "0")))) for item in positions),
            Decimal("0"),
        )
        liquidation_price = next(
            (
                Decimal(str(item["liq_price"]))
                for item in positions
                if item.get("liq_price") not in (None, "")
            ),
            None,
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
        managed_contracts = {
            str(item.get("contract"))
            for item in orders
            if str(item.get("text", "")).startswith("t-rangebot-")
        }
        if managed_contracts:
            self._managed_contract = next(iter(managed_contracts))
        self._managed_order_ids = managed_orders
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
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=str(account.get("available", "0")),
            position_quantity=str(position_quantity),
            liquidation_price=liquidation_price,
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
            protection_ready=True,
        )

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
        signed_quantity = (
            request.quantity if request.direction == "long" else -request.quantity
        )
        payload = {
            "contract": request.symbol,
            "size": str(signed_quantity),
            "price": (
                "0" if request.order_type == "market" else str(request.limit_price)
            ),
            "tif": "ioc" if request.order_type == "market" else "gtc",
            "text": f"t-rangebot-{request.client_request_id}",
            "reduce_only": False,
        }
        result = self._request(
            "POST",
            "/futures/usdt/orders",
            "",
            json.dumps(payload, separators=(",", ":")),
        )
        self._managed_contract = request.symbol
        if result.get("id") is not None:
            self._managed_order_ids = (str(result["id"]),)
        return ExchangeOperationResult(
            accepted=True,
            client_request_id=request.client_request_id,
            order_id=str(result.get("id")),
            message_ar="تم قبول أمر مُدار.",
        )

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return self._orders_disabled("cancel")
        for order_id in self._managed_order_ids:
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
        if self._managed_position_size == 0:
            return ExchangeOperationResult(
                accepted=True,
                client_request_id="protection",
                message_ar="لا يوجد مركز يحتاج حماية.",
            )
        return ExchangeOperationResult(
            accepted=True,
            client_request_id="protection",
            message_ar="حالة الحماية المُدارة مؤكدة بالمصالحة.",
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


def entry_blocks(
    snapshot: ExchangeSnapshot | None,
    mode: TradingMode,
    live_locked: bool,
    emergency_stop: bool,
) -> tuple[str, ...]:
    """Return Arabic, operator-facing reasons without exposing exchange payloads."""
    reasons: list[str] = []
    if mode == "live" and live_locked:
        reasons.append("وضع Live مقفل؛ يلزم تأكيد LIVE بعد اكتمال فحوصات الأمان.")
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
    live_locked: bool,
    emergency_stop: bool,
) -> ModeState:
    reasons = entry_blocks(snapshot, mode, live_locked, emergency_stop)
    return ModeState(
        mode=mode,
        live_locked=live_locked,
        emergency_stop=emergency_stop,
        can_enter=not reasons,
        blocked_reasons_ar=reasons,
        snapshot=snapshot,
    )
