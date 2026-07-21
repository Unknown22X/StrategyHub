"""Persisted Gate account equity history and engine-owned performance calculations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Integer, Numeric, String, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.exchange import ExchangeSnapshot
from rangebot.domain.performance import (
    AccountEquityPoint,
    AccountPerformanceSeries,
    PerformanceMode,
    PerformancePeriod,
)


class PerformanceBase(DeclarativeBase):
    pass


class AccountEquityPointRecord(PerformanceBase):
    __tablename__ = "account_equity_point"

    point_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_equity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    used_margin: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    margin_usage_percentage: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    realized_pnl_total: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    fees_total: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    funding_total: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    net_pnl_total: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    open_exposure: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)


class AccountPerformanceRepository:
    """Append reconciliation points and provide period-bounded account series."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def record(self, snapshot: ExchangeSnapshot) -> AccountEquityPoint | None:
        if snapshot.reconciliation_error is not None:
            return None
        occurred_at = self._utc(snapshot.reconciled_at)
        with Session(self._database_engine) as session:
            existing = session.scalar(
                select(AccountEquityPointRecord).where(
                    AccountEquityPointRecord.mode == snapshot.mode,
                    AccountEquityPointRecord.occurred_at == occurred_at,
                )
            )
            if existing is not None:
                return self._to_domain(existing)
            record = AccountEquityPointRecord(
                mode=snapshot.mode,
                occurred_at=occurred_at,
                total_equity=snapshot.total_futures_equity,
                available_balance=snapshot.available_futures_balance,
                used_margin=snapshot.used_margin,
                margin_usage_percentage=snapshot.margin_usage_percentage,
                realized_pnl_total=snapshot.realized_pnl_total,
                unrealized_pnl=snapshot.unrealized_pnl,
                fees_total=snapshot.fees_total,
                funding_total=snapshot.funding_total,
                net_pnl_total=snapshot.net_pnl_total,
                open_exposure=snapshot.open_exposure,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def series(
        self,
        mode: PerformanceMode,
        period: PerformancePeriod,
        *,
        now: datetime | None = None,
        maximum_points: int = 5000,
    ) -> AccountPerformanceSeries:
        if maximum_points < 2 or maximum_points > 20_000:
            raise ValueError("maximum_points must be between 2 and 20000.")
        generated_at = self._utc(now or datetime.now(UTC))
        cutoff = self._cutoff(period, generated_at)
        statement = (
            select(AccountEquityPointRecord)
            .where(AccountEquityPointRecord.mode == mode)
            .order_by(AccountEquityPointRecord.occurred_at.asc())
        )
        if cutoff is not None:
            statement = statement.where(AccountEquityPointRecord.occurred_at >= cutoff)
        with Session(self._database_engine) as session:
            records = list(session.scalars(statement))
        if len(records) > maximum_points:
            records = self._downsample(records, maximum_points)
        points = tuple(self._to_domain(record) for record in records)
        if not points:
            return AccountPerformanceSeries(
                mode=mode,
                period=period,
                generated_at=generated_at,
                points=(),
                baseline_equity=None,
                ending_equity=None,
                equity_change=None,
                equity_change_percentage=None,
                maximum_drawdown_percentage=None,
                realized_pnl_total=None,
                unrealized_pnl=None,
                fees_total=None,
                funding_total=None,
                net_pnl_total=None,
                open_exposure=None,
            )
        first = points[0]
        latest = points[-1]
        equity_change = latest.total_equity - first.total_equity
        with localcontext() as context:
            context.prec = 40
            equity_change_percentage = (
                (equity_change / first.total_equity) * Decimal("100")
                if first.total_equity != 0
                else None
            )
        return AccountPerformanceSeries(
            mode=mode,
            period=period,
            generated_at=generated_at,
            points=points,
            baseline_equity=first.total_equity,
            ending_equity=latest.total_equity,
            equity_change=equity_change,
            equity_change_percentage=equity_change_percentage,
            maximum_drawdown_percentage=self._maximum_drawdown(points),
            realized_pnl_total=latest.realized_pnl_total - first.realized_pnl_total,
            unrealized_pnl=latest.unrealized_pnl,
            fees_total=latest.fees_total - first.fees_total,
            funding_total=latest.funding_total - first.funding_total,
            net_pnl_total=latest.net_pnl_total - first.net_pnl_total,
            open_exposure=latest.open_exposure,
        )

    @staticmethod
    def _maximum_drawdown(points: tuple[AccountEquityPoint, ...]) -> Decimal:
        peak: Decimal | None = None
        maximum = Decimal("0")
        with localcontext() as context:
            context.prec = 40
            for point in points:
                if peak is None or point.total_equity > peak:
                    peak = point.total_equity
                if peak is None or peak <= 0:
                    continue
                drawdown = ((peak - point.total_equity) / peak) * Decimal("100")
                if drawdown > maximum:
                    maximum = drawdown
        return maximum

    @staticmethod
    def _cutoff(period: PerformancePeriod, now: datetime) -> datetime | None:
        if period == "all":
            return None
        if period == "7d":
            return now - timedelta(days=7)
        if period == "30d":
            return now - timedelta(days=30)
        riyadh = ZoneInfo("Asia/Riyadh")
        local_now = now.astimezone(riyadh)
        local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return local_midnight.astimezone(UTC)

    @staticmethod
    def _downsample(
        records: list[AccountEquityPointRecord], maximum_points: int
    ) -> list[AccountEquityPointRecord]:
        if len(records) <= maximum_points:
            return records
        last_index = len(records) - 1
        selected_indices = {
            round(index * last_index / (maximum_points - 1))
            for index in range(maximum_points)
        }
        return [records[index] for index in sorted(selected_indices)]

    @classmethod
    def _to_domain(cls, record: AccountEquityPointRecord) -> AccountEquityPoint:
        return AccountEquityPoint(
            point_id=record.point_id,
            mode=record.mode,
            occurred_at=cls._utc(record.occurred_at),
            total_equity=record.total_equity,
            available_balance=record.available_balance,
            used_margin=record.used_margin,
            margin_usage_percentage=record.margin_usage_percentage,
            realized_pnl_total=record.realized_pnl_total,
            unrealized_pnl=record.unrealized_pnl,
            fees_total=record.fees_total,
            funding_total=record.funding_total,
            net_pnl_total=record.net_pnl_total,
            open_exposure=record.open_exposure,
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
