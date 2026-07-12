"""Gate.io adapter boundary and durable safety policy for exchange-backed modes."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

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

    @staticmethod
    def _unavailable(client_request_id: str) -> ExchangeOperationResult:
        return ExchangeOperationResult(
            accepted=False,
            client_request_id=client_request_id,
            message_ar="لا يوجد adapter Gate.io مهيأ؛ لم يُرسل أي أمر.",
        )


@dataclass(frozen=True)
class GateIoV4Endpoints:
    """Deliberately explicit endpoints; Testnet/Live credentials stay in `.env`."""

    testnet_base_url: str = "https://fx-api-testnet.gateio.ws/api/v4"
    live_base_url: str = "https://api.gateio.ws/api/v4"


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
