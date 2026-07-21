"""Persistence, lifecycle, history, and ownership for strategy instances."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
from threading import RLock
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from pydantic_core import to_jsonable_python

from rangebot.domain.strategy import (
    StrategyConfigurationVersion,
    StrategyDecision,
    StrategyDecisionCreate,
    StrategyDeletionReadiness,
    StrategyInstance,
    StrategyInstanceCreate,
    StrategyInstanceDuplicate,
    StrategyInstanceUpdate,
    StrategyLifecycle,
    StrategyRun,
    TradeOwnership,
    TradeOwnershipCreate,
)


class StrategyInstanceBase(DeclarativeBase):
    pass


class StrategyInstanceRecord(StrategyInstanceBase):
    __tablename__ = "strategy_instance"

    instance_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_id: Mapped[str] = mapped_column(String(72), nullable=False)
    template_version: Mapped[str] = mapped_column(String(50), nullable=False)
    preset_id: Mapped[str | None] = mapped_column(String(64))
    preset_revision: Mapped[int | None] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_margin: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    requested_leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)


class StrategyConfigurationVersionRecord(StrategyInstanceBase):
    __tablename__ = "strategy_configuration_version"

    version_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_margin: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    requested_leverage: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StrategyRunRecord(StrategyInstanceBase):
    __tablename__ = "strategy_run"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    configuration_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(200))


class StrategyDecisionRecord(StrategyInstanceBase):
    __tablename__ = "strategy_decision"

    decision_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    signal: Mapped[str] = mapped_column(String(100), nullable=False)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_json: Mapped[str] = mapped_column(Text, nullable=False)


class TradeOwnershipRecord(StrategyInstanceBase):
    __tablename__ = "trade_ownership"

    ownership_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    identity_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    external_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(16))
    symbol: Mapped[str | None] = mapped_column(String(64))
    direction: Mapped[str | None] = mapped_column(String(16))
    trailing_stop_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    trailing_stop_distance: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    trailing_state: Mapped[str | None] = mapped_column(String(16))
    trailing_order_id: Mapped[str | None] = mapped_column(String(200))
    trailing_last_error: Mapped[str | None] = mapped_column(String(500))
    trailing_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    instance_id: Mapped[str | None] = mapped_column(String(36))
    run_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "stopped": {"running", "monitoring"},
    "running": {"paused", "stopped", "error"},
    "monitoring": {"paused", "stopped", "error"},
    "paused": {"running", "monitoring", "stopped"},
    "error": {"stopped"},
}


class StrategyInstanceRepository:
    """Store strategy state and enforce account-level lifecycle invariants."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine
        self._lock = RLock()

    def list(self, *, include_archived: bool = False) -> list[StrategyInstance]:
        with Session(self._database_engine) as session:
            statement = select(StrategyInstanceRecord)
            if not include_archived:
                statement = statement.where(
                    StrategyInstanceRecord.archived_at.is_(None)
                )
            records = session.scalars(
                statement.order_by(
                    StrategyInstanceRecord.is_pinned.desc(),
                    StrategyInstanceRecord.created_at,
                )
            )
            return [self._to_domain(record) for record in records]

    def archived(self) -> list[StrategyInstance]:
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(StrategyInstanceRecord)
                .where(StrategyInstanceRecord.archived_at.is_not(None))
                .order_by(StrategyInstanceRecord.archived_at.desc())
            )
            return [self._to_domain(record) for record in records]

    def get(self, instance_id: str) -> StrategyInstance:
        with Session(self._database_engine) as session:
            return self._to_domain(self._instance(session, instance_id))

    def create(
        self,
        change: StrategyInstanceCreate,
        *,
        template_version: str = "unknown",
        preset_revision: int | None = None,
    ) -> StrategyInstance:
        now = datetime.now(UTC)
        configuration_json = self._configuration_json(change.configuration)
        template_id = change.template_id or f"builtin:{change.type_id}"
        record = StrategyInstanceRecord(
            instance_id=str(uuid4()),
            type_id=change.type_id,
            template_id=template_id,
            template_version=template_version,
            preset_id=change.preset_id,
            preset_revision=preset_revision,
            name=change.name,
            environment=change.environment,
            symbol=change.symbol,
            timeframe_minutes=change.timeframe_minutes,
            direction=change.direction,
            requested_margin=change.requested_margin,
            requested_leverage=change.requested_leverage,
            configuration_json=configuration_json,
            status="stopped",
            is_pinned=False,
            archived_at=None,
            archive_reason=None,
            created_at=now,
            updated_at=now,
            revision=1,
        )
        with self._lock, Session(self._database_engine) as session:
            session.add(record)
            session.add(
                StrategyConfigurationVersionRecord(
                    instance_id=record.instance_id,
                    revision=record.revision,
                    requested_margin=record.requested_margin,
                    requested_leverage=record.requested_leverage,
                    configuration_json=configuration_json,
                    created_at=now,
                )
            )
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def duplicate(
        self, instance_id: str, change: StrategyInstanceDuplicate
    ) -> StrategyInstance:
        source = self.get(instance_id)
        default_name = f"{source.name} — نسخة"
        name = change.name or default_name[:200]
        return self.create(
            StrategyInstanceCreate(
                type_id=source.type_id,
                template_id=source.template_id,
                preset_id=source.preset_id,
                name=name,
                environment=source.environment,
                symbol=source.symbol,
                timeframe_minutes=source.timeframe_minutes,
                direction=source.direction,
                requested_margin=source.requested_margin,
                requested_leverage=source.requested_leverage,
                configuration=source.configuration,
            ),
            template_version=source.template_version,
            preset_revision=source.preset_revision,
        )

    def update(
        self, instance_id: str, change: StrategyInstanceUpdate
    ) -> StrategyInstance:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            if record.archived_at is not None:
                raise RuntimeError("Restore an archived Strategy before editing it.")
            if record.status not in {"stopped", "paused"}:
                raise RuntimeError("Running or monitoring strategies cannot be edited.")
            values = change.model_dump(exclude_none=True)
            configuration = values.pop("configuration", None)
            for field, value in values.items():
                setattr(record, field, value)
            if configuration is not None:
                record.configuration_json = self._configuration_json(configuration)
            record.updated_at = datetime.now(UTC)
            record.revision += 1
            session.add(
                StrategyConfigurationVersionRecord(
                    instance_id=record.instance_id,
                    revision=record.revision,
                    requested_margin=record.requested_margin,
                    requested_leverage=record.requested_leverage,
                    configuration_json=record.configuration_json,
                    created_at=record.updated_at,
                )
            )
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def delete(self, instance_id: str) -> None:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            reasons = self._deletion_reason_codes(session, record)
            if reasons:
                raise RuntimeError(
                    "This Strategy contains runtime, trading, Backtest, deployment, or audit history. Archive it instead."
                )
            for version in session.scalars(
                select(StrategyConfigurationVersionRecord).where(
                    StrategyConfigurationVersionRecord.instance_id == instance_id
                )
            ):
                session.delete(version)
            session.delete(record)
            session.commit()

    def deletion_readiness(self, instance_id: str) -> StrategyDeletionReadiness:
        with Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            reasons = self._deletion_reason_codes(session, record)
        messages = {
            "strategy_not_stopped": "Stop the Strategy before deleting or archiving it.",
            "run_history_present": "Strategy Run history must be preserved.",
            "decision_history_present": "Signal decision history must be preserved.",
            "ownership_history_present": "Order or Position ownership history must be preserved.",
            "trade_history_present": "Trade history must be preserved.",
            "deployment_history_present": "Bot Deployment history must be preserved.",
            "setup_history_present": "Coin Setup history references this Strategy.",
            "backtest_history_present": "A Backtest created this Strategy.",
        }
        return StrategyDeletionReadiness(
            instance_id=instance_id,
            can_delete=not reasons,
            must_archive=bool(reasons),
            reason_codes=tuple(reasons),
            messages={code: messages[code] for code in reasons},
        )

    def set_pinned(self, instance_id: str, pinned: bool) -> StrategyInstance:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            if record.archived_at is not None:
                raise RuntimeError("Archived Strategies cannot be pinned.")
            record.is_pinned = pinned
            record.updated_at = datetime.now(UTC)
            record.revision += 1
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def archive(self, instance_id: str, reason: str = "") -> StrategyInstance:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            if record.status != "stopped":
                raise RuntimeError("Stop the Strategy before archiving it.")
            if record.archived_at is None:
                now = datetime.now(UTC)
                record.archived_at = now
                record.archive_reason = reason.strip()[:500] or None
                record.is_pinned = False
                record.updated_at = now
                record.revision += 1
                session.commit()
                session.refresh(record)
            return self._to_domain(record)

    def restore(self, instance_id: str) -> StrategyInstance:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            if record.archived_at is not None:
                record.archived_at = None
                record.archive_reason = None
                record.status = "stopped"
                record.updated_at = datetime.now(UTC)
                record.revision += 1
                session.commit()
                session.refresh(record)
            return self._to_domain(record)

    def transition(
        self,
        instance_id: str,
        target: StrategyLifecycle,
        *,
        configuration_snapshot_extensions: dict[str, object] | None = None,
    ) -> StrategyInstance:
        with self._lock, Session(self._database_engine) as session:
            record = self._instance(session, instance_id)
            if record.archived_at is not None and target != "stopped":
                raise RuntimeError("Restore an archived Strategy before starting it.")
            if target == record.status:
                return self._to_domain(record)
            if target not in _ALLOWED_TRANSITIONS.get(record.status, set()):
                raise RuntimeError(
                    f"Invalid strategy transition: {record.status} -> {target}"
                )
            if target == "running":
                automatic = session.scalar(
                    select(StrategyInstanceRecord).where(
                        StrategyInstanceRecord.status == "running",
                        StrategyInstanceRecord.instance_id != instance_id,
                    )
                )
                if automatic is not None:
                    raise RuntimeError(
                        "Another strategy already controls automatic entries."
                    )
            now = datetime.now(UTC)
            if record.status in {"running", "monitoring"}:
                self._finish_active_run(
                    session,
                    instance_id,
                    status="error" if target == "error" else "completed",
                    reason=target,
                    ended_at=now,
                )
            if target in {"running", "monitoring"}:
                configuration_revision = self._latest_configuration_revision(
                    session, instance_id
                )
                snapshot = self._run_configuration_snapshot(
                    session,
                    record,
                    configuration_revision,
                )
                if configuration_snapshot_extensions:
                    snapshot.update(configuration_snapshot_extensions)
                session.add(
                    StrategyRunRecord(
                        run_id=str(uuid4()),
                        instance_id=instance_id,
                        mode="automatic" if target == "running" else "monitoring",
                        status="active",
                        configuration_revision=configuration_revision,
                        configuration_snapshot_json=self._configuration_json(snapshot),
                        started_at=now,
                        ended_at=None,
                        end_reason=None,
                    )
                )
            record.status = target
            record.updated_at = now
            record.revision += 1
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def configuration_versions(
        self, instance_id: str
    ) -> list[StrategyConfigurationVersion]:
        with Session(self._database_engine) as session:
            self._instance(session, instance_id)
            records = session.scalars(
                select(StrategyConfigurationVersionRecord)
                .where(StrategyConfigurationVersionRecord.instance_id == instance_id)
                .order_by(StrategyConfigurationVersionRecord.revision)
            )
            return [self._configuration_version_to_domain(record) for record in records]

    def runs(self, instance_id: str) -> list[StrategyRun]:
        with Session(self._database_engine) as session:
            self._instance(session, instance_id)
            records = session.scalars(
                select(StrategyRunRecord)
                .where(StrategyRunRecord.instance_id == instance_id)
                .order_by(StrategyRunRecord.started_at.desc())
            )
            return [self._run_to_domain(record) for record in records]

    def active_run(self, instance_id: str) -> StrategyRun:
        with Session(self._database_engine) as session:
            self._instance(session, instance_id)
            record = self._active_run(session, instance_id)
            if record is None:
                raise LookupError(f"No active strategy run for {instance_id}.")
            return self._run_to_domain(record)

    def decisions(self, instance_id: str, limit: int = 100) -> list[StrategyDecision]:
        if limit < 1 or limit > 1000:
            raise ValueError("Decision limit must be between 1 and 1000.")
        with Session(self._database_engine) as session:
            self._instance(session, instance_id)
            records = session.scalars(
                select(StrategyDecisionRecord)
                .where(StrategyDecisionRecord.instance_id == instance_id)
                .order_by(StrategyDecisionRecord.occurred_at.desc())
                .limit(limit)
            )
            return [self._decision_to_domain(record) for record in records]

    def record_decision(
        self, instance_id: str, change: StrategyDecisionCreate
    ) -> StrategyDecision:
        with self._lock, Session(self._database_engine) as session:
            instance = self._instance(session, instance_id)
            run = self._active_run(session, instance_id)
            if run is None:
                raise RuntimeError("A decision requires an active strategy run.")
            record = StrategyDecisionRecord(
                run_id=run.run_id,
                instance_id=instance_id,
                symbol=instance.symbol,
                occurred_at=change.occurred_at or datetime.now(UTC),
                signal=change.signal,
                eligible=change.eligible,
                reason_codes_json=json.dumps(
                    list(change.reason_codes),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
                analysis_json=json.dumps(
                    to_jsonable_python(change.analysis),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._decision_to_domain(record)

    def record_trade_ownership(self, change: TradeOwnershipCreate) -> TradeOwnership:
        with self._lock, Session(self._database_engine) as session:
            if change.origin in {"automatic_strategy", "monitoring_conversion"}:
                if change.instance_id is None or change.run_id is None:
                    raise ValueError(
                        "Strategy-originated trades require instance and run ownership."
                    )
            if change.instance_id is not None:
                self._instance(session, change.instance_id)
            if change.run_id is not None:
                run = session.get(StrategyRunRecord, change.run_id)
                if run is None:
                    raise LookupError(f"Unknown strategy run: {change.run_id}")
                if (
                    change.instance_id is not None
                    and run.instance_id != change.instance_id
                ):
                    raise ValueError(
                        "Trade run does not belong to the supplied strategy."
                    )
            record = TradeOwnershipRecord(
                identity_kind=change.identity_kind,
                external_identity=change.external_identity,
                origin=change.origin,
                environment=change.environment,
                symbol=change.symbol,
                direction=change.direction,
                trailing_stop_price=change.trailing_stop_price,
                trailing_stop_distance=change.trailing_stop_distance,
                trailing_state=change.trailing_state,
                trailing_order_id=change.trailing_order_id,
                trailing_last_error=change.trailing_last_error,
                trailing_updated_at=(
                    change.trailing_updated_at
                    or (
                        datetime.now(UTC) if change.trailing_state is not None else None
                    )
                ),
                instance_id=change.instance_id,
                run_id=change.run_id,
                created_at=datetime.now(UTC),
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError(
                    "Trade identity ownership is already recorded."
                ) from error
            session.refresh(record)
            return self._ownership_to_domain(record)

    def trade_ownership(
        self, identity_kind: str, external_identity: str
    ) -> TradeOwnership | None:
        with Session(self._database_engine) as session:
            record = session.scalar(
                select(TradeOwnershipRecord).where(
                    TradeOwnershipRecord.identity_kind == identity_kind,
                    TradeOwnershipRecord.external_identity == external_identity,
                )
            )
            return self._ownership_to_domain(record) if record is not None else None

    def trade_ownerships(
        self,
        *,
        identity_kind: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        direction: str | None = None,
    ) -> list[TradeOwnership]:
        statement = select(TradeOwnershipRecord).order_by(
            TradeOwnershipRecord.created_at.desc()
        )
        if identity_kind is not None:
            statement = statement.where(
                TradeOwnershipRecord.identity_kind == identity_kind
            )
        if environment is not None:
            statement = statement.where(TradeOwnershipRecord.environment == environment)
        if symbol is not None:
            statement = statement.where(TradeOwnershipRecord.symbol == symbol)
        if direction is not None:
            statement = statement.where(TradeOwnershipRecord.direction == direction)
        with Session(self._database_engine) as session:
            return [
                self._ownership_to_domain(record)
                for record in session.scalars(statement)
            ]

    def update_trailing_protection(
        self,
        identity_kind: str,
        external_identity: str,
        *,
        state: str,
        trailing_order_id: str | None = None,
        error: str | None = None,
    ) -> TradeOwnership:
        if state not in {"desired", "active", "error"}:
            raise ValueError("Unsupported trailing protection state.")
        with self._lock, Session(self._database_engine) as session:
            record = session.scalar(
                select(TradeOwnershipRecord).where(
                    TradeOwnershipRecord.identity_kind == identity_kind,
                    TradeOwnershipRecord.external_identity == external_identity,
                )
            )
            if record is None:
                raise LookupError("Unknown trade ownership identity.")
            record.trailing_state = state
            record.trailing_order_id = trailing_order_id
            record.trailing_last_error = error
            record.trailing_updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._ownership_to_domain(record)

    def delete_trade_ownership(
        self, identity_kind: str, external_identity: str
    ) -> bool:
        with self._lock, Session(self._database_engine) as session:
            record = session.scalar(
                select(TradeOwnershipRecord).where(
                    TradeOwnershipRecord.identity_kind == identity_kind,
                    TradeOwnershipRecord.external_identity == external_identity,
                )
            )
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    @staticmethod
    def _instance(session: Session, instance_id: str) -> StrategyInstanceRecord:
        record = session.get(StrategyInstanceRecord, instance_id)
        if record is None:
            raise LookupError(f"Unknown strategy instance: {instance_id}")
        return record

    @staticmethod
    def _active_run(session: Session, instance_id: str) -> StrategyRunRecord | None:
        return session.scalar(
            select(StrategyRunRecord).where(
                StrategyRunRecord.instance_id == instance_id,
                StrategyRunRecord.status == "active",
            )
        )

    @staticmethod
    def _latest_configuration_revision(session: Session, instance_id: str) -> int:
        revision = session.scalar(
            select(StrategyConfigurationVersionRecord.revision)
            .where(StrategyConfigurationVersionRecord.instance_id == instance_id)
            .order_by(StrategyConfigurationVersionRecord.revision.desc())
            .limit(1)
        )
        if revision is None:
            raise RuntimeError(
                "Strategy instance is missing its configuration-version history."
            )
        return revision

    @classmethod
    def _run_configuration_snapshot(
        cls,
        session: Session,
        record: StrategyInstanceRecord,
        configuration_revision: int,
    ) -> dict[str, object]:
        version = session.scalar(
            select(StrategyConfigurationVersionRecord).where(
                StrategyConfigurationVersionRecord.instance_id == record.instance_id,
                StrategyConfigurationVersionRecord.revision == configuration_revision,
            )
        )
        if version is None:
            raise RuntimeError(
                "Strategy run cannot start without its configuration-version snapshot."
            )
        return {
            "schema_version": 1,
            "instance": {
                "instance_id": record.instance_id,
                "type_id": record.type_id,
                "template_id": record.template_id,
                "template_version": record.template_version,
                "preset_id": record.preset_id,
                "preset_revision": record.preset_revision,
                "name": record.name,
                "environment": record.environment,
                "symbol": record.symbol,
                "timeframe_minutes": record.timeframe_minutes,
                "direction": record.direction,
                "requested_margin": str(version.requested_margin),
                "requested_leverage": version.requested_leverage,
                "configuration": json.loads(version.configuration_json),
                "status": record.status,
                "created_at": cls._with_utc(record.created_at).isoformat(),
                "updated_at": cls._with_utc(record.updated_at).isoformat(),
                "revision": record.revision,
            },
            "configuration_revision": configuration_revision,
        }

    @staticmethod
    def _deletion_reason_codes(
        session: Session,
        record: StrategyInstanceRecord,
    ) -> list[str]:
        reasons: list[str] = []
        instance_id = record.instance_id
        if record.status != "stopped":
            reasons.append("strategy_not_stopped")
        if (
            session.scalar(
                select(StrategyRunRecord.run_id)
                .where(StrategyRunRecord.instance_id == instance_id)
                .limit(1)
            )
            is not None
        ):
            reasons.append("run_history_present")
        if (
            session.scalar(
                select(StrategyDecisionRecord.decision_id)
                .where(StrategyDecisionRecord.instance_id == instance_id)
                .limit(1)
            )
            is not None
        ):
            reasons.append("decision_history_present")
        if (
            session.scalar(
                select(TradeOwnershipRecord.ownership_id)
                .where(TradeOwnershipRecord.instance_id == instance_id)
                .limit(1)
            )
            is not None
        ):
            reasons.append("ownership_history_present")
        raw_checks = (
            (
                "trade_history_present",
                "SELECT 1 FROM trade_fill WHERE instance_id = :id LIMIT 1",
            ),
            (
                "deployment_history_present",
                "SELECT 1 FROM bot_deployment WHERE runtime_instance_id = :id LIMIT 1",
            ),
            (
                "setup_history_present",
                "SELECT 1 FROM strategy_coin_setup WHERE runtime_instance_id = :id LIMIT 1",
            ),
            (
                "backtest_history_present",
                "SELECT 1 FROM backtest_strategy_application WHERE instance_id = :id LIMIT 1",
            ),
        )
        for code, statement in raw_checks:
            if (
                session.execute(text(statement), {"id": instance_id}).first()
                is not None
            ):
                reasons.append(code)
        return reasons

    def _finish_active_run(
        self,
        session: Session,
        instance_id: str,
        *,
        status: str,
        reason: str,
        ended_at: datetime,
    ) -> None:
        run = self._active_run(session, instance_id)
        if run is None:
            raise RuntimeError("Active strategy state is missing its run record.")
        run.status = status
        run.ended_at = ended_at
        run.end_reason = reason

    @staticmethod
    def _configuration_json(configuration: dict[str, object]) -> str:
        return json.dumps(
            to_jsonable_python(configuration),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _with_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value

    @classmethod
    def _to_domain(cls, record: StrategyInstanceRecord) -> StrategyInstance:
        return StrategyInstance(
            instance_id=record.instance_id,
            type_id=record.type_id,
            template_id=record.template_id,
            template_version=record.template_version,
            preset_id=record.preset_id,
            preset_revision=record.preset_revision,
            name=record.name,
            environment=record.environment,
            symbol=record.symbol,
            timeframe_minutes=record.timeframe_minutes,
            direction=record.direction,
            requested_margin=record.requested_margin,
            requested_leverage=record.requested_leverage,
            configuration=json.loads(record.configuration_json),
            status=record.status,
            is_pinned=record.is_pinned,
            archived_at=(
                cls._with_utc(record.archived_at) if record.archived_at else None
            ),
            archive_reason=record.archive_reason,
            created_at=cls._with_utc(record.created_at),
            updated_at=cls._with_utc(record.updated_at),
            revision=record.revision,
        )

    @classmethod
    def _configuration_version_to_domain(
        cls, record: StrategyConfigurationVersionRecord
    ) -> StrategyConfigurationVersion:
        return StrategyConfigurationVersion(
            version_id=record.version_id,
            instance_id=record.instance_id,
            revision=record.revision,
            requested_margin=record.requested_margin,
            requested_leverage=record.requested_leverage,
            configuration=json.loads(record.configuration_json),
            created_at=cls._with_utc(record.created_at),
        )

    @classmethod
    def _run_to_domain(cls, record: StrategyRunRecord) -> StrategyRun:
        return StrategyRun(
            run_id=record.run_id,
            instance_id=record.instance_id,
            mode=record.mode,
            status=record.status,
            configuration_revision=record.configuration_revision,
            configuration_snapshot=json.loads(record.configuration_snapshot_json),
            started_at=cls._with_utc(record.started_at),
            ended_at=cls._with_utc(record.ended_at) if record.ended_at else None,
            end_reason=record.end_reason,
        )

    @classmethod
    def _decision_to_domain(cls, record: StrategyDecisionRecord) -> StrategyDecision:
        return StrategyDecision(
            decision_id=record.decision_id,
            run_id=record.run_id,
            instance_id=record.instance_id,
            symbol=record.symbol,
            occurred_at=cls._with_utc(record.occurred_at),
            signal=record.signal,
            eligible=record.eligible,
            reason_codes=tuple(json.loads(record.reason_codes_json)),
            analysis=json.loads(record.analysis_json),
        )

    @classmethod
    def _ownership_to_domain(cls, record: TradeOwnershipRecord) -> TradeOwnership:
        return TradeOwnership(
            ownership_id=record.ownership_id,
            identity_kind=record.identity_kind,
            external_identity=record.external_identity,
            origin=record.origin,
            environment=record.environment,
            symbol=record.symbol,
            direction=record.direction,
            trailing_stop_price=record.trailing_stop_price,
            trailing_stop_distance=record.trailing_stop_distance,
            trailing_state=record.trailing_state,
            trailing_order_id=record.trailing_order_id,
            trailing_last_error=record.trailing_last_error,
            trailing_updated_at=(
                cls._with_utc(record.trailing_updated_at)
                if record.trailing_updated_at is not None
                else None
            ),
            instance_id=record.instance_id,
            run_id=record.run_id,
            created_at=cls._with_utc(record.created_at),
        )
