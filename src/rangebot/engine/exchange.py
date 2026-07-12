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

from rangebot.domain.exchange import (
    ExchangeEntryRequest,
    ExchangeOperationResult,
    ExchangeSnapshot,
    ModeState,
    TradingMode,
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

    def submit_entry(self, mode: TradingMode, request: ExchangeEntryRequest) -> ExchangeOperationResult:
        return self._unavailable(request.client_request_id)

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("cancel-managed-entry")

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("close-managed-position")

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        return self._unavailable("ensure-protection")

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
        self.pending_request_id: str | None = None
        self.protection_confirmed = True
        self.subscription_confirmed = True
        self.rest_snapshot_confirmed = True
        self.websocket_price_updates = 2
        self.market_observed_at = datetime.now(UTC)
        self.submissions: dict[str, ExchangeOperationResult] = {}

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=Decimal("1000"),
            position_quantity=self.position_quantity,
            managed_order_ids=(self.pending_request_id,) if self.pending_request_id else (),
            unmanaged_state=False,
            one_way_confirmed=True,
            cross_margin_confirmed=True,
            leverage_confirmed=5,
            market_ready=True,
            history_ready=True,
            protection_ready=self.protection_confirmed,
            subscription_confirmed=self.subscription_confirmed,
            rest_snapshot_confirmed=self.rest_snapshot_confirmed,
            websocket_price_updates=self.websocket_price_updates,
            market_observed_at=self.market_observed_at,
        )

    def submit_entry(self, mode: TradingMode, request: ExchangeEntryRequest) -> ExchangeOperationResult:
        prior = self.submissions.get(request.client_request_id)
        if prior is not None:
            return prior
        if self.position_quantity != 0 or self.pending_request_id is not None:
            return ExchangeOperationResult(accepted=False, client_request_id=request.client_request_id, message_ar="يوجد مركز أو أمر دخول مُدار قائم.")
        self.position_quantity = request.quantity
        self.protection_confirmed = request.protections_enabled
        result = ExchangeOperationResult(accepted=True, client_request_id=request.client_request_id, order_id=f"mock-{request.client_request_id}", message_ar="تمت تعبئة محاكاة الأمر المُدار.")
        self.submissions[request.client_request_id] = result
        return result

    def apply_partial_fill(self, quantity: Decimal) -> None:
        if quantity <= 0 or quantity > self.position_quantity:
            raise ValueError("Partial fill must be within the managed position.")
        self.position_quantity = quantity
        self.protection_confirmed = True

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        self.pending_request_id = None
        return ExchangeOperationResult(accepted=True, client_request_id="cancel", message_ar="تم إلغاء أمر الدخول المُدار.")

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        self.position_quantity = Decimal("0")
        self.protection_confirmed = True
        return ExchangeOperationResult(accepted=True, client_request_id="close", message_ar="تم إغلاق المركز المُدار بالكامل.")

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        self.protection_confirmed = self.position_quantity == 0 or self.protection_confirmed
        return ExchangeOperationResult(accepted=self.protection_confirmed, client_request_id="protection", message_ar="تم التحقق من حماية المركز المُدار.")


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
            base_url=endpoints.testnet_base_url if mode == "testnet" else endpoints.live_base_url,
        )

    def redacted_description(self) -> str:
        return f"{self.mode} Gate.io configuration ({self.key[:3]}…[REDACTED])"


