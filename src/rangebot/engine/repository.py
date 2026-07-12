"""Persistence for the engine's minimal lifecycle snapshot."""

from datetime import UTC, datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.runtime import RuntimeState
from rangebot.domain.paper import PaperAccountChange, PaperAccountSnapshot, PaperAuditEntry


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
    available_futures_balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
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
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)


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
                raise RuntimeError("Paper Account has an open position or pending entry.")
            replacement = self._new_record(change, revision=existing.revision + 1)
            session.delete(existing)
            session.flush()
            session.add(replacement)
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

    @staticmethod
    def _new_record(change: PaperAccountChange, revision: int = 1) -> PaperAccountRecord:
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
