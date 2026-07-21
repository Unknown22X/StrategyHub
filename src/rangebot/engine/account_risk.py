"""Persisted account-wide policy and daily Gate risk calculations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Integer, Numeric
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.account_risk import (
    AccountRiskPolicy,
    AccountRiskPolicyUpdate,
    AccountRiskStatus,
)
from rangebot.domain.performance import PerformanceMode
from rangebot.engine.performance import AccountPerformanceRepository
from rangebot.engine.trade_history import TradeHistoryRepository


class AccountRiskBase(DeclarativeBase):
    pass


class AccountRiskPolicyRecord(AccountRiskBase):
    __tablename__ = "account_risk_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    losing_trade_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_trade_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountRiskPolicyRepository:
    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine
        self._lock = RLock()

    def get(self) -> AccountRiskPolicy:
        with self._lock, Session(self._database_engine) as session:
            record = session.get(AccountRiskPolicyRecord, 1)
            if record is None:
                record = self._default_record()
                session.add(record)
                session.commit()
                session.refresh(record)
            return self._to_domain(record)

    def update(self, change: AccountRiskPolicyUpdate) -> AccountRiskPolicy:
        with self._lock, Session(self._database_engine) as session:
            record = session.get(AccountRiskPolicyRecord, 1)
            if record is None:
                record = self._default_record()
                session.add(record)
            record.daily_loss_limit = change.daily_loss_limit
            record.losing_trade_limit = change.losing_trade_limit
            record.automatic_trade_limit = change.automatic_trade_limit
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    @staticmethod
    def _default_record() -> AccountRiskPolicyRecord:
        return AccountRiskPolicyRecord(
            id=1,
            daily_loss_limit=Decimal("100"),
            losing_trade_limit=3,
            automatic_trade_limit=5,
            revision=1,
            updated_at=datetime.now(UTC),
        )

    @staticmethod
    def _to_domain(record: AccountRiskPolicyRecord) -> AccountRiskPolicy:
        updated_at = record.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return AccountRiskPolicy(
            daily_loss_limit=record.daily_loss_limit,
            losing_trade_limit=record.losing_trade_limit,
            automatic_trade_limit=record.automatic_trade_limit,
            revision=record.revision,
            updated_at=updated_at,
        )


class AccountRiskService:
    """Calculate fail-closed daily risk from Gate equity and immutable fills."""

    def __init__(
        self,
        policy_repository: AccountRiskPolicyRepository,
        performance_repository: AccountPerformanceRepository,
        trade_history_repository: TradeHistoryRepository,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy_repository
        self._performance = performance_repository
        self._trades = trade_history_repository
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def status(
        self,
        environment: Literal["testnet", "live"],
    ) -> AccountRiskStatus:
        now = self._utc(self._now_factory())
        day_start = self._riyadh_day_start(now)
        policy = self._policy.get()
        performance = self._performance.series(
            cast(PerformanceMode, environment),
            "today",
            now=now,
            maximum_points=20_000,
        )
        baseline = performance.baseline_equity
        current = performance.ending_equity
        baseline_ready = baseline is not None and current is not None
        equity_loss = (
            max(Decimal("0"), baseline - current)
            if baseline is not None and current is not None
            else Decimal("0")
        )
        losing_trades, automatic_trades = self._trades.daily_risk_counts(
            environment=environment,
            since=day_start,
        )
        reasons: list[str] = []
        if not baseline_ready:
            reasons.append("daily_baseline_unavailable")
        if equity_loss >= policy.daily_loss_limit:
            reasons.append("daily_loss_limit_reached")
        if losing_trades >= policy.losing_trade_limit:
            reasons.append("losing_trade_limit_reached")
        automatic_limit_reached = automatic_trades >= policy.automatic_trade_limit
        if automatic_limit_reached:
            reasons.append("automatic_trade_limit_reached")
        common_blocked = (
            not baseline_ready
            or equity_loss >= policy.daily_loss_limit
            or losing_trades >= policy.losing_trade_limit
        )
        return AccountRiskStatus(
            environment=environment,
            day=now.astimezone(ZoneInfo("Asia/Riyadh")).date(),
            baseline_ready=baseline_ready,
            baseline_equity=baseline,
            current_equity=current,
            equity_loss_used=equity_loss,
            remaining_loss_allowance=max(
                Decimal("0"), policy.daily_loss_limit - equity_loss
            ),
            losing_trades=losing_trades,
            automatic_trades=automatic_trades,
            policy=policy,
            manual_entries_blocked=common_blocked,
            automatic_entries_blocked=common_blocked or automatic_limit_reached,
            blocked_reason_codes=tuple(reasons),
        )

    @staticmethod
    def _riyadh_day_start(value: datetime) -> datetime:
        local = AccountRiskService._utc(value).astimezone(ZoneInfo("Asia/Riyadh"))
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