class GateIoV4Adapter:
    """Signed Gate v4 futures adapter; network/order access is explicitly opt-in."""

    def __init__(
        self,
        configuration: GateIoConfiguration,
        transport: Callable[[str, str, dict[str, str], str], dict[str, Any]] | None = None,
        allow_network: bool = False,
        allow_order_submission: bool = False,
    ) -> None:
        self._configuration = configuration
        self._transport = transport
        self._allow_network = allow_network
        self._allow_order_submission = allow_order_submission

    def signed_headers(self, method: str, path: str, query: str, body: str, timestamp: str) -> dict[str, str]:
        payload_hash = hashlib.sha512(body.encode("utf-8")).hexdigest()
        signing_string = "\n".join((method.upper(), f"/api/v4{path}", query, payload_hash, timestamp))
        signature = hmac.new(self._configuration.secret.encode("utf-8"), signing_string.encode("utf-8"), hashlib.sha512).hexdigest()
        return {"Accept": "application/json", "Content-Type": "application/json", "KEY": self._configuration.key, "Timestamp": timestamp, "SIGN": signature}

    def reconcile(self, mode: TradingMode) -> ExchangeSnapshot:
        self._require_mode(mode)
        account = self._request("GET", "/futures/usdt/accounts", "", "")
        positions = self._request("GET", "/futures/usdt/positions", "", "")
        orders = self._request("GET", "/futures/usdt/orders", "status=open", "")
        position_quantity = sum(
            (abs(Decimal(str(item.get("size", "0")))) for item in positions),
            Decimal("0"),
        )
        return ExchangeSnapshot(
            mode=mode,
            reconciled_at=datetime.now(UTC),
            available_futures_balance=str(account.get("available", "0")),
            position_quantity=str(position_quantity),
            managed_order_ids=tuple(str(item["id"]) for item in orders if str(item.get("text", "")).startswith("t-rangebot-")),
            unmanaged_state=bool(positions)
            or any(
                not str(item.get("text", "")).startswith("t-rangebot-")
                for item in orders
            ),
            one_way_confirmed=True,
            cross_margin_confirmed=True,
            leverage_confirmed=5,
            market_ready=False,
            history_ready=False,
            protection_ready=True,
        )

    def submit_entry(self, mode: TradingMode, request: ExchangeEntryRequest) -> ExchangeOperationResult:
        self._require_mode(mode)
        if not self._allow_order_submission:
            return ExchangeOperationResult(accepted=False, client_request_id=request.client_request_id, message_ar="إرسال أوامر Gate.io معطّل افتراضياً.")
        payload = {"contract": request.symbol, "size": str(request.quantity), "price": "0" if request.order_type == "market" else str(request.limit_price), "tif": "ioc" if request.order_type == "market" else "gtc", "text": f"t-rangebot-{request.client_request_id}", "reduce_only": False}
        result = self._request("POST", "/futures/usdt/orders", "", json.dumps(payload, separators=(",", ":")))
        return ExchangeOperationResult(accepted=True, client_request_id=request.client_request_id, order_id=str(result.get("id")), message_ar="تم قبول أمر مُدار.")

    def cancel_managed_entry(self, mode: TradingMode) -> ExchangeOperationResult:
        return ExchangeOperationResult(accepted=False, client_request_id="cancel", message_ar="إلغاء Gate.io يتطلب مصالحة محددة بالمعرّف المُدار.")

    def close_managed_position(self, mode: TradingMode) -> ExchangeOperationResult:
        return ExchangeOperationResult(accepted=False, client_request_id="close", message_ar="الإغلاق Gate.io يتطلب مصالحة كمية حديثة.")

    def ensure_protection(self, mode: TradingMode) -> ExchangeOperationResult:
        return ExchangeOperationResult(accepted=False, client_request_id="protection", message_ar="حماية Gate.io تتطلب بيانات تعبئة فعلية.")

    def _request(self, method: str, path: str, query: str, body: str) -> dict[str, Any]:
        if not self._allow_network or self._transport is None:
            raise RuntimeError("Gate.io network access is disabled.")
        timestamp = str(int(time()))
        return self._transport(method, path, self.signed_headers(method, path, query, body, timestamp), body)

    def _require_mode(self, mode: TradingMode) -> None:
        if mode != self._configuration.mode:
            raise ValueError("Gate.io adapter mode mismatch.")


def entry_blocks(snapshot: ExchangeSnapshot | None, mode: TradingMode, live_locked: bool, emergency_stop: bool) -> tuple[str, ...]:
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
        reasons.append("توجد حالة Exchange غير مُدارة؛ عالجها في Gate.io ثم حدّث المصالحة.")
    if snapshot.position_quantity != Decimal("0"):
        reasons.append("يوجد مركز قائم؛ يمنع ذلك أي دخول جديد.")
    if snapshot.reconciliation_error:
        reasons.append("توجد مشكلة مصالحة تمنع الدخول الجديد.")
    if not snapshot.one_way_confirmed:
        reasons.append("لم يتم تأكيد وضع One-way.")
    if not snapshot.cross_margin_confirmed:
        reasons.append("لم يتم تأكيد Cross margin.")
    if not snapshot.market_ready or not snapshot.history_ready:
        reasons.append("بيانات السوق أو التاريخ غير جاهزة أو قديمة.")
    if (
        snapshot.market_observed_at is None
        or datetime.now(UTC) - snapshot.market_observed_at > timedelta(seconds=10)
    ):
        reasons.append("آخر بيانات سوق أقدم من عشر ثوانٍ.")
    if not snapshot.subscription_confirmed or not snapshot.rest_snapshot_confirmed:
        reasons.append("لم يكتمل تأكيد اشتراك السوق ولقطة REST.")
    if snapshot.websocket_price_updates < 2:
        reasons.append("يلزم تحديثان أحدث من WebSocket بعد الاتصال.")
    if not snapshot.protection_ready:
        reasons.append("حماية المركز تحتاج إلى مصالحة أو استعادة.")
    return tuple(reasons)


def mode_state(mode: TradingMode, snapshot: ExchangeSnapshot | None, live_locked: bool, emergency_stop: bool) -> ModeState:
    reasons = entry_blocks(snapshot, mode, live_locked, emergency_stop)
    return ModeState(mode=mode, live_locked=live_locked, emergency_stop=emergency_stop, can_enter=not reasons, blocked_reasons_ar=reasons, snapshot=snapshot)
