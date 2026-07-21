"""Durable immutable trade-fill history and ownership attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from threading import RLock

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    case,
    func,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.trades import TradeFill, TradeFillCreate, TradeHistorySummary


class TradeHistoryBase(DeclarativeBase):
    pass


class TradeFillRecord(TradeHistoryBase):
    __tablename__ = "trade_fill"
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "external_trade_id",
            name="uq_trade_fill_environment_external_id",
        ),
        Index("ix_trade_fill_occurred_at", "occurred_at"),
        Index("ix_trade_fill_contract", "contract", "occurred_at"),
        Index("ix_trade_fill_instance", "instance_id", "occurred_at"),
        Index("ix_trade_fill_run", "run_id", "occurred_at"),
        Index("ix_trade_fill_order", "environment", "order_id"),
    )

    fill_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    external_trade_id: Mapped[str] = mapped_column(String(200), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(200))
    contract: Mapped[str] = mapped_column(String(64), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    position_effect: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    close_quantity: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    trade_value: Mapped[Decimal] = mapped_column(Numeric(30, 12), nullable=False)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(32))
    instance_id: Mapped[str | None] = mapped_column(String(36))
    run_id: Mapped[str | None] = mapped_column(String(36))
    strategy_name_snapshot: Mapped[str | None] = mapped_column(String(200))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradeHistoryRepository:
    """Persist fills idempotently and attach immutable execution ownership."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine
        self._lock = RLock()

    def record(self, change: TradeFillCreate) -> TradeFill:
        with self._lock, Session(self._database_engine) as session:
            existing = self._find(session, change.environment, change.external_trade_id)
            if existing is not None:
                return self._to_domain(existing)
            record = TradeFillRecord(
                environment=change.environment,
                external_trade_id=change.external_trade_id,
                order_id=change.order_id,
                contract=change.contract,
                side=change.side,
                position_effect=change.position_effect,
                quantity=change.quantity,
                price=change.price,
                fee=change.fee,
                role=change.role,
                close_quantity=change.close_quantity,
                trade_value=change.trade_value,
                realized_pnl=change.realized_pnl,
                occurred_at=self._with_utc(change.occurred_at),
                source=change.source,
                origin=change.origin,
                instance_id=change.instance_id,
                run_id=change.run_id,
                strategy_name_snapshot=change.strategy_name_snapshot,
                ingested_at=datetime.now(UTC),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    def record_many(self, changes: tuple[TradeFillCreate, ...]) -> tuple[TradeFill, ...]:
        return tuple(self.record(change) for change in changes)

    def attach_order_ownership(
        self,
        *,
        environment: str,
        order_id: str,
        origin: str,
        instance_id: str | None,
        run_id: str | None,
        strategy_name_snapshot: str | None,
    ) -> int:
        """Attach ownership only to rows that have not already been attributed."""
        with self._lock, Session(self._database_engine) as session:
            records = list(
                session.scalars(
                    select(TradeFillRecord).where(
                        TradeFillRecord.environment == environment,
                        TradeFillRecord.order_id == order_id,
                    )
                )
            )
            updated = 0
            for record in records:
                if record.origin not in (None, "external") or record.instance_id is not None:
                    continue
                record.origin = origin
                record.instance_id = instance_id
                record.run_id = run_id
                record.strategy_name_snapshot = strategy_name_snapshot
                updated += 1
            session.commit()
            return updated

    def attach_fill_ownership(
        self,
        *,
        environment: str,
        external_trade_id: str,
        origin: str,
        instance_id: str | None,
        run_id: str | None,
        strategy_name_snapshot: str | None,
    ) -> TradeFill:
        with self._lock, Session(self._database_engine) as session:
            record = self._find(session, environment, external_trade_id)
            if record is None:
                raise LookupError(f"Unknown trade fill: {environment}/{external_trade_id}")
            if record.origin is None:
                record.origin = origin
                record.instance_id = instance_id
                record.run_id = run_id
                record.strategy_name_snapshot = strategy_name_snapshot
                session.commit()
                session.refresh(record)
            return self._to_domain(record)

    def list(
        self,
        *,
        environment: str | None = None,
        contract: str | None = None,
        instance_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[TradeFill]:
        if limit < 1 or limit > 2000:
            raise ValueError("Trade-history limit must be between 1 and 2000.")
        statement = select(TradeFillRecord).order_by(
            TradeFillRecord.occurred_at.desc(), TradeFillRecord.fill_id.desc()
        )
        if environment is not None:
            statement = statement.where(TradeFillRecord.environment == environment)
        if contract is not None:
            statement = statement.where(TradeFillRecord.contract == contract)
        if instance_id is not None:
            statement = statement.where(TradeFillRecord.instance_id == instance_id)
        if run_id is not None:
            statement = statement.where(TradeFillRecord.run_id == run_id)
        if since is not None:
            statement = statement.where(TradeFillRecord.occurred_at >= self._with_utc(since))
        with Session(self._database_engine) as session:
            return [
                self._to_domain(record)
                for record in session.scalars(statement.limit(limit))
            ]

    def daily_risk_counts(
        self,
        *,
        environment: str,
        since: datetime,
    ) -> tuple[int, int]:
        """Return distinct losing closes and automatic entry orders since a UTC cutoff."""
        statement = select(
            TradeFillRecord.order_id,
            TradeFillRecord.external_trade_id,
            TradeFillRecord.realized_pnl,
            TradeFillRecord.close_quantity,
            TradeFillRecord.origin,
            TradeFillRecord.position_effect,
        ).where(
            TradeFillRecord.environment == environment,
            TradeFillRecord.occurred_at >= self._with_utc(since),
        )
        losing_orders: set[str] = set()
        automatic_orders: set[str] = set()
        with Session(self._database_engine) as session:
            rows = session.execute(statement)
            for order_id, trade_id, realized_pnl, close_quantity, origin, effect in rows:
                identity = str(order_id or trade_id)
                if close_quantity > 0 and realized_pnl is not None and realized_pnl < 0:
                    losing_orders.add(identity)
                if origin == "automatic_strategy" and effect == "open":
                    automatic_orders.add(identity)
        return len(losing_orders), len(automatic_orders)

    def latest_entry_time(
        self,
        *,
        environment: str,
        contract: str,
        instance_id: str,
    ) -> datetime | None:
        statement = select(func.max(TradeFillRecord.occurred_at)).where(
            TradeFillRecord.environment == environment,
            TradeFillRecord.contract == contract,
            TradeFillRecord.instance_id == instance_id,
            TradeFillRecord.position_effect == "open",
        )
        with Session(self._database_engine) as session:
            value = session.scalar(statement)
        return self._with_utc(value) if value is not None else None

    def summary(
        self,
        *,
        environment: str | None = None,
        contract: str | None = None,
        instance_id: str | None = None,
        run_id: str | None = None,
        since: datetime | None = None,
    ) -> TradeHistorySummary:
        statement = select(
            func.count(TradeFillRecord.fill_id),
            func.count(TradeFillRecord.realized_pnl),
            func.coalesce(
                func.sum(TradeFillRecord.quantity - TradeFillRecord.close_quantity),
                0,
            ),
            func.coalesce(func.sum(TradeFillRecord.close_quantity), 0),
            func.coalesce(func.sum(TradeFillRecord.realized_pnl), 0),
            func.coalesce(
                func.sum(case((TradeFillRecord.realized_pnl > 0, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(case((TradeFillRecord.realized_pnl < 0, 1), else_=0)),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (TradeFillRecord.realized_pnl > 0, TradeFillRecord.realized_pnl),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (TradeFillRecord.realized_pnl < 0, TradeFillRecord.realized_pnl),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(func.sum(TradeFillRecord.fee), 0),
            func.coalesce(func.sum(func.abs(TradeFillRecord.trade_value)), 0),
        )
        statement = self._filtered_statement(
            statement,
            environment=environment,
            contract=contract,
            instance_id=instance_id,
            run_id=run_id,
            since=since,
        )
        with Session(self._database_engine) as session:
            values = session.execute(statement).one()
        known_realized = int(values[1])
        winning_fills = int(values[5])
        losing_fills = int(values[6])
        gross_profit = Decimal(str(values[7])) if winning_fills else None
        gross_loss = Decimal(str(values[8])) if losing_fills else None
        decisive_fills = winning_fills + losing_fills
        return TradeHistorySummary(
            fills=int(values[0]),
            opened_quantity=max(Decimal(str(values[2])), Decimal("0")),
            closed_quantity=Decimal(str(values[3])),
            realized_pnl=(Decimal(str(values[4])) if known_realized else None),
            realized_pnl_known_fills=known_realized,
            winning_fills=winning_fills,
            losing_fills=losing_fills,
            win_rate_percentage=(
                Decimal(winning_fills) / Decimal(decisive_fills) * Decimal("100")
                if decisive_fills
                else None
            ),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            average_win=(
                gross_profit / Decimal(winning_fills)
                if gross_profit is not None and winning_fills
                else None
            ),
            average_loss=(
                gross_loss / Decimal(losing_fills)
                if gross_loss is not None and losing_fills
                else None
            ),
            profit_factor=(
                gross_profit / abs(gross_loss)
                if gross_profit is not None
                and gross_loss is not None
                and gross_loss != 0
                else None
            ),
            fees=Decimal(str(values[9])),
            gross_trade_value=Decimal(str(values[10])),
        )

    @classmethod
    def _filtered_statement(
        cls,
        statement,
        *,
        environment: str | None,
        contract: str | None,
        instance_id: str | None,
        run_id: str | None,
        since: datetime | None,
    ):
        if environment is not None:
            statement = statement.where(TradeFillRecord.environment == environment)
        if contract is not None:
            statement = statement.where(TradeFillRecord.contract == contract)
        if instance_id is not None:
            statement = statement.where(TradeFillRecord.instance_id == instance_id)
        if run_id is not None:
            statement = statement.where(TradeFillRecord.run_id == run_id)
        if since is not None:
            statement = statement.where(
                TradeFillRecord.occurred_at >= cls._with_utc(since)
            )
        return statement

    @staticmethod
    def _find(
        session: Session, environment: str, external_trade_id: str
    ) -> TradeFillRecord | None:
        return session.scalar(
            select(TradeFillRecord).where(
                TradeFillRecord.environment == environment,
                TradeFillRecord.external_trade_id == external_trade_id,
            )
        )

    @staticmethod
    def _with_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    @classmethod
    def _to_domain(cls, record: TradeFillRecord) -> TradeFill:
        return TradeFill(
            fill_id=record.fill_id,
            environment=record.environment,
            external_trade_id=record.external_trade_id,
            order_id=record.order_id,
            contract=record.contract,
            side=record.side,
            position_effect=record.position_effect,
            quantity=record.quantity,
            price=record.price,
            fee=record.fee,
            role=record.role,
            close_quantity=record.close_quantity,
            trade_value=record.trade_value,
            realized_pnl=record.realized_pnl,
            occurred_at=cls._with_utc(record.occurred_at),
            source=record.source,
            origin=record.origin,
            instance_id=record.instance_id,
            run_id=record.run_id,
            strategy_name_snapshot=record.strategy_name_snapshot,
            ingested_at=cls._with_utc(record.ingested_at),
        )
