"""Persisted account-wide policy and immutable Riyadh daily risk baselines."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import RLock
from typing import Literal, cast
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, Date, DateTime, Integer, Numeric, String
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.account_risk import (
    AccountRiskLimitStatus,
    AccountRiskPolicy,
    AccountRiskPolicyUpdate,
    AccountRiskStatus,
    RiskLimitState,
)
from rangebot.domain.performance import PerformanceMode
from rangebot.engine.performance import AccountPerformanceRepository
from rangebot.engine.trade_history import TradeHistoryRepository


RIYADH = ZoneInfo("Asia/Riyadh")


class AccountRiskBase(DeclarativeBase):
    pass


class AccountRiskPolicyRecord(AccountRiskBase):
    __tablename__ = "account_risk_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_loss_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    daily_loss_limit: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    losing_trade_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    losing_trade_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    automatic_trade_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    automatic_trade_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class AccountDailyRiskBaselineRecord(AccountRiskBase):
    __tablename__ = "account_daily_risk_baseline"

    environment: Mapped[str] = mapped_column(String(16), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    baseline_equity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)


@dataclass(frozen=True)
class AccountDailyRiskBaseline:
    environment: Literal["testnet", "live"]
    day: date
    baseline_equity: Decimal
    captured_at: datetime
    source: str


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
            record.daily_loss_enabled = change.daily_loss_enabled
            record.daily_loss_limit = change.daily_loss_limit
            record.losing_trade_enabled = change.losing_trade_enabled
            record.losing_trade_limit = change.losing_trade_limit
            record.automatic_trade_enabled = change.automatic_trade_enabled
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
            daily_loss_enabled=True,
            daily_loss_limit=Decimal("100"),
            losing_trade_enabled=True,
            losing_trade_limit=3,
            automatic_trade_enabled=True,
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
            daily_loss_enabled=record.daily_loss_enabled,
            daily_loss_limit=record.daily_loss_limit,
            losing_trade_enabled=record.losing_trade_enabled,
            losing_trade_limit=record.losing_trade_limit,
            automatic_trade_enabled=record.automatic_trade_enabled,
            automatic_trade_limit=record.automatic_trade_limit,
            revision=record.revision,
            updated_at=updated_at,
        )


class AccountDailyRiskBaselineRepository:
    """Capture one environment/day baseline exactly once and never update it."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine
        self._lock = RLock()

    def get(
        self,
        environment: Literal["testnet", "live"],
        day: date,
    ) -> AccountDailyRiskBaseline | None:
        with self._lock, Session(self._database_engine) as session:
            record = session.get(
                AccountDailyRiskBaselineRecord,
                {"environment": environment, "day": day},
            )
            return self._to_domain(record) if record is not None else None

    def capture_if_missing(
        self,
        *,
        environment: Literal["testnet", "live"],
        day: date,
        baseline_equity: Decimal,
        captured_at: datetime,
        source: str = "first_reconciled_equity_point",
    ) -> AccountDailyRiskBaseline:
        if captured_at.tzinfo is None:
            raise ValueError("Daily risk baseline timestamp must be timezone-aware.")
        with self._lock, Session(self._database_engine) as session:
            identity = {"environment": environment, "day": day}
            record = session.get(AccountDailyRiskBaselineRecord, identity)
            if record is None:
                record = AccountDailyRiskBaselineRecord(
                    environment=environment,
                    day=day,
                    baseline_equity=baseline_equity,
                    captured_at=captured_at.astimezone(UTC),
                    source=source,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
            return self._to_domain(record)

    @staticmethod
    def _to_domain(record: AccountDailyRiskBaselineRecord) -> AccountDailyRiskBaseline:
        captured_at = record.captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        return AccountDailyRiskBaseline(
            environment=cast(Literal["testnet", "live"], record.environment),
            day=record.day,
            baseline_equity=record.baseline_equity,
            captured_at=captured_at,
            source=record.source,
        )


class AccountRiskService:
    """Calculate fail-closed daily risk from immutable baselines and immutable fills."""

    def __init__(
        self,
        policy_repository: AccountRiskPolicyRepository,
        baseline_repository: AccountDailyRiskBaselineRepository,
        performance_repository: AccountPerformanceRepository,
        trade_history_repository: TradeHistoryRepository,
        *,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._policy = policy_repository
        self._baselines = baseline_repository
        self._performance = performance_repository
        self._trades = trade_history_repository
        self._now_factory = now_factory or (lambda: datetime.now(UTC))

    def status(
        self,
        environment: Literal["testnet", "live"],
        *,
        synchronization_complete: bool = True,
    ) -> AccountRiskStatus:
        now = self._utc(self._now_factory())
        local_day = now.astimezone(RIYADH).date()
        day_start = self._riyadh_day_start(now)
        policy = self._policy.get()
        performance = self._performance.series(
            cast(PerformanceMode, environment),
            "today",
            now=now,
            maximum_points=20_000,
        )
        current = performance.ending_equity
        baseline = self._baselines.get(environment, local_day)
        if (
            baseline is None
            and synchronization_complete
            and performance.baseline_equity is not None
            and performance.points
        ):
            baseline = self._baselines.capture_if_missing(
                environment=environment,
                day=local_day,
                baseline_equity=performance.baseline_equity,
                captured_at=performance.points[0].occurred_at,
            )
        baseline_equity = baseline.baseline_equity if baseline is not None else None
        baseline_ready = baseline_equity is not None and current is not None
        equity_loss = (
            max(Decimal("0"), baseline_equity - current)
            if baseline_equity is not None and current is not None
            else Decimal("0")
        )
        losing_trades, automatic_trades = self._trades.daily_risk_counts(
            environment=environment,
            since=day_start,
        )

        risk_data_state = self._risk_data_state(
            synchronization_complete=synchronization_complete,
            baseline_equity=baseline_equity,
            current_equity=current,
        )
        daily_loss_state = self._limit_state(
            enabled=policy.daily_loss_enabled,
            synchronization_complete=synchronization_complete,
            data_ready=baseline_ready,
            reached=equity_loss >= policy.daily_loss_limit,
        )
        losing_trade_state = self._limit_state(
            enabled=policy.losing_trade_enabled,
            synchronization_complete=synchronization_complete,
            data_ready=True,
            reached=losing_trades >= policy.losing_trade_limit,
        )
        automatic_trade_state = self._limit_state(
            enabled=policy.automatic_trade_enabled,
            synchronization_complete=synchronization_complete,
            data_ready=True,
            reached=automatic_trades >= policy.automatic_trade_limit,
        )

        reasons: list[str] = []
        if not synchronization_complete:
            reasons.append("synchronization_incomplete")
        elif policy.daily_loss_enabled and current is None:
            reasons.append("risk_data_unavailable")
        elif policy.daily_loss_enabled and baseline_equity is None:
            reasons.append("daily_baseline_missing")
        if daily_loss_state == "reached":
            reasons.append("daily_loss_limit_reached")
        if losing_trade_state == "reached":
            reasons.append("losing_trade_limit_reached")
        if automatic_trade_state == "reached":
            reasons.append("automatic_trade_limit_reached")

        daily_data_blocked = policy.daily_loss_enabled and not baseline_ready
        common_blocked = (
            not synchronization_complete
            or daily_data_blocked
            or daily_loss_state == "reached"
            or losing_trade_state == "reached"
        )
        automatic_blocked = common_blocked or automatic_trade_state == "reached"
        remaining_loss = max(Decimal("0"), policy.daily_loss_limit - equity_loss)
        limits = (
            self._limit_status(
                key="daily_equity_loss",
                enabled=policy.daily_loss_enabled,
                state=daily_loss_state,
                unit="USDT",
                limit_value=policy.daily_loss_limit,
                used_value=equity_loss if baseline_ready else None,
                blocks_manual=daily_loss_state == "reached" or daily_data_blocked,
                blocks_automatic=daily_loss_state == "reached" or daily_data_blocked,
            ),
            self._limit_status(
                key="daily_losing_trades",
                enabled=policy.losing_trade_enabled,
                state=losing_trade_state,
                unit="trades",
                limit_value=Decimal(policy.losing_trade_limit),
                used_value=Decimal(losing_trades),
                blocks_manual=losing_trade_state == "reached",
                blocks_automatic=losing_trade_state == "reached",
            ),
            self._limit_status(
                key="daily_automatic_entries",
                enabled=policy.automatic_trade_enabled,
                state=automatic_trade_state,
                unit="entries",
                limit_value=Decimal(policy.automatic_trade_limit),
                used_value=Decimal(automatic_trades),
                blocks_manual=False,
                blocks_automatic=automatic_trade_state == "reached",
            ),
        )
        return AccountRiskStatus(
            environment=environment,
            day=local_day,
            synchronization_complete=synchronization_complete,
            risk_data_state=risk_data_state,
            baseline_ready=baseline_ready,
            baseline_equity=baseline_equity,
            baseline_captured_at=baseline.captured_at if baseline is not None else None,
            current_equity=current,
            equity_loss_used=equity_loss,
            remaining_loss_allowance=remaining_loss,
            losing_trades=losing_trades,
            automatic_trades=automatic_trades,
            policy=policy,
            limits=limits,
            manual_entries_blocked=common_blocked,
            automatic_entries_blocked=automatic_blocked,
            blocked_reason_codes=tuple(reasons),
        )

    @staticmethod
    def _risk_data_state(
        *,
        synchronization_complete: bool,
        baseline_equity: Decimal | None,
        current_equity: Decimal | None,
    ) -> Literal[
        "ready",
        "baseline_missing",
        "account_data_unavailable",
        "synchronizing",
    ]:
        if not synchronization_complete:
            return "synchronizing"
        if current_equity is None:
            return "account_data_unavailable"
        if baseline_equity is None:
            return "baseline_missing"
        return "ready"

    @staticmethod
    def _limit_state(
        *,
        enabled: bool,
        synchronization_complete: bool,
        data_ready: bool,
        reached: bool,
    ) -> RiskLimitState:
        if not enabled:
            return "disabled"
        if not synchronization_complete:
            return "synchronizing"
        if not data_ready:
            return "data_unavailable"
        return "reached" if reached else "not_reached"

    @staticmethod
    def _limit_status(
        *,
        key: Literal[
            "daily_equity_loss",
            "daily_losing_trades",
            "daily_automatic_entries",
        ],
        enabled: bool,
        state: RiskLimitState,
        unit: Literal["USDT", "trades", "entries"],
        limit_value: Decimal,
        used_value: Decimal | None,
        blocks_manual: bool,
        blocks_automatic: bool,
    ) -> AccountRiskLimitStatus:
        remaining = (
            max(Decimal("0"), limit_value - used_value)
            if enabled and used_value is not None
            else None
        )
        return AccountRiskLimitStatus(
            key=key,
            enabled=enabled,
            state=state,
            unit=unit,
            limit_value=limit_value,
            used_value=used_value,
            remaining_value=remaining,
            blocks_manual_entries=blocks_manual,
            blocks_automatic_entries=blocks_automatic,
        )

    @staticmethod
    def _riyadh_day_start(value: datetime) -> datetime:
        local = AccountRiskService._utc(value).astimezone(RIYADH)
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
