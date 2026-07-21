"""Read-only projection of sanitized engine activity from existing audit records."""

from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from rangebot.domain.activity import ActivityEvent, ActivityQuery
from rangebot.engine.discovery_repository import BacktestRunRecord, DiscoveryScanRecord
from rangebot.engine.repository import (
    ExchangeRequestRecord,
    PaperAccountAuditRecord,
    RuntimeStateRecord,
)
from rangebot.engine.strategy_instances import (
    StrategyDecisionRecord,
    StrategyInstanceRecord,
)


class ActivityFeedService:
    """Combine existing audit sources without becoming a new trading truth."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def list(self, query: ActivityQuery) -> list[ActivityEvent]:
        fetch_limit = min(max(query.limit * 3, 100), 1000)
        with Session(self._database_engine) as session:
            strategy_names = {
                record.instance_id: record.name
                for record in session.scalars(select(StrategyInstanceRecord))
            }
            events = [
                *self._strategy_decisions(session, strategy_names, fetch_limit),
                *self._strategy_states(session, fetch_limit),
                *self._exchange_requests(session, strategy_names, fetch_limit),
                *self._paper_audit(session, fetch_limit),
                *self._research(session, fetch_limit),
                *self._runtime(session),
            ]

        filtered = [event for event in events if self._matches(event, query)]
        filtered.sort(key=lambda event: event.occurred_at, reverse=True)
        return filtered[: query.limit]

    @classmethod
    def _strategy_decisions(
        cls,
        session: Session,
        strategy_names: dict[str, str],
        limit: int,
    ) -> list[ActivityEvent]:
        records = session.scalars(
            select(StrategyDecisionRecord)
            .order_by(StrategyDecisionRecord.occurred_at.desc())
            .limit(limit)
        )
        return [
            ActivityEvent(
                event_id=f"decision:{record.decision_id}",
                occurred_at=cls._utc(record.occurred_at),
                category="decision",
                severity="positive" if record.eligible else "neutral",
                title_ar=f"قرار استراتيجية: {record.signal}",
                detail_ar=cls._decision_detail(record.reason_codes_json),
                symbol=record.symbol,
                strategy_instance_id=record.instance_id,
                strategy_name=strategy_names.get(record.instance_id),
                status="eligible" if record.eligible else "not_eligible",
                source_identity=str(record.decision_id),
            )
            for record in records
        ]

    @classmethod
    def _strategy_states(cls, session: Session, limit: int) -> list[ActivityEvent]:
        records = session.scalars(
            select(StrategyInstanceRecord)
            .order_by(StrategyInstanceRecord.updated_at.desc())
            .limit(limit)
        )
        return [
            ActivityEvent(
                event_id=f"strategy:{record.instance_id}:{record.revision}",
                occurred_at=cls._utc(record.updated_at),
                category="strategy",
                severity=cls._strategy_severity(record.status),
                title_ar=f"حالة الاستراتيجية: {record.name}",
                detail_ar=f"الحالة الحالية {record.status} على {record.symbol}",
                environment=record.environment,
                symbol=record.symbol,
                strategy_instance_id=record.instance_id,
                strategy_name=record.name,
                status=record.status,
                source_identity=record.instance_id,
            )
            for record in records
        ]

    @classmethod
    def _exchange_requests(
        cls,
        session: Session,
        strategy_names: dict[str, str],
        limit: int,
    ) -> list[ActivityEvent]:
        records = session.scalars(
            select(ExchangeRequestRecord)
            .order_by(ExchangeRequestRecord.updated_at.desc())
            .limit(limit)
        )
        events: list[ActivityEvent] = []
        for record in records:
            symbol, instance_id = cls._safe_exchange_context(record.payload_json)
            events.append(
                ActivityEvent(
                    event_id=f"order:{record.client_request_id}",
                    occurred_at=cls._utc(record.updated_at),
                    category="order",
                    severity=cls._order_severity(record.status),
                    title_ar=f"عملية تداول: {record.kind}",
                    detail_ar=f"الحالة {record.status}",
                    environment=record.mode,
                    symbol=symbol,
                    strategy_instance_id=instance_id,
                    strategy_name=strategy_names.get(instance_id) if instance_id else None,
                    status=record.status,
                    source_identity=record.client_request_id,
                )
            )
        return events

    @classmethod
    def _paper_audit(cls, session: Session, limit: int) -> list[ActivityEvent]:
        records = session.scalars(
            select(PaperAccountAuditRecord)
            .order_by(PaperAccountAuditRecord.occurred_at.desc())
            .limit(limit)
        )
        return [
            ActivityEvent(
                event_id=f"paper:{record.id}",
                occurred_at=cls._utc(record.occurred_at),
                category="risk" if cls._is_risk_action(record.action) else "paper",
                severity=cls._paper_severity(record.action),
                title_ar=f"حدث Paper: {record.action}",
                detail_ar=record.reason,
                environment="paper",
                status=record.action,
                source_identity=str(record.id),
            )
            for record in records
        ]

    @classmethod
    def _research(cls, session: Session, limit: int) -> list[ActivityEvent]:
        scans = session.scalars(
            select(DiscoveryScanRecord)
            .order_by(DiscoveryScanRecord.created_at.desc())
            .limit(limit)
        )
        backtests = session.scalars(
            select(BacktestRunRecord)
            .order_by(BacktestRunRecord.created_at.desc())
            .limit(limit)
        )
        events = [
            ActivityEvent(
                event_id=f"scan:{record.scan_id}",
                occurred_at=cls._utc(record.created_at),
                category="research",
                severity="neutral",
                title_ar="اكتمل فحص فرص استراتيجية",
                detail_ar=(
                    f"{record.strategy_type_id} · إطار {record.timeframe_minutes} دقيقة"
                ),
                status="completed",
                source_identity=record.scan_id,
            )
            for record in scans
        ]
        events.extend(
            ActivityEvent(
                event_id=f"backtest:{record.backtest_id}",
                occurred_at=cls._utc(record.created_at),
                category="research",
                severity="neutral",
                title_ar="اكتمل اختبار تاريخي",
                detail_ar=(
                    f"{record.strategy_type_id} · {record.symbol} · "
                    f"إطار {record.timeframe_minutes} دقيقة"
                ),
                symbol=record.symbol,
                status="completed",
                source_identity=record.backtest_id,
            )
            for record in backtests
        )
        return events

    @classmethod
    def _runtime(cls, session: Session) -> list[ActivityEvent]:
        record = session.get(RuntimeStateRecord, 1)
        if record is None:
            return []
        return [
            ActivityEvent(
                event_id=f"runtime:{record.state_revision}",
                occurred_at=cls._utc(record.started_at),
                category="system",
                severity="positive" if record.lifecycle == "running" else "warning",
                title_ar="حالة محرك RangeBot",
                detail_ar=f"المحرك في حالة {record.lifecycle}",
                status=record.lifecycle,
                source_identity=str(record.state_revision),
            )
        ]

    @staticmethod
    def _matches(event: ActivityEvent, query: ActivityQuery) -> bool:
        if query.category is not None and event.category != query.category:
            return False
        if query.environment is not None and event.environment != query.environment:
            return False
        if (
            query.strategy_instance_id is not None
            and event.strategy_instance_id != query.strategy_instance_id
        ):
            return False
        if query.symbol is not None and event.symbol != query.symbol:
            return False
        if query.since is not None and event.occurred_at < ActivityFeedService._utc(query.since):
            return False
        return True

    @staticmethod
    def _decision_detail(reason_codes_json: str) -> str:
        try:
            values = json.loads(reason_codes_json)
        except json.JSONDecodeError:
            return "لا توجد أسباب قابلة للعرض."
        if not isinstance(values, list) or not values:
            return "لا توجد أسباب مسجلة."
        return "، ".join(str(value) for value in values[:8])

    @staticmethod
    def _safe_exchange_context(payload_json: str) -> tuple[str | None, str | None]:
        """Extract only non-secret display identifiers from the persisted request."""
        try:
            payload = json.loads(payload_json)
        except json.JSONDecodeError:
            return None, None
        if not isinstance(payload, dict):
            return None, None
        symbol = payload.get("symbol") or payload.get("contract")
        instance_id = payload.get("instance_id")
        return (
            str(symbol) if isinstance(symbol, str) else None,
            str(instance_id) if isinstance(instance_id, str) else None,
        )

    @staticmethod
    def _strategy_severity(status: str) -> str:
        if status == "error":
            return "negative"
        if status in {"running", "monitoring"}:
            return "positive"
        if status in {"paused", "starting", "stopping", "recovering"}:
            return "warning"
        return "neutral"

    @staticmethod
    def _order_severity(status: str) -> str:
        lowered = status.lower()
        if any(value in lowered for value in ("reject", "fail", "error")):
            return "negative"
        if any(value in lowered for value in ("filled", "submitted", "accepted")):
            return "positive"
        if any(value in lowered for value in ("pending", "created")):
            return "warning"
        return "neutral"

    @staticmethod
    def _paper_severity(action: str) -> str:
        lowered = action.lower()
        if any(value in lowered for value in ("reject", "error", "fail", "blocked")):
            return "negative"
        if any(value in lowered for value in ("fill", "close", "restore", "reset")):
            return "positive"
        if ActivityFeedService._is_risk_action(action):
            return "warning"
        return "neutral"

    @staticmethod
    def _is_risk_action(action: str) -> bool:
        lowered = action.lower()
        return any(
            value in lowered
            for value in ("risk", "emergency", "protection", "stale", "limit")
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
