"""Persistence for the engine's minimal lifecycle snapshot."""

import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.runtime import RuntimeState
from rangebot.domain.paper import (
    PaperAccountChange,
    PaperAccountSnapshot,
    PaperAuditEntry,
    PaperAutomaticLimitRequest,
    PaperAutomaticSignalRequest,
    PaperCloseRequest,
    PaperCloseResult,
    PaperEmergencyState,
    PaperEmergencyStopRequest,
    PaperMarketEntryRequest,
    PaperMarketEntryResult,
    PaperFeeSchedule,
    PaperHelpTopic,
    PaperLimitCheck,
    PaperLimitCheckResult,
    PaperLimitEntryRequest,
    PaperPendingEntry,
    PaperPosition,
    PaperProfile,
    PaperProfileApplyResult,
    PaperProfileChange,
    PaperProtection,
    PaperProtectionCheck,
    PaperProtectionTriggerResult,
    PaperResumeRequest,
    PaperRiskAdjustment,
    PaperRiskSettings,
    PaperRiskSnapshot,
    PaperUsedSignal,
    PaperVerificationRecord,
    PaperVerificationRequest,
)
from rangebot.domain.entry_preview import create_entry_preview, preview_is_current
from rangebot.domain.market import PaperWatchlist, WatchlistItem


RIYADH = timezone(timedelta(hours=3), "Asia/Riyadh")
MONEY_SCALE = Decimal("0.00000001")
ENGINE_BUILD_ID = "0.1.0"


class Base(DeclarativeBase):
    pass


class RuntimeStateRecord(Base):
    __tablename__ = "runtime_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    state_revision: Mapped[int] = mapped_column(Integer, nullable=False)


