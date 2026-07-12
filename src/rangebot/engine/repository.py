"""Persistence for the engine's minimal lifecycle snapshot."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.runtime import RuntimeState


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
