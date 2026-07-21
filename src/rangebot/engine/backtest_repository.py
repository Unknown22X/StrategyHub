"""Persistence for immutable portfolio backtests and inspectable event logs."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.backtesting import (
    BacktestPortfolioRequest,
    BacktestResult,
    BacktestRunStatus,
    StoredPortfolioBacktestRun,
)


class PortfolioBacktestBase(DeclarativeBase):
    pass


class PortfolioBacktestRunRecord(PortfolioBacktestBase):
    __tablename__ = "backtest_portfolio_run"

    backtest_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    setup_id: Mapped[str | None] = mapped_column(String(36))
    setup_revision: Mapped[int | None] = mapped_column(Integer)
    strategy_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_message_ar: Mapped[str] = mapped_column(Text, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_data_hash: Mapped[str | None] = mapped_column(String(64))
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    post_test_observations: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class _EventMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("backtest_portfolio_run.backtest_id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)


class BacktestCandidateRecord(_EventMixin, PortfolioBacktestBase):
    __tablename__ = "backtest_candidate"
    __table_args__ = (UniqueConstraint("backtest_id", "sequence"),)
    candidate_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestDecisionRecord(_EventMixin, PortfolioBacktestBase):
    __tablename__ = "backtest_decision"
    __table_args__ = (UniqueConstraint("backtest_id", "sequence"),)
    decision_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestOrderRecord(_EventMixin, PortfolioBacktestBase):
    __tablename__ = "backtest_order"
    __table_args__ = (UniqueConstraint("backtest_id", "sequence"),)
    order_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestFillRecord(_EventMixin, PortfolioBacktestBase):
    __tablename__ = "backtest_fill"
    __table_args__ = (UniqueConstraint("backtest_id", "sequence"),)
    fill_json: Mapped[str] = mapped_column(Text, nullable=False)


class PortfolioBacktestRepository:
    def __init__(self, database_engine: Engine) -> None:
        self._engine = database_engine
        self._lock = RLock()

    def create(self, request: BacktestPortfolioRequest) -> StoredPortfolioBacktestRun:
        now = datetime.now(UTC)
        payload = request.model_dump_json()
        record = PortfolioBacktestRunRecord(
            backtest_id=str(uuid4()), setup_id=request.setup_id,
            setup_revision=request.setup_revision,
            strategy_type_id=request.strategy_type_id,
            strategy_version=request.strategy_version, mode=request.mode,
            status="queued", progress_percentage=0,
            stage_message_ar="تمت إضافة الاختبار إلى قائمة التنفيذ.",
            configuration_hash=sha256(payload.encode("utf-8")).hexdigest(),
            input_data_hash=None, request_json=payload, result_json=None,
            failure_reason=None,
            post_test_observations="", created_at=now,
            started_at=None, completed_at=None,
        )
        with self._lock, Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def fail_interrupted_runs(self) -> int:
        """Prevent process restarts from leaving nonterminal runs stuck forever."""
        now = datetime.now(UTC)
        with self._lock, Session(self._engine) as session:
            result = session.execute(
                update(PortfolioBacktestRunRecord)
                .where(
                    PortfolioBacktestRunRecord.status.in_(
                        ("queued", "loading_data", "running", "calculating_results")
                    )
                )
                .values(
                    status="failed",
                    stage_message_ar="توقف الاختبار بسبب إعادة تشغيل المحرك.",
                    failure_reason=(
                        "The engine restarted before this persisted run completed. "
                        "Create a new run from the saved configuration."
                    ),
                    completed_at=now,
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def progress(
        self, backtest_id: str, status: BacktestRunStatus,
        percentage: int, message_ar: str,
    ) -> StoredPortfolioBacktestRun:
        with self._lock, Session(self._engine) as session:
            record = self._require(session, backtest_id)
            self._require_nonterminal(record)
            record.status = status
            record.progress_percentage = percentage
            record.stage_message_ar = message_ar
            if record.started_at is None and status not in {"queued", "canceled"}:
                record.started_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def complete(
        self, backtest_id: str, result: BacktestResult
    ) -> StoredPortfolioBacktestRun:
        with self._lock, Session(self._engine) as session:
            record = self._require(session, backtest_id)
            self._require_nonterminal(record)
            if record.input_data_hash is None:
                raise RuntimeError("Backtest input data fingerprint was not recorded.")
            if result.portfolio_request is None or result.portfolio_request.model_dump_json() != record.request_json:
                raise ValueError("Backtest result configuration does not match the persisted run.")
            record.status = "completed"
            record.progress_percentage = 100
            record.stage_message_ar = "اكتمل الاختبار وحُفظت نتائجه."
            record.result_json = result.model_dump_json()
            record.completed_at = datetime.now(UTC)
            for index, item in enumerate(result.candidates):
                session.add(BacktestCandidateRecord(backtest_id=backtest_id, sequence=index, symbol=item.symbol, candidate_json=item.model_dump_json()))
            for index, item in enumerate(result.decisions):
                session.add(BacktestDecisionRecord(backtest_id=backtest_id, sequence=index, symbol=item.symbol, decision_json=item.model_dump_json()))
            for index, item in enumerate(result.orders):
                session.add(BacktestOrderRecord(backtest_id=backtest_id, sequence=index, symbol=item.symbol, order_json=item.model_dump_json()))
            for index, item in enumerate(result.fills):
                session.add(BacktestFillRecord(backtest_id=backtest_id, sequence=index, symbol=item.symbol, fill_json=item.model_dump_json()))
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def record_input_fingerprint(
        self, backtest_id: str, input_data_hash: str
    ) -> StoredPortfolioBacktestRun:
        if len(input_data_hash) != 64:
            raise ValueError("Backtest input fingerprint must be SHA-256.")
        with self._lock, Session(self._engine) as session:
            record = self._require(session, backtest_id)
            self._require_nonterminal(record)
            if record.input_data_hash not in {None, input_data_hash}:
                raise RuntimeError("Backtest input fingerprint is immutable once recorded.")
            record.input_data_hash = input_data_hash
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def fail(self, backtest_id: str, reason: str) -> StoredPortfolioBacktestRun:
        with self._lock, Session(self._engine) as session:
            record = self._require(session, backtest_id)
            self._require_nonterminal(record)
            record.status = "failed"
            record.stage_message_ar = "فشل الاختبار التاريخي."
            record.failure_reason = reason[:4000]
            record.completed_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def get(self, backtest_id: str) -> StoredPortfolioBacktestRun:
        with Session(self._engine) as session:
            return self._to_domain(self._require(session, backtest_id))

    def list(self, limit: int = 50) -> list[StoredPortfolioBacktestRun]:
        if limit < 1 or limit > 500:
            raise ValueError("Backtest limit must be between 1 and 500.")
        with Session(self._engine) as session:
            records = session.scalars(select(PortfolioBacktestRunRecord).order_by(PortfolioBacktestRunRecord.created_at.desc()).limit(limit))
            # History lists intentionally omit large event/equity payloads.
            return [self._to_domain(item, include_result=False) for item in records]

    def update_notes(self, backtest_id: str, observations: str) -> StoredPortfolioBacktestRun:
        with self._lock, Session(self._engine) as session:
            record = self._require(session, backtest_id)
            record.post_test_observations = observations
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    @staticmethod
    def _require(session: Session, backtest_id: str) -> PortfolioBacktestRunRecord:
        record = session.get(PortfolioBacktestRunRecord, backtest_id)
        if record is None:
            raise LookupError(f"Unknown portfolio backtest: {backtest_id}")
        return record

    @staticmethod
    def _require_nonterminal(record: PortfolioBacktestRunRecord) -> None:
        if record.status in {"completed", "failed", "canceled"}:
            raise RuntimeError(
                f"Backtest {record.backtest_id} is immutable after {record.status}."
            )

    @staticmethod
    def _utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _to_domain(
        cls,
        record: PortfolioBacktestRunRecord,
        *,
        include_result: bool = True,
    ) -> StoredPortfolioBacktestRun:
        return StoredPortfolioBacktestRun(
            backtest_id=record.backtest_id, status=record.status,
            progress_percentage=record.progress_percentage,
            stage_message_ar=record.stage_message_ar,
            configuration_hash=record.configuration_hash,
            input_data_hash=record.input_data_hash,
            created_at=cls._utc(record.created_at),
            started_at=cls._utc(record.started_at),
            completed_at=cls._utc(record.completed_at),
            request=BacktestPortfolioRequest.model_validate_json(record.request_json),
            result=(
                BacktestResult.model_validate_json(record.result_json)
                if include_result and record.result_json else None
            ),
            failure_reason=record.failure_reason,
            post_test_observations=record.post_test_observations,
        )