class RuntimeStateRepository:
    """Stores a single engine-owned lifecycle state record."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def record_started(self) -> RuntimeState:
        now = datetime.now(UTC)
        with Session(self._database_engine) as session:
            record = session.get(RuntimeStateRecord, 1)
            if record is None:
                record = RuntimeStateRecord(
                    id=1,
                    lifecycle="running",
                    started_at=now,
                    last_heartbeat_at=now,
                    state_revision=1,
                )
                session.add(record)
            else:
                record.lifecycle = "running"
                record.started_at = now
                record.last_heartbeat_at = now
                record.state_revision += 1
            session.commit()
            return self._to_domain(record)

    def record_heartbeat(self) -> None:
        with Session(self._database_engine) as session:
            record = session.get(RuntimeStateRecord, 1)
            if record is None:
                raise RuntimeError("Engine runtime state has not been initialized.")
            record.last_heartbeat_at = datetime.now(UTC)
            session.commit()

    def get_state(self) -> RuntimeState:
        with Session(self._database_engine) as session:
            record = session.scalar(
                select(RuntimeStateRecord).where(RuntimeStateRecord.id == 1)
            )
            if record is None:
                raise RuntimeError("Engine runtime state has not been initialized.")
            return self._to_domain(record)

    @staticmethod
    def _to_domain(record: RuntimeStateRecord) -> RuntimeState:
        started_at = record.started_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        return RuntimeState(
            lifecycle=record.lifecycle,
            started_at=started_at,
            last_heartbeat_at=RuntimeStateRepository._with_utc(
                record.last_heartbeat_at
            ),
            state_revision=record.state_revision,
        )

    @staticmethod
    def _with_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class PaperAccountRecord(Base):
    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    starting_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    available_futures_balance: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False
    )
    position_quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    pending_entry: Mapped[bool] = mapped_column(Boolean, nullable=False)
    protection_state: Mapped[str] = mapped_column(String(32), nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    risk_state: Mapped[str] = mapped_column(String(64), nullable=False)
    last_change_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class PaperAccountAuditRecord(Base):
    __tablename__ = "paper_account_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


class PaperPositionRecord(Base):
    __tablename__ = "paper_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    entry_fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    allocated_margin: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    taker_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, default=Decimal("0.001")
    )
    maker_fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(24, 8), nullable=False, default=Decimal("0.001")
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaperProtectionRecord(Base):
    __tablename__ = "paper_protection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    take_profit_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    stop_loss_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    warning: Mapped[str | None] = mapped_column(String(500))


class PaperFeeScheduleRecord(Base):
    __tablename__ = "paper_fee_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    maker_fee_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    taker_fee_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)


class PaperPendingEntryRecord(Base):
    __tablename__ = "paper_pending_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    allocated_margin: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    limit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    taker_fee_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    maker_fee_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    entry_fee_rate: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_zone: Mapped[str | None] = mapped_column(String(200))
    signal_symbol: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PaperRiskStateRecord(Base):
    __tablename__ = "paper_risk_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    baseline_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    realized_net_loss: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    losing_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_fills: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    losing_trade_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_fill_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False)


class PaperEmergencyStopRecord(Base):
    __tablename__ = "paper_emergency_stop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    automatic_trading_requires_restart: Mapped[bool] = mapped_column(
        Boolean, nullable=False
    )


class PaperUsedSignalRecord(Base):
    __tablename__ = "paper_used_signal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    trigger_zone: Mapped[str] = mapped_column(String(200), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reset_seen: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PaperProfileRecord(Base):
    __tablename__ = "paper_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    safety_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)


class PaperActiveProfileRecord(Base):
    __tablename__ = "paper_active_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int | None] = mapped_column(Integer)


class PaperVerificationRecordRow(Base):
    __tablename__ = "paper_verification_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_build: Mapped[str] = mapped_column(String(200), nullable=False)
    safety_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)


class PaperAccountRepository:
    """Persists state belonging exclusively to the local Paper Account."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def get(self) -> PaperAccountSnapshot:
        with Session(self._database_engine) as session:
            record = session.get(PaperAccountRecord, 1)
            if record is None:
                raise LookupError("Paper Account has not been initialized.")
            return self._to_snapshot(record)

    def initialize(self, change: PaperAccountChange) -> PaperAccountSnapshot:
        with Session(self._database_engine) as session:
            if session.get(PaperAccountRecord, 1) is not None:
                raise ValueError("Paper Account is already initialized.")
            record = self._new_record(change)
            session.add(record)
            session.add(
                PaperFeeScheduleRecord(
                    id=1,
                    maker_fee_rate=Decimal("0.001"),
                    taker_fee_rate=Decimal("0.001"),
                )
            )
            session.add(self._new_risk_state(record.available_futures_balance))
            session.add(
                PaperEmergencyStopRecord(
                    id=1,
                    active=False,
                    reason=None,
                    activated_at=None,
                    automatic_trading_requires_restart=False,
                )
            )
            self._audit(session, "initialized", change.reason)
            session.commit()
            return self._to_snapshot(record)

    def reset(self, change: PaperAccountChange) -> PaperAccountSnapshot:
        with Session(self._database_engine) as session:
            existing = session.get(PaperAccountRecord, 1)
            if existing is None:
                raise LookupError("Paper Account has not been initialized.")
            if existing.position_quantity != Decimal("0") or existing.pending_entry:
                self._audit(session, "reset_rejected", change.reason)
                session.commit()
                raise RuntimeError(
                    "Paper Account has an open position or pending entry."
                )
            replacement = self._new_record(change, revision=existing.revision + 1)
            session.delete(existing)
            session.flush()
            session.add(replacement)
            risk = self._risk_state(session, replacement)
            risk.day = self._riyadh_day()
            risk.baseline_balance = replacement.available_futures_balance
            risk.realized_net_loss = Decimal("0")
            risk.losing_trades = 0
            risk.automatic_fills = 0
            self._audit(session, "reset", change.reason)
            session.commit()
            return self._to_snapshot(replacement)

    def audit_entries(self) -> list[PaperAuditEntry]:
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(PaperAccountAuditRecord).order_by(PaperAccountAuditRecord.id)
            )
            return [
                PaperAuditEntry(
                    occurred_at=RuntimeStateRepository._with_utc(record.occurred_at),
                    action=record.action,
                    reason=record.reason,
                )
                for record in records
            ]

    def set_position_quantity(self, quantity: Decimal) -> None:
        """Internal state seam used by later Paper execution workflows and tests."""
        if quantity < 0:
            raise ValueError("Paper position quantity cannot be negative.")
        with Session(self._database_engine) as session:
            record = session.get(PaperAccountRecord, 1)
            if record is None:
                raise LookupError("Paper Account has not been initialized.")
            record.position_quantity = quantity
            record.revision += 1
            session.commit()

    def close_position(self, request: PaperCloseRequest) -> PaperCloseResult:
        """Cancel simulated protection and close the exact remaining Paper quantity."""
        if request.confirmation != "CLOSE PAPER POSITION":
            raise ValueError("Explicit Paper close confirmation required.")
        with Session(self._database_engine) as session:
            position = session.get(PaperPositionRecord, 1)
            account = session.get(PaperAccountRecord, 1)
            if position is None or account is None:
                raise LookupError("Paper Account has no open position.")
            protection = session.get(PaperProtectionRecord, 1)
            if protection is not None:
                session.delete(protection)
            result = self._close_position_record(
                session,
                account,
                position,
                request.market_price,
                "manual_close",
                "تم إغلاق مركز Paper يدويا بعد إلغاء أوامر الحماية المحلية.",
                position.taker_fee_rate,
            )
            self._start_cooldown(session, account)
            session.commit()
            return result

    def cancel_pending_entry(self) -> PaperAccountSnapshot:
        """Cancel a managed Paper pending entry without touching open positions."""
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            pending = session.get(PaperPendingEntryRecord, 1)
            if pending is None:
                raise LookupError("Paper Account has no pending entry.")
            session.delete(pending)
            account.pending_entry = False
            account.last_change_reason = "Paper pending entry cancelled"
            account.revision += 1
            self._audit(
                session,
                "pending_entry_cancelled",
                "تم إلغاء أمر الدخول المعلق في Paper دون تغيير أي مركز مفتوح.",
            )
            session.commit()
            return self._to_snapshot(account)

    def pending_entry(self) -> PaperPendingEntry:
        with Session(self._database_engine) as session:
            record = session.get(PaperPendingEntryRecord, 1)
            if record is None:
                raise LookupError("Paper Account has no pending entry.")
            return self._to_pending_entry(record)

    def create_limit_entry(self, request: PaperLimitEntryRequest) -> PaperLimitCheckResult:
        """Create one full-or-none Paper Limit entry without placing any exchange order."""
        if request.confirmation != "CONFIRM PAPER LIMIT ENTRY":
            raise ValueError("Explicit Paper Limit-entry confirmation required.")
        if not preview_is_current(request.preview, request.current_request):
            raise ValueError("Paper Entry Preview is stale.")
        recalculated = create_entry_preview(request.current_request)
        if not recalculated.can_submit:
            raise ValueError("Paper Limit entry is blocked by allocation safeguards.")
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            self._assert_entry_allowed(session, account, automatic=False)
            fee_schedule = self._fee_schedule(session)
            if (
                request.current_request.taker_fee_rate is not None
                and request.current_request.taker_fee_rate != fee_schedule.taker_fee_rate
            ):
                raise ValueError("Paper Entry Preview is stale: fee schedule changed.")
            marketable = (
                request.limit_price >= request.placement_price
                if request.current_request.direction == "long"
                else request.limit_price <= request.placement_price
            )
            entry_fee_rate = (
                fee_schedule.taker_fee_rate if marketable else fee_schedule.maker_fee_rate
            )
            pending = PaperPendingEntryRecord(
                id=1,
                kind="limit",
                direction=request.current_request.direction,
                quantity=recalculated.quantity,
                allocated_margin=recalculated.allocated_margin,
                limit_price=request.limit_price,
                leverage=request.current_request.leverage,
                taker_fee_rate=fee_schedule.taker_fee_rate,
                maker_fee_rate=fee_schedule.maker_fee_rate,
                entry_fee_rate=entry_fee_rate,
                expires_at=request.expires_at,
                signal_zone=request.signal_zone,
                signal_symbol=request.signal_symbol,
                created_at=datetime.now(UTC),
            )
            session.add(pending)
            account.pending_entry = True
            account.last_change_reason = "Paper Limit entry pending"
            account.revision += 1
            self._audit(
                session,
                "limit_entry_pending",
                "تم إنشاء أمر Paper Limit محلي وينتظر تحقق السعر أو انتهاء الصلاحية.",
            )
            session.commit()
            return PaperLimitCheckResult(
                filled=False,
                expired=False,
                account=self._to_snapshot(account),
                pending_entry=self._to_pending_entry(pending),
            )

    def check_limit_entry(self, check: PaperLimitCheck) -> PaperLimitCheckResult:
        """Fill or expire a pending Paper Limit order, fully or not at all."""
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            pending = session.get(PaperPendingEntryRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            if pending is None:
                raise LookupError("Paper Account has no pending entry.")
            observed_at = RuntimeStateRepository._with_utc(check.observed_at)
            expires_at = RuntimeStateRepository._with_utc(pending.expires_at)
            if observed_at >= expires_at:
                signal_zone = pending.signal_zone
                direction = pending.direction
                session.delete(pending)
                account.pending_entry = False
                account.last_change_reason = "Paper Limit entry expired"
                account.revision += 1
                if signal_zone is not None:
                    self._record_used_signal(
                        session, pending.signal_symbol or "ACTIVE", direction, signal_zone
                    )
                self._audit(
                    session,
                    "limit_entry_expired",
                    "انتهت صلاحية أمر Paper Limit وتم إلغاؤه محليا.",
                )
                session.commit()
                return PaperLimitCheckResult(
                    filled=False,
                    expired=True,
                    account=self._to_snapshot(account),
                    activity="انتهت صلاحية أمر Paper Limit.",
                )
            should_fill = (
                check.market_price <= pending.limit_price
                if pending.direction == "long"
                else check.market_price >= pending.limit_price
            )
            if not should_fill:
                return PaperLimitCheckResult(
                    filled=False,
                    expired=False,
                    account=self._to_snapshot(account),
                    pending_entry=self._to_pending_entry(pending),
                )
            entry_fee = pending.quantity * pending.limit_price * pending.entry_fee_rate
            total_debit = pending.allocated_margin + entry_fee
            if total_debit > account.available_futures_balance:
                raise ValueError("Paper Limit fill exceeds available balance.")
            position = PaperPositionRecord(
                id=1,
                direction=pending.direction,
                quantity=pending.quantity,
                entry_price=pending.limit_price,
                entry_fee=entry_fee,
                allocated_margin=pending.allocated_margin,
                leverage=pending.leverage,
                taker_fee_rate=pending.taker_fee_rate,
                maker_fee_rate=pending.maker_fee_rate,
                opened_at=observed_at,
            )
            session.add(position)
            take_profit, stop_loss = self._protection_prices(position)
            session.add(
                PaperProtectionRecord(
                    id=1,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                    quantity=pending.quantity,
                    state="protected",
                    warning=None,
                )
            )
            if pending.signal_zone is not None:
                self._record_used_signal(
                    session,
                    pending.signal_symbol or "ACTIVE",
                    pending.direction,
                    pending.signal_zone,
                )
            session.delete(pending)
            account.pending_entry = False
            account.position_quantity = position.quantity
            account.protection_state = "protected"
            account.available_futures_balance -= total_debit
            account.last_change_reason = "Paper Limit entry filled"
            account.revision += 1
            self._record_risk_result(session, account, Decimal("0"), entry_fee, True)
            activity = (
                "تم تنفيذ أمر Paper Limit بالكامل برسوم Taker."
                if pending.entry_fee_rate == pending.taker_fee_rate
                else "تم تنفيذ أمر Paper Limit بالكامل برسوم Maker."
            )
            self._audit(session, "limit_entry_filled", activity)
            session.commit()
            return PaperLimitCheckResult(
                filled=True,
                expired=False,
                account=self._to_snapshot(account),
                position=self._to_position(position),
                activity=activity,
            )

    def risk_snapshot(self) -> PaperRiskSnapshot:
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            risk = self._risk_state(session, account)
            session.commit()
            return self._to_risk_snapshot(risk, account)

    def update_risk_settings(self, settings: PaperRiskSettings) -> PaperRiskSnapshot:
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            risk = self._risk_state(session, account)
            risk.daily_loss_limit = settings.daily_loss_limit
            risk.losing_trade_limit = settings.losing_trade_limit
            risk.automatic_fill_limit = settings.automatic_fill_limit
            risk.cooldown_seconds = settings.cooldown_seconds
            self._sync_risk_state(account, risk)
            session.commit()
            return self._to_risk_snapshot(risk, account)

    def adjust_risk(self, adjustment: PaperRiskAdjustment) -> PaperRiskSnapshot:
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            self._record_risk_result(
                session,
                account,
                adjustment.realized_pnl,
                adjustment.fees + adjustment.funding,
                adjustment.automatic_fill,
            )
            risk = self._risk_state(session, account)
            session.commit()
            return self._to_risk_snapshot(risk, account)

    def automatic_market_entry(
        self, request: PaperAutomaticSignalRequest
    ) -> PaperMarketEntryResult:
        if not request.market_ready or not request.history_ready:
            raise ValueError("Automatic Paper entry requires fresh market and history data.")
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            self._assert_entry_allowed(session, account, automatic=True)
            if self._used_signal_exists(
                session, request.symbol, request.direction, request.trigger_zone
            ):
                raise RuntimeError("Paper automatic signal is already used.")
            self._record_used_signal(
                session, request.symbol, request.direction, request.trigger_zone
            )
            risk = self._risk_state(session, account)
            risk.automatic_fills += 1
            self._sync_risk_state(account, risk)
            session.commit()
        entry_request = PaperMarketEntryRequest(
            preview=request.preview,
            current_request=request.current_request,
            confirmation="CONFIRM PAPER MARKET ENTRY",
            market_ready=request.market_ready,
            history_ready=request.history_ready,
        )
        result = self.enter_market(entry_request)
        return result.model_copy(
            update={
                "activity": "تم فتح مركز Paper تلقائيا وتم حفظ الإشارة كمستخدمة."
            }
        )

    def automatic_limit_entry(
        self, request: PaperAutomaticLimitRequest
    ) -> PaperLimitCheckResult:
        if not request.market_ready or not request.history_ready:
            raise ValueError("Automatic Paper Limit requires fresh market and history data.")
        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            self._assert_entry_allowed(session, account, automatic=True)
            if self._used_signal_exists(
                session,
                request.symbol,
                request.current_request.direction,
                request.trigger_zone,
            ):
                raise RuntimeError("Paper automatic signal is already used.")
        offset = request.offset_percentage / Decimal("100")
        limit_price = (
            request.placement_price * (Decimal("1") - offset)
            if request.current_request.direction == "long"
            else request.placement_price * (Decimal("1") + offset)
        )
        return self.create_limit_entry(
            PaperLimitEntryRequest(
                preview=request.preview,
                current_request=request.current_request,
                limit_price=limit_price,
                placement_price=request.placement_price,
                expires_at=request.expires_at,
                confirmation="CONFIRM PAPER LIMIT ENTRY",
                signal_zone=request.trigger_zone,
                signal_symbol=request.symbol,
            )
        )

    def used_signals(self) -> list[PaperUsedSignal]:
        with Session(self._database_engine) as session:
            records = session.scalars(select(PaperUsedSignalRecord))
            return [self._to_used_signal(record) for record in records]

    def directional_reset(self, symbol: str, direction: str) -> list[PaperUsedSignal]:
        with Session(self._database_engine) as session:
            records = list(
                session.scalars(
                    select(PaperUsedSignalRecord).where(
                        PaperUsedSignalRecord.symbol == symbol,
                        PaperUsedSignalRecord.direction == direction,
                    )
                )
            )
            for record in records:
                record.reset_seen = True
            session.commit()
            return [self._to_used_signal(record) for record in records]

    def emergency_state(self) -> PaperEmergencyState:
        with Session(self._database_engine) as session:
            return self._to_emergency_state(self._emergency_state(session))

    def activate_emergency_stop(
        self, request: PaperEmergencyStopRequest
    ) -> PaperEmergencyState:
        if request.confirmation != "EMERGENCY STOP":
            raise ValueError("Explicit Emergency Stop confirmation required.")
        with Session(self._database_engine) as session:
            emergency = self._emergency_state(session)
            emergency.active = True
            emergency.reason = request.reason
            emergency.activated_at = datetime.now(UTC)
            emergency.automatic_trading_requires_restart = True
            account = session.get(PaperAccountRecord, 1)
            pending = session.get(PaperPendingEntryRecord, 1)
            if account is not None and pending is not None:
                session.delete(pending)
                account.pending_entry = False
                account.last_change_reason = "Paper Emergency Stop cancelled pending entry"
                account.revision += 1
            self._audit(
                session,
                "emergency_stop",
                "تم تفعيل إيقاف الطوارئ في Paper وإيقاف الدخولات الجديدة.",
            )
            session.commit()
            return self._to_emergency_state(emergency)

    def resume_after_emergency(self, request: PaperResumeRequest) -> PaperEmergencyState:
        if request.confirmation != "RESUME":
            raise ValueError("Type RESUME to clear Paper Emergency Stop.")
        with Session(self._database_engine) as session:
            emergency = self._emergency_state(session)
            emergency.active = False
            emergency.reason = None
            emergency.activated_at = None
            emergency.automatic_trading_requires_restart = True
            self._audit(
                session,
                "emergency_resume",
                "تم مسح إيقاف الطوارئ، ويجب تشغيل التداول التلقائي من جديد.",
            )
            session.commit()
            return self._to_emergency_state(emergency)

    def confirm_automatic_restart(self) -> None:
        with Session(self._database_engine) as session:
            emergency = self._emergency_state(session)
            if emergency.active:
                raise RuntimeError("Paper Emergency Stop blocks automatic trading.")
            emergency.automatic_trading_requires_restart = False
            session.commit()

    def emergency_close_position(self, request: PaperCloseRequest) -> PaperCloseResult:
        if request.confirmation != "EMERGENCY CLOSE PAPER POSITION":
            raise ValueError("Explicit Emergency Close confirmation required.")
        with Session(self._database_engine) as session:
            emergency = self._emergency_state(session)
            emergency.active = True
            emergency.reason = "Emergency Close Position"
            emergency.activated_at = datetime.now(UTC)
            emergency.automatic_trading_requires_restart = True
            session.commit()
        return self.close_position(
            request.model_copy(update={"confirmation": "CLOSE PAPER POSITION"})
        )

    def save_profile(self, change: PaperProfileChange) -> PaperProfile:
        with Session(self._database_engine) as session:
            settings_json, fingerprint = self._profile_payload(change.settings)
            record = PaperProfileRecord(
                name=change.name,
                settings_json=settings_json,
                safety_fingerprint=fingerprint,
            )
            session.add(record)
            self._audit(session, "profile_saved", "تم حفظ ملف إعدادات Paper بدون أسرار.")
            session.commit()
            return self._to_profile(record)

    def profiles(self) -> list[PaperProfile]:
        with Session(self._database_engine) as session:
            return [
                self._to_profile(record)
                for record in session.scalars(select(PaperProfileRecord))
            ]

    def duplicate_profile(self, profile_id: int, change: PaperProfileChange) -> PaperProfile:
        with Session(self._database_engine) as session:
            original = session.get(PaperProfileRecord, profile_id)
            if original is None:
                raise LookupError("Paper profile not found.")
            settings = json.loads(original.settings_json)
            if change.settings:
                settings.update(change.settings)
            settings_json, fingerprint = self._profile_payload(settings)
            duplicate = PaperProfileRecord(
                name=change.name,
                settings_json=settings_json,
                safety_fingerprint=fingerprint,
            )
            session.add(duplicate)
            self._audit(session, "profile_duplicated", "تم نسخ ملف إعدادات Paper.")
            session.commit()
            return self._to_profile(duplicate)

    def update_profile(self, profile_id: int, change: PaperProfileChange) -> PaperProfile:
        with Session(self._database_engine) as session:
            record = session.get(PaperProfileRecord, profile_id)
            if record is None:
                raise LookupError("Paper profile not found.")
            settings_json, fingerprint = self._profile_payload(change.settings)
            record.name = change.name
            record.settings_json = settings_json
            record.safety_fingerprint = fingerprint
            self._audit(session, "profile_updated", "تم تعديل ملف إعدادات Paper.")
            session.commit()
            return self._to_profile(record)

    def delete_profile(self, profile_id: int) -> None:
        with Session(self._database_engine) as session:
            record = session.get(PaperProfileRecord, profile_id)
            if record is None:
                raise LookupError("Paper profile not found.")
            session.delete(record)
            self._audit(session, "profile_deleted", "تم حذف ملف إعدادات Paper.")
            session.commit()

    def apply_profile(
        self, profile_id: int, change: PaperProfileChange
    ) -> PaperProfileApplyResult:
        if change.confirmation != "APPLY PAPER PROFILE":
            raise ValueError("Explicit Paper profile apply confirmation required.")
        with Session(self._database_engine) as session:
            record = session.get(PaperProfileRecord, profile_id)
            if record is None:
                raise LookupError("Paper profile not found.")
            profile = self._to_profile(record)
            summary = [f"{key}: {value}" for key, value in profile.settings.items()]
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            fee_schedule = self._fee_schedule(session)
            if "maker_fee_rate" in profile.settings:
                fee_schedule.maker_fee_rate = Decimal(
                    str(profile.settings["maker_fee_rate"])
                )
            if "taker_fee_rate" in profile.settings:
                fee_schedule.taker_fee_rate = Decimal(
                    str(profile.settings["taker_fee_rate"])
                )
            risk = self._risk_state(session, account)
            for field in (
                "daily_loss_limit",
                "losing_trade_limit",
                "automatic_fill_limit",
                "cooldown_seconds",
            ):
                if field in profile.settings:
                    setattr(risk, field, profile.settings[field])
            self._sync_risk_state(account, risk)
            active_profile = self._active_profile(session)
            active_profile.profile_id = profile.id
            activity = "تم تطبيق ملف إعدادات Paper على النشاط المستقبلي فقط."
            self._audit(session, "profile_applied", activity)
            session.commit()
            return PaperProfileApplyResult(
                profile=profile, change_summary=summary, activity=activity
            )

    def help_topics(self) -> list[PaperHelpTopic]:
        return [
            PaperHelpTopic(
                slug="modes",
                title_ar="الأوضاع",
                body_ar="Paper محاكاة محلية، وTestnet للتجربة، وLive يحتاج تأكيدات منفصلة.",
            ),
            PaperHelpTopic(
                slug="protection",
                title_ar="جني الربح ووقف الخسارة",
                body_ar="يحاكي Paper حماية TP/SL محليا ولا يرسل أوامر إلى Gate.io.",
            ),
            PaperHelpTopic(
                slug="risk",
                title_ar="المخاطر والتهدئة",
                body_ar="حدود الخسارة والصفقات الخاسرة تمنع الدخولات الجديدة فقط، بينما يبقى الإغلاق والإلغاء متاحين.",
            ),
            PaperHelpTopic(
                slug="emergency",
                title_ar="إيقاف الطوارئ",
                body_ar="إيقاف الطوارئ مستمر بعد إعادة التشغيل ولا يزول إلا بكتابة RESUME.",
            ),
        ]

    def record_verification(
        self, request: PaperVerificationRequest
    ) -> PaperVerificationRecord:
        with Session(self._database_engine) as session:
            safety_fingerprint = self._current_safety_fingerprint(session)
            existing = session.get(PaperVerificationRecordRow, 1)
            if existing is None:
                existing = PaperVerificationRecordRow(
                    id=1,
                    recorded_at=datetime.now(UTC),
                    engine_build=ENGINE_BUILD_ID,
                    safety_fingerprint=safety_fingerprint,
                    evidence=request.evidence,
                )
                session.add(existing)
            else:
                existing.recorded_at = datetime.now(UTC)
                existing.engine_build = ENGINE_BUILD_ID
                existing.safety_fingerprint = safety_fingerprint
                existing.evidence = request.evidence
            self._audit(session, "paper_verification_recorded", "تم تسجيل تحقق Paper كدليل استرشادي.")
            session.commit()
            return self._to_verification(
                existing, ENGINE_BUILD_ID, safety_fingerprint
            )

    def verification(self) -> PaperVerificationRecord:
        with Session(self._database_engine) as session:
            safety_fingerprint = self._current_safety_fingerprint(session)
            record = session.get(PaperVerificationRecordRow, 1)
            if record is None:
                now = datetime.now(UTC)
                return PaperVerificationRecord(
                    id=0,
                    recorded_at=now,
                    engine_build=ENGINE_BUILD_ID,
                    safety_fingerprint=safety_fingerprint,
                    evidence="",
                    stale=True,
                    advisory_warning_ar="تحقق Paper مفقود أو قديم، وهذا تحذير استرشادي فقط.",
                )
            return self._to_verification(record, ENGINE_BUILD_ID, safety_fingerprint)

    def enter_market(self, request: PaperMarketEntryRequest) -> PaperMarketEntryResult:
        """Create one isolated Paper position after every manual-entry safeguard."""
        if request.confirmation != "CONFIRM PAPER MARKET ENTRY":
            raise ValueError("Explicit Paper Market-entry confirmation required.")
        if not request.market_ready:
            raise ValueError("Paper Market entry is blocked: market data is not ready.")
        if not request.history_ready:
            raise ValueError("Paper Market entry is blocked: history is not ready.")
        if not preview_is_current(request.preview, request.current_request):
            raise ValueError("Paper Entry Preview is stale.")
        recalculated = create_entry_preview(request.current_request)
        if not recalculated.can_submit:
            raise ValueError("Paper Market entry is blocked by allocation safeguards.")

        with Session(self._database_engine) as session:
            account = session.get(PaperAccountRecord, 1)
            if account is None:
                raise LookupError("Paper Account has not been initialized.")
            self._assert_entry_allowed(session, account, automatic=False)
            fee_schedule = self._fee_schedule(session)
            if (
                request.current_request.taker_fee_rate is not None
                and request.current_request.taker_fee_rate != fee_schedule.taker_fee_rate
            ):
                raise ValueError("Paper Entry Preview is stale: fee schedule changed.")

            slippage_fraction = request.slippage_percentage / Decimal("100")
            if request.current_request.direction == "long":
                fill_price = recalculated.expected_entry_price * (
                    Decimal("1") + slippage_fraction
                )
            else:
                fill_price = recalculated.expected_entry_price * (
                    Decimal("1") - slippage_fraction
                )
            quantity = recalculated.quantity
            entry_fee = quantity * fill_price * (
                fee_schedule.taker_fee_rate
            )
            allocated_margin = quantity * fill_price / Decimal(
                request.current_request.leverage
            )
            total_debit = allocated_margin + entry_fee
            if total_debit + recalculated.safety_reserve > account.available_futures_balance:
                raise ValueError("Paper Market entry exceeds available balance after fill.")

            position = PaperPositionRecord(
                id=1,
                direction=request.current_request.direction,
                quantity=quantity,
                entry_price=fill_price,
                entry_fee=entry_fee,
                allocated_margin=allocated_margin,
                leverage=request.current_request.leverage,
                taker_fee_rate=fee_schedule.taker_fee_rate,
                maker_fee_rate=fee_schedule.maker_fee_rate,
                opened_at=datetime.now(UTC),
            )
            session.add(position)
            take_profit, stop_loss = self._protection_prices(position)
            session.add(
                PaperProtectionRecord(
                    id=1,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                    quantity=quantity,
                    state="protected",
                    warning=None,
                )
            )
            account.position_quantity = quantity
            account.protection_state = "protected"
            account.available_futures_balance -= total_debit
            account.last_change_reason = "Paper manual Market entry"
            account.revision += 1
            activity = "تم فتح مركز ورقي يدوي بسعر السوق بعد تأكيد المستخدم."
            self._audit(session, "manual_market_entry", activity)
            session.commit()
            snapshot = self._to_snapshot(account)
            return PaperMarketEntryResult(
                position=self._to_position(position), account=snapshot, activity=activity
            )

    def position(self) -> PaperPosition:
        with Session(self._database_engine) as session:
            record = session.get(PaperPositionRecord, 1)
            if record is None:
                raise LookupError("Paper Account has no open position.")
            return self._to_position(record)

    def protection(self) -> PaperProtection:
        with Session(self._database_engine) as session:
            record = session.get(PaperProtectionRecord, 1)
            if record is None:
                raise LookupError("Paper position has no protection.")
            return self._to_protection(record)

    def fee_schedule(self) -> PaperFeeSchedule:
        with Session(self._database_engine) as session:
            record = self._fee_schedule(session)
            return PaperFeeSchedule(
                maker_fee_rate=record.maker_fee_rate, taker_fee_rate=record.taker_fee_rate
            )

    def update_fee_schedule(self, schedule: PaperFeeSchedule) -> PaperFeeSchedule:
        """Update only future Paper trades; open positions retain their stored rates."""
        with Session(self._database_engine) as session:
            record = self._fee_schedule(session)
            record.maker_fee_rate = schedule.maker_fee_rate
            record.taker_fee_rate = schedule.taker_fee_rate
            session.commit()
            return PaperFeeSchedule(
                maker_fee_rate=record.maker_fee_rate, taker_fee_rate=record.taker_fee_rate
            )

    def check_protection(
        self, check: PaperProtectionCheck
    ) -> PaperProtectionTriggerResult:
        """Apply a deterministic Paper TP/SL trigger without exchange authority."""
        with Session(self._database_engine) as session:
            position = session.get(PaperPositionRecord, 1)
            protection = session.get(PaperProtectionRecord, 1)
            account = session.get(PaperAccountRecord, 1)
            if position is None or protection is None or account is None:
                raise LookupError("Paper position has no active protection.")
            reason: str | None = None
            exit_price: Decimal | None = None
            if position.direction == "long":
                if check.market_price >= protection.take_profit_price:
                    reason, exit_price = "take_profit", protection.take_profit_price
                elif check.market_price <= protection.stop_loss_price:
                    reason, exit_price = "stop_loss", protection.stop_loss_price
            else:
                if check.market_price <= protection.take_profit_price:
                    reason, exit_price = "take_profit", protection.take_profit_price
                elif check.market_price >= protection.stop_loss_price:
                    reason, exit_price = "stop_loss", protection.stop_loss_price
            if reason is None or exit_price is None:
                return PaperProtectionTriggerResult(
                    triggered=False, account=self._to_snapshot(account)
                )
            exit_fee_rate = (
                position.taker_fee_rate
                if reason == "stop_loss"
                else position.maker_fee_rate
            )
            exit_fee = position.quantity * exit_price * exit_fee_rate
            price_pnl = position.quantity * (exit_price - position.entry_price)
            if position.direction == "short":
                price_pnl = -price_pnl
            account.available_futures_balance += (
                position.allocated_margin + price_pnl - exit_fee
            )
            account.position_quantity = Decimal("0")
            account.protection_state = "none"
            account.last_change_reason = f"Paper {reason} triggered"
            account.revision += 1
            self._record_risk_result(
                session, account, price_pnl - position.entry_fee, exit_fee, False
            )
            activity = "تم إغلاق المركز الورقي عبر حماية جني الربح أو وقف الخسارة."
            activity = (
                "تم تنفيذ حماية جني الربح برسوم Maker."
                if reason == "take_profit"
                else "تم تنفيذ حماية وقف الخسارة برسوم Taker."
            )
            self._audit(session, reason, activity)
            session.delete(protection)
            session.delete(position)
            self._start_cooldown(session, account)
            session.commit()
            return PaperProtectionTriggerResult(
                triggered=True,
                reason=reason,
                account=self._to_snapshot(account),
                exit_fee_rate=exit_fee_rate,
                exit_fee=exit_fee,
                activity=activity,
            )

    @staticmethod
    def _protection_prices(position: PaperPositionRecord) -> tuple[Decimal, Decimal]:
        target = position.allocated_margin * Decimal("0.30")
        maximum_loss = position.allocated_margin * Decimal("0.10")
        if position.direction == "long":
            tp = (
                target + position.entry_fee + position.quantity * position.entry_price
            ) / (position.quantity * (Decimal("1") - position.maker_fee_rate))
            sl = (
                position.quantity * position.entry_price + position.entry_fee - maximum_loss
            ) / (position.quantity * (Decimal("1") - position.taker_fee_rate))
        else:
            tp = (
                position.quantity * position.entry_price - position.entry_fee - target
            ) / (position.quantity * (Decimal("1") + position.maker_fee_rate))
            sl = (
                position.quantity * position.entry_price - position.entry_fee + maximum_loss
            ) / (position.quantity * (Decimal("1") + position.taker_fee_rate))
        return tp, sl

    @staticmethod
    def _new_record(
        change: PaperAccountChange, revision: int = 1
    ) -> PaperAccountRecord:
        return PaperAccountRecord(
            id=1,
            starting_balance=change.starting_balance,
            available_futures_balance=change.starting_balance,
            position_quantity=Decimal("0"),
            pending_entry=False,
            protection_state="none",
            cooldown_until=None,
            risk_state="clear",
            last_change_reason=change.reason,
            revision=revision,
        )

    @staticmethod
    def _audit(session: Session, action: str, reason: str) -> None:
        session.add(
            PaperAccountAuditRecord(
                occurred_at=datetime.now(UTC), action=action, reason=reason
            )
        )

    @staticmethod
    def _to_snapshot(record: PaperAccountRecord) -> PaperAccountSnapshot:
        return PaperAccountSnapshot(
            starting_balance=record.starting_balance,
            available_futures_balance=record.available_futures_balance,
            position_quantity=record.position_quantity,
            pending_entry=record.pending_entry,
            protection_state=record.protection_state,
            cooldown_until=(
                RuntimeStateRepository._with_utc(record.cooldown_until)
                if record.cooldown_until
                else None
            ),
            risk_state=record.risk_state,
            last_change_reason=record.last_change_reason,
            revision=record.revision,
        )

    @staticmethod
    def _to_position(record: PaperPositionRecord) -> PaperPosition:
        return PaperPosition(
            direction=record.direction,
            quantity=record.quantity,
            entry_price=record.entry_price,
            entry_fee=record.entry_fee,
            allocated_margin=record.allocated_margin,
            leverage=record.leverage,
            taker_fee_rate=record.taker_fee_rate,
            maker_fee_rate=record.maker_fee_rate,
            opened_at=RuntimeStateRepository._with_utc(record.opened_at),
        )

    @staticmethod
    def _to_protection(record: PaperProtectionRecord) -> PaperProtection:
        return PaperProtection(
            take_profit_price=record.take_profit_price,
            stop_loss_price=record.stop_loss_price,
            quantity=record.quantity,
            state=record.state,
            warning=record.warning,
        )

    @staticmethod
    def _fee_schedule(session: Session) -> PaperFeeScheduleRecord:
        record = session.get(PaperFeeScheduleRecord, 1)
        if record is None:
            record = PaperFeeScheduleRecord(
                id=1, maker_fee_rate=Decimal("0.001"), taker_fee_rate=Decimal("0.001")
            )
            session.add(record)
            session.flush()
        return record

    @staticmethod
    def _riyadh_day(now: datetime | None = None) -> str:
        return (now or datetime.now(UTC)).astimezone(RIYADH).date().isoformat()

    @classmethod
    def _new_risk_state(cls, balance: Decimal) -> PaperRiskStateRecord:
        return PaperRiskStateRecord(
            id=1,
            day=cls._riyadh_day(),
            baseline_balance=balance,
            realized_net_loss=Decimal("0"),
            losing_trades=0,
            automatic_fills=0,
            daily_loss_limit=Decimal("100"),
            losing_trade_limit=3,
            automatic_fill_limit=10,
            cooldown_seconds=60,
        )

    @classmethod
    def _risk_state(
        cls, session: Session, account: PaperAccountRecord
    ) -> PaperRiskStateRecord:
        record = session.get(PaperRiskStateRecord, 1)
        if record is None:
            record = cls._new_risk_state(account.available_futures_balance)
            session.add(record)
            session.flush()
        if record.day != cls._riyadh_day():
            record.day = cls._riyadh_day()
            record.baseline_balance = account.available_futures_balance
            record.realized_net_loss = Decimal("0")
            record.losing_trades = 0
            record.automatic_fills = 0
        cls._sync_risk_state(account, record)
        return record

    @staticmethod
    def _sync_risk_state(
        account: PaperAccountRecord, risk: PaperRiskStateRecord
    ) -> None:
        manual_blocked = (
            risk.realized_net_loss >= risk.daily_loss_limit
            or risk.losing_trades >= risk.losing_trade_limit
        )
        automatic_blocked = manual_blocked or (
            risk.automatic_fills >= risk.automatic_fill_limit
        )
        cooldown_until = (
            RuntimeStateRepository._with_utc(account.cooldown_until)
            if account.cooldown_until
            else None
        )
        if cooldown_until is not None and cooldown_until > datetime.now(UTC):
            account.risk_state = "cooldown"
        elif manual_blocked:
            account.risk_state = "entry_blocked"
        elif automatic_blocked:
            account.risk_state = "automatic_blocked"
        else:
            account.risk_state = "clear"

    def _assert_entry_allowed(
        self, session: Session, account: PaperAccountRecord, automatic: bool
    ) -> None:
        if account.position_quantity != Decimal("0") or account.pending_entry:
            raise RuntimeError("Paper Account already has an active trade state.")
        emergency = self._emergency_state(session)
        if emergency.active:
            raise RuntimeError("Paper Emergency Stop blocks new entries.")
        risk = self._risk_state(session, account)
        cooldown_until = (
            RuntimeStateRepository._with_utc(account.cooldown_until)
            if account.cooldown_until
            else None
        )
        if cooldown_until is not None and cooldown_until > datetime.now(UTC):
            raise RuntimeError("Paper entry is blocked by cooldown.")
        if risk.realized_net_loss >= risk.daily_loss_limit:
            raise RuntimeError("Paper entry is blocked by daily loss limit.")
        if risk.losing_trades >= risk.losing_trade_limit:
            raise RuntimeError("Paper entry is blocked by losing-trade limit.")
        if automatic and risk.automatic_fills >= risk.automatic_fill_limit:
            raise RuntimeError("Paper automatic entry is blocked by daily fill limit.")

    @staticmethod
    def _to_pending_entry(record: PaperPendingEntryRecord) -> PaperPendingEntry:
        return PaperPendingEntry(
            id=record.id,
            kind="limit",
            direction=record.direction,
            quantity=record.quantity,
            limit_price=record.limit_price,
            expires_at=RuntimeStateRepository._with_utc(record.expires_at),
            signal_zone=record.signal_zone,
        )

    def _close_position_record(
        self,
        session: Session,
        account: PaperAccountRecord,
        position: PaperPositionRecord,
        exit_price: Decimal,
        action: str,
        activity: str,
        fee_rate: Decimal,
    ) -> PaperCloseResult:
        exit_fee = position.quantity * exit_price * fee_rate
        price_pnl = position.quantity * (exit_price - position.entry_price)
        if position.direction == "short":
            price_pnl = -price_pnl
        realized_pnl = price_pnl - position.entry_fee - exit_fee
        account.available_futures_balance += position.allocated_margin + price_pnl - exit_fee
        account.position_quantity = Decimal("0")
        account.protection_state = "none"
        account.last_change_reason = action
        account.revision += 1
        self._record_risk_result(
            session, account, price_pnl - position.entry_fee, exit_fee, False
        )
        self._audit(session, action, activity)
        session.delete(position)
        return PaperCloseResult(
            account=self._to_snapshot(account),
            exit_fee_rate=fee_rate,
            exit_fee=exit_fee,
            realized_pnl=realized_pnl,
            activity=activity,
        )

    def _record_risk_result(
        self,
        session: Session,
        account: PaperAccountRecord,
        realized_pnl: Decimal,
        fees: Decimal,
        automatic_fill: bool,
    ) -> None:
        risk = self._risk_state(session, account)
        net_result = realized_pnl - fees
        if net_result < 0:
            risk.realized_net_loss += -net_result
            risk.losing_trades += 1
        if automatic_fill:
            risk.automatic_fills += 1
        self._sync_risk_state(account, risk)

    def _start_cooldown(self, session: Session, account: PaperAccountRecord) -> None:
        if account.position_quantity != Decimal("0"):
            return
        if session.get(PaperProtectionRecord, 1) is not None:
            return
        risk = self._risk_state(session, account)
        account.cooldown_until = datetime.now(UTC) + timedelta(
            seconds=risk.cooldown_seconds
        )
        self._sync_risk_state(account, risk)

    @staticmethod
    def _emergency_state(session: Session) -> PaperEmergencyStopRecord:
        record = session.get(PaperEmergencyStopRecord, 1)
        if record is None:
            record = PaperEmergencyStopRecord(
                id=1,
                active=False,
                reason=None,
                activated_at=None,
                automatic_trading_requires_restart=False,
            )
            session.add(record)
            session.flush()
        return record

    @staticmethod
    def _to_emergency_state(record: PaperEmergencyStopRecord) -> PaperEmergencyState:
        return PaperEmergencyState(
            active=record.active,
            reason=record.reason,
            activated_at=(
                RuntimeStateRepository._with_utc(record.activated_at)
                if record.activated_at
                else None
            ),
            automatic_trading_requires_restart=record.automatic_trading_requires_restart,
        )

    @staticmethod
    def _record_used_signal(
        session: Session, symbol: str, direction: str, trigger_zone: str
    ) -> None:
        existing = session.scalar(
            select(PaperUsedSignalRecord).where(
                PaperUsedSignalRecord.symbol == symbol,
                PaperUsedSignalRecord.direction == direction,
                PaperUsedSignalRecord.trigger_zone == trigger_zone,
            )
        )
        if existing is None:
            session.add(
                PaperUsedSignalRecord(
                    symbol=symbol,
                    direction=direction,
                    trigger_zone=trigger_zone,
                    used_at=datetime.now(UTC),
                    reset_seen=False,
                )
            )

    @staticmethod
    def _used_signal_exists(
        session: Session, symbol: str, direction: str, trigger_zone: str
    ) -> bool:
        record = session.scalar(
            select(PaperUsedSignalRecord).where(
                PaperUsedSignalRecord.symbol == symbol,
                PaperUsedSignalRecord.direction == direction,
                PaperUsedSignalRecord.trigger_zone == trigger_zone,
            )
        )
        return record is not None and not record.reset_seen

    @staticmethod
    def _to_used_signal(record: PaperUsedSignalRecord) -> PaperUsedSignal:
        return PaperUsedSignal(
            symbol=record.symbol,
            direction=record.direction,
            trigger_zone=record.trigger_zone,
            used_at=RuntimeStateRepository._with_utc(record.used_at),
            reset_seen=record.reset_seen,
        )

    @staticmethod
    def _profile_payload(settings: dict[str, object]) -> tuple[str, str]:
        serialized = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        safety_settings = {
            key: value
            for key, value in settings.items()
            if key not in {"theme", "language", "font_size", "layout"}
        }
        fingerprint = hashlib.sha256(
            json.dumps(safety_settings, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return serialized, fingerprint

    @staticmethod
    def _active_profile(session: Session) -> PaperActiveProfileRecord:
        record = session.get(PaperActiveProfileRecord, 1)
        if record is None:
            record = PaperActiveProfileRecord(id=1, profile_id=None)
            session.add(record)
            session.flush()
        return record

    def _current_safety_fingerprint(self, session: Session) -> str:
        active_profile = self._active_profile(session)
        if active_profile.profile_id is None:
            return hashlib.sha256(b"default-paper-profile").hexdigest()
        profile = session.get(PaperProfileRecord, active_profile.profile_id)
        if profile is None:
            return hashlib.sha256(b"default-paper-profile").hexdigest()
        return profile.safety_fingerprint

    @staticmethod
    def _to_profile(record: PaperProfileRecord) -> PaperProfile:
        return PaperProfile(
            id=record.id,
            name=record.name,
            settings=json.loads(record.settings_json),
            safety_fingerprint=record.safety_fingerprint,
        )

    @staticmethod
    def _to_risk_snapshot(
        record: PaperRiskStateRecord, account: PaperAccountRecord
    ) -> PaperRiskSnapshot:
        manual_blocked = (
            record.realized_net_loss >= record.daily_loss_limit
            or record.losing_trades >= record.losing_trade_limit
        )
        return PaperRiskSnapshot(
            day=record.day,
            baseline_balance=record.baseline_balance,
            realized_net_loss=record.realized_net_loss,
            losing_trades=record.losing_trades,
            automatic_fills=record.automatic_fills,
            settings=PaperRiskSettings(
                daily_loss_limit=record.daily_loss_limit,
                losing_trade_limit=record.losing_trade_limit,
                automatic_fill_limit=record.automatic_fill_limit,
                cooldown_seconds=record.cooldown_seconds,
            ),
            manual_entries_blocked=manual_blocked,
            automatic_entries_blocked=manual_blocked
            or record.automatic_fills >= record.automatic_fill_limit,
            cooldown_until=(
                RuntimeStateRepository._with_utc(account.cooldown_until)
                if account.cooldown_until
                else None
            ),
        )

    @staticmethod
    def _to_verification(
        record: PaperVerificationRecordRow,
        engine_build: str,
        safety_fingerprint: str,
    ) -> PaperVerificationRecord:
        stale = (
            record.engine_build != engine_build
            or record.safety_fingerprint != safety_fingerprint
        )
        return PaperVerificationRecord(
            id=record.id,
            recorded_at=RuntimeStateRepository._with_utc(record.recorded_at),
            engine_build=record.engine_build,
            safety_fingerprint=record.safety_fingerprint,
            evidence=record.evidence,
            stale=stale,
            advisory_warning_ar=(
                "تحقق Paper قديم، وهذا تحذير استرشادي فقط."
                if stale
                else None
            ),
        )


class PaperWatchlistRecord(Base):
    __tablename__ = "paper_watchlist"

    symbol: Mapped[str] = mapped_column(String(64), primary_key=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="both")


class PaperAutomationStateRecord(Base):
    __tablename__ = "paper_automation_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    automatic_trading_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PaperWatchlistRepository:
    """Stores manual Paper watchlist membership, never exchange state."""

    MAXIMUM_SIZE = 20

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def add(self, symbol: str) -> None:
        with Session(self._database_engine) as session:
            if session.get(PaperWatchlistRecord, symbol) is not None:
                return
            count = session.scalar(
                select(func.count()).select_from(PaperWatchlistRecord)
            )
            if count >= self.MAXIMUM_SIZE:
                raise ValueError("Paper watchlist is limited to 20 contracts.")
            highest_priority = session.scalar(
                select(PaperWatchlistRecord.priority)
                .order_by(PaperWatchlistRecord.priority.desc())
                .limit(1)
            )
            session.add(
                PaperWatchlistRecord(
                    symbol=symbol,
                    priority=(highest_priority or 0) + 1,
                    is_active=False,
                    direction="both",
                )
            )
            session.commit()

    def remove(self, symbol: str) -> None:
        with Session(self._database_engine) as session:
            record = session.get(PaperWatchlistRecord, symbol)
            if record is None:
                raise LookupError("Paper contract is not watched.")
            was_active = record.is_active
            session.delete(record)
            if was_active:
                self._automation_state(session).automatic_trading_enabled = False
            session.commit()

    def set_active(self, symbol: str) -> None:
        with Session(self._database_engine) as session:
            selected = session.get(PaperWatchlistRecord, symbol)
            if selected is None:
                raise LookupError("Active Auto-Trading Coin must be watched first.")
            changed = not selected.is_active
            for record in session.scalars(select(PaperWatchlistRecord)):
                record.is_active = record.symbol == symbol
            if changed:
                self._automation_state(session).automatic_trading_enabled = False
            session.commit()

    def set_priority(self, symbol: str, priority: int) -> None:
        with Session(self._database_engine) as session:
            record = session.get(PaperWatchlistRecord, symbol)
            if record is None:
                raise LookupError("Paper contract is not watched.")
            record.priority = priority
            session.commit()

    def set_direction(self, symbol: str, direction: str) -> None:
        with Session(self._database_engine) as session:
            record = session.get(PaperWatchlistRecord, symbol)
            if record is None:
                raise LookupError("Paper contract is not watched.")
            record.direction = direction
            session.commit()

    def direction_for(self, symbol: str) -> str:
        with Session(self._database_engine) as session:
            record = session.get(PaperWatchlistRecord, symbol)
            if record is None:
                raise LookupError("Paper contract is not watched.")
            return record.direction

    def start_automation(self) -> None:
        with Session(self._database_engine) as session:
            active = session.scalar(
                select(PaperWatchlistRecord).where(PaperWatchlistRecord.is_active)
            )
            if active is None:
                raise ValueError(
                    "Select an Active Auto-Trading Coin before starting automation."
                )
            self._automation_state(session).automatic_trading_enabled = True
            session.commit()

    def stop_automation(self) -> None:
        with Session(self._database_engine) as session:
            self._automation_state(session).automatic_trading_enabled = False
            session.commit()

    def get(self) -> PaperWatchlist:
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(PaperWatchlistRecord).order_by(PaperWatchlistRecord.priority)
            )
            return PaperWatchlist(
                items=[
                    WatchlistItem(
                        symbol=record.symbol,
                        priority=record.priority,
                        is_active=record.is_active,
                        monitoring_only=not record.is_active,
                        direction=record.direction,
                    )
                    for record in records
                ],
                automatic_trading_enabled=self._automation_state(
                    session
                ).automatic_trading_enabled,
            )

    @staticmethod
    def _automation_state(session: Session) -> PaperAutomationStateRecord:
        state = session.get(PaperAutomationStateRecord, 1)
        if state is None:
            state = PaperAutomationStateRecord(id=1, automatic_trading_enabled=False)
            session.add(state)
            session.flush()
        return state
