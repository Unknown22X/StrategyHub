"""Durable environment activation proof separate from ordinary UI preferences."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.environment import ApplicationEnvironment, EnvironmentActivation


class EnvironmentActivationBase(DeclarativeBase):
    pass


class EnvironmentActivationRecord(EnvironmentActivationBase):
    __tablename__ = "environment_activation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class EnvironmentActivationRepository:
    """Persist only environments that completed the authoritative runtime workflow."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def get(self) -> EnvironmentActivation | None:
        with Session(self._database_engine) as session:
            record = session.get(EnvironmentActivationRecord, 1)
            return self._to_domain(record) if record is not None else None

    def save(
        self,
        environment: ApplicationEnvironment,
        *,
        confirmed_at: datetime | None = None,
    ) -> EnvironmentActivation:
        timestamp = confirmed_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("Environment activation timestamp must be timezone-aware.")
        timestamp = timestamp.astimezone(UTC)
        with Session(self._database_engine) as session:
            record = session.get(EnvironmentActivationRecord, 1)
            if record is None:
                record = EnvironmentActivationRecord(
                    id=1,
                    environment=environment,
                    confirmed_at=timestamp,
                    revision=1,
                )
                session.add(record)
            else:
                record.environment = environment
                record.confirmed_at = timestamp
                record.revision += 1
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    @staticmethod
    def _to_domain(record: EnvironmentActivationRecord) -> EnvironmentActivation:
        confirmed_at = record.confirmed_at
        if confirmed_at.tzinfo is None:
            confirmed_at = confirmed_at.replace(tzinfo=UTC)
        return EnvironmentActivation(
            environment=record.environment,
            confirmed_at=confirmed_at,
            revision=record.revision,
        )
