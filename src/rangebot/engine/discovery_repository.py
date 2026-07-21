"""Durable scan and backtest audit repository."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.backtesting import (
    BacktestEquityPoint,
    BacktestResult,
    BacktestRunRequest,
    BacktestTrade,
    StoredBacktestRun,
)
from rangebot.domain.discovery import (
    StoredStrategyScan,
    StrategyScanRequest,
    StrategyScanResult,
)


class DiscoveryResearchBase(DeclarativeBase):
    pass


class DiscoveryScanRecord(DiscoveryResearchBase):
    __tablename__ = "discovery_scan"

    scan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiscoveryScanCandidateRecord(DiscoveryResearchBase):
    __tablename__ = "discovery_scan_candidate"

    candidate_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    scan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestRunRecord(DiscoveryResearchBase):
    __tablename__ = "backtest_run"

    backtest_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str | None] = mapped_column(String(36))
    setup_id: Mapped[str | None] = mapped_column(String(36))
    setup_revision: Mapped[int | None] = mapped_column(Integer)
    strategy_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BacktestTradeRecord(DiscoveryResearchBase):
    __tablename__ = "backtest_trade"

    trade_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trade_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trade_json: Mapped[str] = mapped_column(Text, nullable=False)


class BacktestEquityPointRecord(DiscoveryResearchBase):
    __tablename__ = "backtest_equity_point"

    point_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    backtest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    point_index: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[str] = mapped_column(String(100), nullable=False)
    drawdown_percentage: Mapped[str] = mapped_column(String(100), nullable=False)


class BacktestStrategyApplicationRecord(DiscoveryResearchBase):
    __tablename__ = "backtest_strategy_application"

    application_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    backtest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DiscoveryResearchRepository:
    """Store reproducible scan and simulation results in SQLite."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine
        self._lock = RLock()

    def save_scan(
        self,
        request: StrategyScanRequest,
        result: StrategyScanResult,
        *,
        strategy_version: str,
    ) -> StoredStrategyScan:
        if result.strategy_type_id != request.strategy_type_id:
            raise ValueError("Scan result strategy does not match its request.")
        if result.timeframe_minutes != request.timeframe_minutes:
            raise ValueError("Scan result timeframe does not match its request.")
        created_at = datetime.now(UTC)
        record = DiscoveryScanRecord(
            scan_id=str(uuid4()),
            strategy_type_id=request.strategy_type_id,
            strategy_version=strategy_version,
            timeframe_minutes=request.timeframe_minutes,
            request_json=request.model_dump_json(),
            result_json=result.model_dump_json(),
            created_at=created_at,
        )
        with self._lock, Session(self._database_engine) as session:
            session.add(record)
            for rank, candidate in enumerate(result.candidates, start=1):
                session.add(
                    DiscoveryScanCandidateRecord(
                        scan_id=record.scan_id,
                        rank=rank,
                        symbol=candidate.symbol,
                        score=candidate.score,
                        candidate_json=candidate.model_dump_json(),
                    )
                )
            session.commit()
            session.refresh(record)
            return self._scan_to_domain(record)

    def get_scan(self, scan_id: str) -> StoredStrategyScan:
        with Session(self._database_engine) as session:
            record = session.get(DiscoveryScanRecord, scan_id)
            if record is None:
                raise LookupError(f"Unknown discovery scan: {scan_id}")
            return self._scan_to_domain(record)

    def list_scans(self, limit: int = 50) -> list[StoredStrategyScan]:
        if limit < 1 or limit > 500:
            raise ValueError("Scan limit must be between 1 and 500.")
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(DiscoveryScanRecord)
                .order_by(DiscoveryScanRecord.created_at.desc())
                .limit(limit)
            )
            return [self._scan_to_domain(record) for record in records]

    def save_backtest(
        self,
        request: BacktestRunRequest,
        result: BacktestResult,
        *,
        strategy_version: str,
    ) -> StoredBacktestRun:
        if result.spec != request.spec():
            raise ValueError("Backtest result specification does not match its request.")
        created_at = datetime.now(UTC)
        record = BacktestRunRecord(
            backtest_id=str(uuid4()),
            scan_id=request.scan_id,
            setup_id=request.setup_id,
            setup_revision=request.setup_revision,
            strategy_type_id=request.strategy_type_id,
            strategy_version=strategy_version,
            symbol=request.symbol,
            timeframe_minutes=request.timeframe_minutes,
            request_json=request.model_dump_json(),
            result_json=result.model_dump_json(),
            started_at=result.started_at,
            ended_at=result.ended_at,
            created_at=created_at,
        )
        with self._lock, Session(self._database_engine) as session:
            if request.scan_id is not None:
                scan = session.get(DiscoveryScanRecord, request.scan_id)
                if scan is None:
                    raise LookupError(f"Unknown discovery scan: {request.scan_id}")
                candidate = session.scalar(
                    select(DiscoveryScanCandidateRecord).where(
                        DiscoveryScanCandidateRecord.scan_id == request.scan_id,
                        DiscoveryScanCandidateRecord.symbol == request.symbol,
                    )
                )
                if candidate is None:
                    raise LookupError(
                        "Backtest symbol is not a candidate in the referenced scan."
                    )
            session.add(record)
            for trade in result.trades:
                session.add(
                    BacktestTradeRecord(
                        backtest_id=record.backtest_id,
                        trade_number=trade.trade_number,
                        trade_json=trade.model_dump_json(),
                    )
                )
            for point_index, point in enumerate(result.equity_curve):
                session.add(
                    BacktestEquityPointRecord(
                        backtest_id=record.backtest_id,
                        point_index=point_index,
                        occurred_at=point.occurred_at,
                        equity=str(point.equity),
                        drawdown_percentage=str(point.drawdown_percentage),
                    )
                )
            session.commit()
            session.refresh(record)
            return self._backtest_to_domain(session, record)

    def get_backtest(self, backtest_id: str) -> StoredBacktestRun:
        with Session(self._database_engine) as session:
            record = session.get(BacktestRunRecord, backtest_id)
            if record is None:
                raise LookupError(f"Unknown backtest run: {backtest_id}")
            return self._backtest_to_domain(session, record)

    def list_backtests(self, limit: int = 50) -> list[StoredBacktestRun]:
        if limit < 1 or limit > 500:
            raise ValueError("Backtest limit must be between 1 and 500.")
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(BacktestRunRecord)
                .order_by(BacktestRunRecord.created_at.desc())
                .limit(limit)
            )
            return [self._backtest_to_domain(session, record) for record in records]

    def record_strategy_application(
        self,
        backtest_id: str,
        instance_id: str,
    ) -> None:
        with self._lock, Session(self._database_engine) as session:
            self._require_backtest(session, backtest_id)
            session.add(
                BacktestStrategyApplicationRecord(
                    backtest_id=backtest_id,
                    instance_id=instance_id,
                    created_at=datetime.now(UTC),
                )
            )
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError(
                    "Backtest or strategy is already linked to an application."
                ) from error

    def backtest_trades(self, backtest_id: str) -> list[BacktestTrade]:
        with Session(self._database_engine) as session:
            self._require_backtest(session, backtest_id)
            records = session.scalars(
                select(BacktestTradeRecord)
                .where(BacktestTradeRecord.backtest_id == backtest_id)
                .order_by(BacktestTradeRecord.trade_number)
            )
            return [BacktestTrade.model_validate_json(record.trade_json) for record in records]

    def backtest_equity(self, backtest_id: str) -> list[BacktestEquityPoint]:
        with Session(self._database_engine) as session:
            self._require_backtest(session, backtest_id)
            records = session.scalars(
                select(BacktestEquityPointRecord)
                .where(BacktestEquityPointRecord.backtest_id == backtest_id)
                .order_by(BacktestEquityPointRecord.point_index)
            )
            return [
                BacktestEquityPoint(
                    occurred_at=self._with_utc(record.occurred_at),
                    equity=Decimal(record.equity),
                    drawdown_percentage=Decimal(record.drawdown_percentage),
                )
                for record in records
            ]

    @staticmethod
    def _require_backtest(session: Session, backtest_id: str) -> BacktestRunRecord:
        record = session.get(BacktestRunRecord, backtest_id)
        if record is None:
            raise LookupError(f"Unknown backtest run: {backtest_id}")
        return record

    @classmethod
    def _scan_to_domain(cls, record: DiscoveryScanRecord) -> StoredStrategyScan:
        return StoredStrategyScan(
            scan_id=record.scan_id,
            strategy_version=record.strategy_version,
            created_at=cls._with_utc(record.created_at),
            request=StrategyScanRequest.model_validate_json(record.request_json),
            result=StrategyScanResult.model_validate_json(record.result_json),
        )

    @classmethod
    def _backtest_to_domain(
        cls,
        session: Session,
        record: BacktestRunRecord,
    ) -> StoredBacktestRun:
        application = session.scalar(
            select(BacktestStrategyApplicationRecord).where(
                BacktestStrategyApplicationRecord.backtest_id == record.backtest_id
            )
        )
        return StoredBacktestRun(
            backtest_id=record.backtest_id,
            scan_id=record.scan_id,
            strategy_version=record.strategy_version,
            created_at=cls._with_utc(record.created_at),
            request=BacktestRunRequest.model_validate_json(record.request_json),
            result=BacktestResult.model_validate_json(record.result_json),
            applied_instance_id=application.instance_id if application is not None else None,
        )

    @staticmethod
    def _with_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
