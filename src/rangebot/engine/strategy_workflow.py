"""Persistence and invariants for the product-level strategy workflow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from threading import RLock
from typing import Any
from uuid import uuid4

from pydantic_core import to_jsonable_python
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.backtesting import BacktestRunRequest, StoredBacktestRun
from rangebot.domain.discovery import StoredStrategyScan
from rangebot.domain.strategy import StrategyInstanceCreate
from rangebot.domain.strategy_workflow import (
    BotDeployment,
    BotDeploymentCreate,
    OpportunityConversionRequest,
    OpportunityStatusUpdate,
    SetupApprovalRequest,
    SetupBacktestRequest,
    StrategyCoinSetup,
    StrategyCoinSetupCreate,
    StrategyCoinSetupUpdate,
    StrategyCoinSetupVersion,
    StrategyOpportunity,
    StrategyExecutionPlan,
    StrategyPreset,
    StrategyPresetCreate,
    StrategyPresetUpdate,
    StrategyPresetVersion,
    StrategySetupApproval,
    StrategySetupDefaults,
    StrategyTemplate,
    StrategyTemplateCreate,
    StrategyTemplateUpdate,
    StrategyTemplateVersion,
    WorkflowSummary,
)
from rangebot.engine.strategy_instances import StrategyInstanceRepository
from rangebot.engine.strategy_registry import StrategyRegistry


class StrategyWorkflowBase(DeclarativeBase):
    pass


class StrategyTemplateRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_template"

    template_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    setup_defaults_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrategyTemplateVersionRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_template_version"

    version_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    template_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    setup_defaults_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StrategyCoinSetupRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_coin_setup"

    setup_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(36), nullable=False)
    template_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_instance_id: Mapped[str | None] = mapped_column(String(36))
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    price_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_state: Mapped[str] = mapped_column(String(16), nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    configuration_overrides_json: Mapped[str] = mapped_column(Text, nullable=False)
    setup_defaults_override_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    latest_backtest_id: Mapped[str | None] = mapped_column(String(36))
    latest_backtest_revision: Mapped[int | None] = mapped_column(Integer)
    latest_backtest_assessment: Mapped[str | None] = mapped_column(String(32))
    source_opportunity_id: Mapped[str | None] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrategyCoinSetupVersionRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_coin_setup_version"

    version_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    setup_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class StrategySetupApprovalRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_setup_approval"

    approval_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    setup_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StrategyOpportunityRecord(StrategyWorkflowBase):
    __tablename__ = "strategy_opportunity"

    opportunity_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    strategy_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_json: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange: Mapped[str] = mapped_column(String(50), nullable=False)
    market_type: Mapped[str] = mapped_column(String(32), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 12))
    price_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_state: Mapped[str] = mapped_column(String(16), nullable=False)
    scanner_score: Mapped[int] = mapped_column(Integer, nullable=False)
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    eligible_now: Mapped[bool] = mapped_column(Boolean, nullable=False)
    qualifying_factors_json: Mapped[str] = mapped_column(Text, nullable=False)
    explanation_ar: Mapped[str] = mapped_column(Text, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    converted_setup_id: Mapped[str | None] = mapped_column(String(36))


class BotDeploymentRecord(StrategyWorkflowBase):
    __tablename__ = "bot_deployment"

    deployment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    setup_id: Mapped[str] = mapped_column(String(36), nullable=False)
    setup_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str] = mapped_column(String(36), nullable=False)
    template_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_type_id: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    configuration_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class StrategyWorkflowRepository:
    """Own the deliberate template → setup → approval → deployment workflow."""

    def __init__(
        self,
        database_engine: Engine,
        registry: StrategyRegistry,
        strategy_instances: StrategyInstanceRepository,
    ) -> None:
        self._database_engine = database_engine
        self._registry = registry
        self._strategy_instances = strategy_instances
        self._lock = RLock()

    # Strategy templates -------------------------------------------------
    def list_templates(self, include_archived: bool = False) -> list[StrategyTemplate]:
        with Session(self._database_engine) as session:
            statement = select(StrategyTemplateRecord).order_by(
                StrategyTemplateRecord.updated_at.desc()
            )
            if not include_archived:
                statement = statement.where(StrategyTemplateRecord.status != "archived")
            records = session.scalars(statement)
            return [self._template_to_domain(session, record) for record in records]

    def get_template(self, template_id: str) -> StrategyTemplate:
        with Session(self._database_engine) as session:
            return self._template_to_domain(
                session, self._template(session, template_id)
            )

    def create_template(self, change: StrategyTemplateCreate) -> StrategyTemplate:
        self._validate_template(change)
        now = datetime.now(UTC)
        record = StrategyTemplateRecord(
            template_id=str(uuid4()),
            type_id=change.type_id,
            name=change.name,
            description=change.description,
            status=change.status,
            current_revision=1,
            timeframe_minutes=change.timeframe_minutes,
            direction=change.direction,
            configuration_json=self._json(change.configuration),
            setup_defaults_json=change.setup_defaults.model_dump_json(),
            created_at=now,
            updated_at=now,
            archived_at=None,
        )
        with self._lock, Session(self._database_engine) as session:
            session.add(record)
            session.add(self._template_version_record(record, now))
            session.commit()
            session.refresh(record)
            return self._template_to_domain(session, record)

    def update_template(
        self, template_id: str, change: StrategyTemplateUpdate
    ) -> StrategyTemplate:
        with self._lock, Session(self._database_engine) as session:
            record = self._template(session, template_id)
            if record.status == "archived":
                raise RuntimeError("Archived strategy templates cannot be edited.")
            values = change.model_dump(exclude_none=True)
            next_configuration = values.get(
                "configuration", json.loads(record.configuration_json)
            )
            next_defaults = values.get(
                "setup_defaults",
                StrategySetupDefaults.model_validate_json(record.setup_defaults_json),
            )
            candidate = StrategyTemplateCreate(
                type_id=record.type_id,
                name=values.get("name", record.name),
                description=values.get("description", record.description),
                timeframe_minutes=values.get(
                    "timeframe_minutes", record.timeframe_minutes
                ),
                direction=values.get("direction", record.direction),
                configuration=next_configuration,
                setup_defaults=next_defaults,
                status=values.get("status", record.status),
            )
            self._validate_template(candidate)
            record.name = candidate.name
            record.description = candidate.description
            record.timeframe_minutes = candidate.timeframe_minutes
            record.direction = candidate.direction
            record.configuration_json = self._json(candidate.configuration)
            record.setup_defaults_json = candidate.setup_defaults.model_dump_json()
            record.status = candidate.status
            record.current_revision += 1
            record.updated_at = datetime.now(UTC)
            session.add(self._template_version_record(record, record.updated_at))
            session.commit()
            session.refresh(record)
            return self._template_to_domain(session, record)

    def template_versions(self, template_id: str) -> list[StrategyTemplateVersion]:
        with Session(self._database_engine) as session:
            self._template(session, template_id)
            records = session.scalars(
                select(StrategyTemplateVersionRecord)
                .where(StrategyTemplateVersionRecord.template_id == template_id)
                .order_by(StrategyTemplateVersionRecord.revision)
            )
            return [self._template_version_to_domain(record) for record in records]

    def archive_template(self, template_id: str) -> StrategyTemplate:
        with self._lock, Session(self._database_engine) as session:
            record = self._template(session, template_id)
            if record.status == "archived":
                return self._template_to_domain(session, record)
            record.status = "archived"
            record.archived_at = datetime.now(UTC)
            record.updated_at = record.archived_at
            session.commit()
            session.refresh(record)
            return self._template_to_domain(session, record)

    def delete_template(self, template_id: str) -> None:
        with self._lock, Session(self._database_engine) as session:
            record = self._template(session, template_id)
            setup = session.scalar(
                select(StrategyCoinSetupRecord).where(
                    StrategyCoinSetupRecord.template_id == template_id
                )
            )
            if record.status != "draft" or setup is not None:
                raise RuntimeError(
                    "Only an unused draft strategy template can be deleted; archive used templates."
                )
            for version in session.scalars(
                select(StrategyTemplateVersionRecord).where(
                    StrategyTemplateVersionRecord.template_id == template_id
                )
            ):
                session.delete(version)
            session.delete(record)
            session.commit()

    # User Presets -------------------------------------------------------
    # The original persisted `strategy_template` records remain in place so
    # every ID, version, setup, Backtest, deployment, and ownership reference
    # stays valid. Public product language now exposes those editable records as
    # Presets while registered strategy implementations are immutable Templates.
    def list_presets(self, include_archived: bool = False) -> list[StrategyPreset]:
        return [
            self._preset_from_legacy_template(template)
            for template in self.list_templates(include_archived)
        ]

    def get_preset(self, preset_id: str) -> StrategyPreset:
        return self._preset_from_legacy_template(self.get_template(preset_id))

    def create_preset(self, change: StrategyPresetCreate) -> StrategyPreset:
        legacy = self.create_template(
            StrategyTemplateCreate.model_validate(change.model_dump())
        )
        return self._preset_from_legacy_template(legacy)

    def update_preset(
        self, preset_id: str, change: StrategyPresetUpdate
    ) -> StrategyPreset:
        legacy = self.update_template(
            preset_id,
            StrategyTemplateUpdate.model_validate(change.model_dump()),
        )
        return self._preset_from_legacy_template(legacy)

    def preset_versions(self, preset_id: str) -> list[StrategyPresetVersion]:
        return [
            StrategyPresetVersion(
                version_id=version.version_id,
                preset_id=version.template_id,
                revision=version.revision,
                timeframe_minutes=version.timeframe_minutes,
                direction=version.direction,
                configuration=version.configuration,
                setup_defaults=version.setup_defaults,
                created_at=version.created_at,
            )
            for version in self.template_versions(preset_id)
        ]

    def archive_preset(self, preset_id: str) -> StrategyPreset:
        return self._preset_from_legacy_template(self.archive_template(preset_id))

    def delete_preset(self, preset_id: str) -> None:
        self.delete_template(preset_id)

    @staticmethod
    def _preset_from_legacy_template(template: StrategyTemplate) -> StrategyPreset:
        return StrategyPreset(
            preset_id=template.template_id,
            type_id=template.type_id,
            name=template.name,
            description=template.description,
            status=template.status,
            current_revision=template.current_revision,
            timeframe_minutes=template.timeframe_minutes,
            direction=template.direction,
            configuration=template.configuration,
            setup_defaults=template.setup_defaults,
            setup_count=template.setup_count,
            created_at=template.created_at,
            updated_at=template.updated_at,
            archived_at=template.archived_at,
            legacy_template_id=template.template_id,
        )

    # Coin setups --------------------------------------------------------
    def list_setups(
        self,
        *,
        template_id: str | None = None,
        include_archived: bool = False,
    ) -> list[StrategyCoinSetup]:
        with Session(self._database_engine) as session:
            self._expire_opportunities(session)
            statement = select(StrategyCoinSetupRecord).order_by(
                StrategyCoinSetupRecord.updated_at.desc()
            )
            if template_id is not None:
                statement = statement.where(
                    StrategyCoinSetupRecord.template_id == template_id
                )
            if not include_archived:
                statement = statement.where(
                    StrategyCoinSetupRecord.status != "archived"
                )
            records = session.scalars(statement)
            return [self._setup_to_domain(session, record) for record in records]

    def get_setup(self, setup_id: str) -> StrategyCoinSetup:
        with Session(self._database_engine) as session:
            return self._setup_to_domain(session, self._setup(session, setup_id))

    def create_setup(
        self,
        change: StrategyCoinSetupCreate,
        *,
        current_price: Decimal | None = None,
        price_observed_at: datetime | None = None,
        price_state: str = "unavailable",
    ) -> StrategyCoinSetup:
        now = datetime.now(UTC)
        with self._lock, Session(self._database_engine) as session:
            template = self._template(session, change.template_id)
            if template.status == "archived":
                raise RuntimeError(
                    "Cannot add a coin to an archived strategy template."
                )
            version = self._template_version(
                session, template.template_id, template.current_revision
            )
            timeframe = change.timeframe_minutes or version.timeframe_minutes
            direction = change.direction or version.direction
            effective_configuration = self._merge_configuration(
                json.loads(version.configuration_json), change.configuration_overrides
            )
            self._validate_configuration(
                template.type_id, effective_configuration, timeframe, direction
            )
            record = StrategyCoinSetupRecord(
                setup_id=str(uuid4()),
                template_id=template.template_id,
                template_revision=template.current_revision,
                runtime_instance_id=None,
                exchange=change.exchange,
                market_type=change.market_type,
                symbol=change.symbol,
                quote_currency=change.quote_currency,
                current_price=current_price,
                price_observed_at=price_observed_at,
                price_state=price_state,
                timeframe_minutes=timeframe,
                direction=direction,
                configuration_overrides_json=self._json(change.configuration_overrides),
                setup_defaults_override_json=(
                    change.setup_defaults_override.model_dump_json()
                    if change.setup_defaults_override is not None
                    else None
                ),
                status="ready_for_backtest",
                latest_backtest_id=None,
                latest_backtest_revision=None,
                latest_backtest_assessment=None,
                source_opportunity_id=change.source_opportunity_id,
                revision=1,
                created_at=now,
                updated_at=now,
                archived_at=None,
            )
            session.add(record)
            try:
                session.flush()
            except IntegrityError as error:
                session.rollback()
                raise ValueError(
                    "This strategy already has a coin setup for the selected market."
                ) from error
            session.add(self._setup_version_record(session, record, now))
            session.commit()
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def update_setup(
        self, setup_id: str, change: StrategyCoinSetupUpdate
    ) -> StrategyCoinSetup:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            if record.status == "archived":
                raise RuntimeError("Archived coin setups cannot be edited.")
            deployment = self._active_deployment_for_setup(session, setup_id)
            if deployment is not None:
                raise RuntimeError(
                    "Pause and stop the active bot deployment before editing this setup."
                )
            values = change.model_dump(exclude_none=True)
            next_overrides = values.get(
                "configuration_overrides",
                json.loads(record.configuration_overrides_json),
            )
            next_defaults = values.get("setup_defaults_override")
            if "setup_defaults_override" not in change.model_fields_set:
                next_defaults = (
                    StrategySetupDefaults.model_validate_json(
                        record.setup_defaults_override_json
                    )
                    if record.setup_defaults_override_json is not None
                    else None
                )
            template = self._template(session, record.template_id)
            version = self._template_version(
                session, record.template_id, record.template_revision
            )
            timeframe = values.get("timeframe_minutes", record.timeframe_minutes)
            direction = values.get("direction", record.direction)
            effective_configuration = self._merge_configuration(
                json.loads(version.configuration_json), next_overrides
            )
            self._validate_configuration(
                template.type_id, effective_configuration, timeframe, direction
            )
            record.symbol = values.get("symbol", record.symbol)
            record.timeframe_minutes = timeframe
            record.direction = direction
            record.configuration_overrides_json = self._json(next_overrides)
            record.setup_defaults_override_json = (
                next_defaults.model_dump_json() if next_defaults is not None else None
            )
            self._invalidate_setup_evidence(session, record)
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            session.add(self._setup_version_record(session, record, record.updated_at))
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise ValueError(
                    "This strategy already has a coin setup for the selected market."
                ) from error
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def reset_setup_defaults(self, setup_id: str) -> StrategyCoinSetup:
        return self.update_setup(
            setup_id,
            StrategyCoinSetupUpdate(
                configuration_overrides={},
                setup_defaults_override=None,
            ),
        )

    def rebase_setup(self, setup_id: str) -> StrategyCoinSetup:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            if record.status == "archived":
                raise RuntimeError("Archived coin setups cannot be rebased.")
            if self._active_deployment_for_setup(session, setup_id) is not None:
                raise RuntimeError(
                    "Stop the active deployment before rebasing the setup."
                )
            template = self._template(session, record.template_id)
            if record.template_revision == template.current_revision:
                return self._setup_to_domain(session, record)
            version = self._template_version(
                session, template.template_id, template.current_revision
            )
            effective_configuration = self._merge_configuration(
                json.loads(version.configuration_json),
                json.loads(record.configuration_overrides_json),
            )
            self._validate_configuration(
                template.type_id,
                effective_configuration,
                record.timeframe_minutes,
                record.direction,
            )
            record.template_revision = template.current_revision
            self._invalidate_setup_evidence(session, record)
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            session.add(self._setup_version_record(session, record, record.updated_at))
            session.commit()
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def update_setup_price(
        self,
        setup_id: str,
        *,
        current_price: Decimal | None,
        observed_at: datetime | None,
        price_state: str,
    ) -> StrategyCoinSetup:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            record.current_price = current_price
            record.price_observed_at = observed_at
            record.price_state = price_state
            record.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def setup_versions(self, setup_id: str) -> list[StrategyCoinSetupVersion]:
        with Session(self._database_engine) as session:
            self._setup(session, setup_id)
            records = session.scalars(
                select(StrategyCoinSetupVersionRecord)
                .where(StrategyCoinSetupVersionRecord.setup_id == setup_id)
                .order_by(StrategyCoinSetupVersionRecord.revision)
            )
            return [self._setup_version_to_domain(record) for record in records]

    def archive_setup(self, setup_id: str) -> StrategyCoinSetup:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            if self._active_deployment_for_setup(session, setup_id) is not None:
                raise RuntimeError(
                    "Running or paused bot deployments must be stopped first."
                )
            record.status = "archived"
            record.archived_at = datetime.now(UTC)
            record.updated_at = record.archived_at
            self._invalidate_approvals(session, record.setup_id, record.updated_at)
            session.commit()
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def delete_setup(self, setup_id: str) -> None:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            approval = session.scalar(
                select(StrategySetupApprovalRecord).where(
                    StrategySetupApprovalRecord.setup_id == setup_id
                )
            )
            deployment = session.scalar(
                select(BotDeploymentRecord).where(
                    BotDeploymentRecord.setup_id == setup_id
                )
            )
            if (
                record.status
                not in {"draft", "ready_for_backtest", "backtest_required"}
                or record.latest_backtest_id is not None
                or record.runtime_instance_id is not None
                or approval is not None
                or deployment is not None
            ):
                raise RuntimeError(
                    "Only an unused draft coin setup can be deleted; archive used setups."
                )
            for version in session.scalars(
                select(StrategyCoinSetupVersionRecord).where(
                    StrategyCoinSetupVersionRecord.setup_id == setup_id
                )
            ):
                session.delete(version)
            session.delete(record)
            session.commit()

    # Backtests and approvals -------------------------------------------
    def build_backtest_request(
        self, setup_id: str, request: SetupBacktestRequest
    ) -> BacktestRunRequest:
        setup = self.get_setup(setup_id)
        template = self.get_template(setup.template_id)
        return BacktestRunRequest(
            setup_id=setup.setup_id,
            setup_revision=setup.revision,
            strategy_type_id=template.type_id,
            symbol=setup.symbol,
            timeframe_minutes=setup.timeframe_minutes,
            configuration=setup.effective_configuration,
            start=request.start,
            end=request.end,
            settings=request.settings.model_copy(
                update={
                    "margin_per_trade": setup.effective_setup_defaults.risk.requested_margin,
                    "leverage": setup.effective_setup_defaults.risk.requested_leverage,
                }
            ),
        )

    def record_backtest(
        self, setup_id: str, stored: StoredBacktestRun
    ) -> StrategyCoinSetup:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            if stored.request.setup_id != setup_id:
                raise ValueError("Backtest does not belong to the selected coin setup.")
            if stored.request.setup_revision != record.revision:
                raise RuntimeError(
                    "The coin setup changed while the backtest was running; run it again."
                )
            record.latest_backtest_id = stored.backtest_id
            record.latest_backtest_revision = record.revision
            record.latest_backtest_assessment = stored.result.assessment.label
            record.status = (
                "backtest_passed"
                if stored.result.assessment.label == "promising"
                else "backtest_failed"
            )
            record.updated_at = datetime.now(UTC)
            self._invalidate_approvals(session, record.setup_id, record.updated_at)
            session.commit()
            session.refresh(record)
            return self._setup_to_domain(session, record)

    def approve_setup(
        self, setup_id: str, request: SetupApprovalRequest
    ) -> StrategySetupApproval:
        with self._lock, Session(self._database_engine) as session:
            record = self._setup(session, setup_id)
            if record.status == "archived":
                raise RuntimeError("Archived coin setups cannot be approved.")
            setup = self._setup_to_domain(session, record)
            template = self._template(session, record.template_id)
            unsupported = self._unsupported_execution_settings(
                template.type_id, setup.effective_setup_defaults
            )
            if unsupported:
                raise RuntimeError(" ".join(unsupported))
            has_current_backtest = (
                record.latest_backtest_id is not None
                and record.latest_backtest_revision == record.revision
                and record.latest_backtest_assessment is not None
            )
            if not has_current_backtest and (
                not request.skip_backtest
                or request.confirmation != "APPROVE WITHOUT BACKTEST"
            ):
                raise RuntimeError(
                    "Approval without a current backtest requires the exact confirmation phrase: "
                    "APPROVE WITHOUT BACKTEST."
                )
            non_promising = (
                has_current_backtest
                and record.latest_backtest_assessment != "promising"
            )
            if non_promising and (
                not request.accept_non_promising
                or request.confirmation != "APPROVE NON-PROMISING BACKTEST"
            ):
                raise RuntimeError(
                    "This backtest is not promising. Exceptional approval requires the exact confirmation phrase."
                )
            now = datetime.now(UTC)
            for existing in session.scalars(
                select(StrategySetupApprovalRecord).where(
                    StrategySetupApprovalRecord.setup_id == setup_id,
                    StrategySetupApprovalRecord.mode == request.mode,
                    StrategySetupApprovalRecord.status == "approved",
                )
            ):
                existing.status = "stale"
                existing.invalidated_at = now
            approval = StrategySetupApprovalRecord(
                approval_id=str(uuid4()),
                setup_id=setup_id,
                setup_revision=record.revision,
                mode=request.mode,
                status="approved",
                note=(
                    f"{request.note}\n[manual override: {record.latest_backtest_assessment}]".strip()
                    if non_promising
                    else f"{request.note}\n[manual override: no backtest]".strip()
                    if not has_current_backtest
                    else request.note
                ),
                approved_at=now,
                invalidated_at=None,
            )
            session.add(approval)
            record.status = f"approved_{request.mode}"
            record.updated_at = now
            session.commit()
            session.refresh(approval)
            return self._approval_to_domain(approval)

    def approvals(self, setup_id: str) -> list[StrategySetupApproval]:
        with Session(self._database_engine) as session:
            self._setup(session, setup_id)
            records = session.scalars(
                select(StrategySetupApprovalRecord)
                .where(StrategySetupApprovalRecord.setup_id == setup_id)
                .order_by(StrategySetupApprovalRecord.approved_at.desc())
            )
            return [self._approval_to_domain(record) for record in records]

    # Opportunities -----------------------------------------------------
    def ingest_scan(self, scan: StoredStrategyScan) -> list[StrategyOpportunity]:
        now = datetime.now(UTC)
        expires_at = scan.created_at + timedelta(hours=24)
        with self._lock, Session(self._database_engine) as session:
            for candidate in scan.result.candidates:
                existing = session.scalar(
                    select(StrategyOpportunityRecord).where(
                        StrategyOpportunityRecord.scan_id == scan.scan_id,
                        StrategyOpportunityRecord.symbol == candidate.symbol,
                    )
                )
                if existing is not None:
                    continue
                price_state = (
                    "fresh"
                    if candidate.market_data_state == "fresh"
                    else "delayed"
                    if candidate.market_data_state in {"stale", "reconnecting"}
                    else "unavailable"
                )
                session.add(
                    StrategyOpportunityRecord(
                        opportunity_id=str(uuid4()),
                        scan_id=scan.scan_id,
                        strategy_type_id=scan.request.strategy_type_id,
                        strategy_version=scan.strategy_version,
                        timeframe_minutes=scan.request.timeframe_minutes,
                        configuration_json=self._json(scan.request.configuration),
                        symbol=candidate.symbol,
                        exchange=candidate.exchange,
                        market_type=candidate.market_type,
                        quote_currency=candidate.quote_currency,
                        current_price=candidate.current_price,
                        price_observed_at=candidate.price_observed_at,
                        price_state=price_state,
                        scanner_score=candidate.score,
                        signal=candidate.signal,
                        eligible_now=candidate.eligible_now,
                        qualifying_factors_json=self._json(candidate.reason_codes),
                        explanation_ar=candidate.explanation_ar,
                        warnings_json=self._json(candidate.warnings),
                        discovered_at=scan.created_at,
                        expires_at=expires_at,
                        status="new" if expires_at > now else "expired",
                        converted_setup_id=None,
                    )
                )
            session.commit()
        return self.list_opportunities(scan_id=scan.scan_id)

    def list_opportunities(
        self,
        *,
        status: str | None = None,
        strategy_type_id: str | None = None,
        scan_id: str | None = None,
    ) -> list[StrategyOpportunity]:
        with self._lock, Session(self._database_engine) as session:
            self._expire_opportunities(session)
            statement = select(StrategyOpportunityRecord).order_by(
                StrategyOpportunityRecord.scanner_score.desc(),
                StrategyOpportunityRecord.discovered_at.desc(),
            )
            if status is not None:
                statement = statement.where(StrategyOpportunityRecord.status == status)
            if strategy_type_id is not None:
                statement = statement.where(
                    StrategyOpportunityRecord.strategy_type_id == strategy_type_id
                )
            if scan_id is not None:
                statement = statement.where(
                    StrategyOpportunityRecord.scan_id == scan_id
                )
            records = session.scalars(statement)
            return [self._opportunity_to_domain(record) for record in records]

    def get_opportunity(self, opportunity_id: str) -> StrategyOpportunity:
        with self._lock, Session(self._database_engine) as session:
            self._expire_opportunities(session)
            return self._opportunity_to_domain(
                self._opportunity(session, opportunity_id)
            )

    def update_opportunity(
        self, opportunity_id: str, change: OpportunityStatusUpdate
    ) -> StrategyOpportunity:
        with self._lock, Session(self._database_engine) as session:
            record = self._opportunity(session, opportunity_id)
            if record.status == "converted":
                raise RuntimeError("Converted opportunities keep their audit status.")
            if (
                self._utc(record.expires_at) <= datetime.now(UTC)
                and change.status != "expired"
            ):
                record.status = "expired"
                session.commit()
                raise RuntimeError("This opportunity has expired; run a fresh scan.")
            record.status = change.status
            session.commit()
            session.refresh(record)
            return self._opportunity_to_domain(record)

    def convert_opportunity(
        self, opportunity_id: str, change: OpportunityConversionRequest
    ) -> StrategyCoinSetup:
        opportunity = self.get_opportunity(opportunity_id)
        if opportunity.status in {"rejected", "ignored", "expired", "converted"}:
            raise RuntimeError("This opportunity cannot be converted to a coin setup.")
        template = self.get_template(change.template_id)
        if template.type_id != opportunity.strategy_type_id:
            raise ValueError(
                "The selected strategy template is not compatible with this opportunity."
            )
        setup = self.create_setup(
            StrategyCoinSetupCreate(
                template_id=change.template_id,
                symbol=opportunity.symbol,
                exchange=opportunity.exchange,
                market_type="usdt_perpetual",
                quote_currency=opportunity.quote_currency,
                timeframe_minutes=opportunity.timeframe_minutes,
                configuration_overrides=change.configuration_overrides,
                setup_defaults_override=change.setup_defaults_override,
                source_opportunity_id=opportunity.opportunity_id,
            ),
            current_price=opportunity.current_price,
            price_observed_at=opportunity.price_observed_at,
            price_state=opportunity.price_state,
        )
        with self._lock, Session(self._database_engine) as session:
            record = self._opportunity(session, opportunity_id)
            record.status = "converted"
            record.converted_setup_id = setup.setup_id
            session.commit()
        return setup

    # Deployments -------------------------------------------------------
    def list_deployments(self) -> list[BotDeployment]:
        with Session(self._database_engine) as session:
            records = session.scalars(
                select(BotDeploymentRecord).order_by(
                    BotDeploymentRecord.created_at.desc()
                )
            )
            return [self._deployment_to_domain(record) for record in records]

    def get_deployment(self, deployment_id: str) -> BotDeployment:
        with Session(self._database_engine) as session:
            return self._deployment_to_domain(self._deployment(session, deployment_id))

    def create_deployment(
        self, setup_id: str, request: BotDeploymentCreate
    ) -> BotDeployment:
        with Session(self._database_engine) as session:
            setup_record = self._setup(session, setup_id)
            setup = self._setup_to_domain(session, setup_record)
            template = self._template(session, setup.template_id)
            approval = self._active_approval(
                session, setup.setup_id, setup.revision, request.environment
            )
            if approval is None:
                raise RuntimeError(
                    f"The current setup revision is not approved for {request.environment}."
                )
            if self._active_deployment_for_setup(session, setup_id) is not None:
                raise RuntimeError("This setup already has an active deployment.")
            metadata = self._registry.get(template.type_id)

        configuration = dict(setup.effective_configuration)
        runtime = self._strategy_instances.create(
            StrategyInstanceCreate(
                type_id=template.type_id,
                name=f"{template.name} · {setup.symbol}"[:200],
                environment=request.environment,
                symbol=setup.symbol,
                timeframe_minutes=setup.timeframe_minutes,
                direction=setup.direction,
                requested_margin=setup.effective_setup_defaults.risk.requested_margin,
                requested_leverage=setup.effective_setup_defaults.risk.requested_leverage,
                configuration=configuration,
            )
        )
        now = datetime.now(UTC)
        snapshot = self._deployment_snapshot(setup, template.type_id, metadata.version)
        record = BotDeploymentRecord(
            deployment_id=str(uuid4()),
            setup_id=setup.setup_id,
            setup_revision=setup.revision,
            template_id=setup.template_id,
            template_revision=setup.template_revision,
            runtime_instance_id=runtime.instance_id,
            environment=request.environment,
            strategy_type_id=template.type_id,
            strategy_version=metadata.version,
            configuration_snapshot_json=self._json(snapshot),
            status="not_started",
            created_at=now,
            updated_at=now,
            started_at=None,
            ended_at=None,
            error_message=None,
        )
        try:
            with self._lock, Session(self._database_engine) as session:
                setup_record = self._setup(session, setup_id)
                setup_record.runtime_instance_id = runtime.instance_id
                setup_record.updated_at = now
                session.add(record)
                session.commit()
                session.refresh(record)
                return self._deployment_to_domain(record)
        except Exception:
            self._strategy_instances.delete(runtime.instance_id)
            raise

    def transition_deployment(self, deployment_id: str, action: str) -> BotDeployment:
        if action not in {"start", "monitor", "pause", "stop"}:
            raise ValueError(f"Unsupported deployment action: {action}")
        with Session(self._database_engine) as session:
            record = self._deployment(session, deployment_id)
            if action in {"start", "monitor"}:
                setup = self._setup(session, record.setup_id)
                if setup.status == "archived":
                    raise RuntimeError("Archived coin setups cannot restart a bot.")
                if setup.revision != record.setup_revision:
                    raise RuntimeError(
                        "This deployment belongs to an older setup revision; create a new approved deployment."
                    )
                approval = self._active_approval(
                    session,
                    record.setup_id,
                    record.setup_revision,
                    record.environment,
                )
                if approval is None:
                    raise RuntimeError(
                        "This deployment approval is missing or stale; approve the current setup revision again."
                    )
            runtime_instance_id = record.runtime_instance_id
            deployment_snapshot = json.loads(record.configuration_snapshot_json)
        target = {
            "start": "running",
            "monitor": "monitoring",
            "pause": "paused",
            "stop": "stopped",
        }[action]
        try:
            run_extensions = None
            if target in {"running", "monitoring"}:
                run_extensions = {
                    "deployment_snapshot": deployment_snapshot,
                }
                setup_defaults = deployment_snapshot.get("setup_defaults")
                if isinstance(setup_defaults, dict):
                    execution_plan = setup_defaults.get("execution_plan")
                    if isinstance(execution_plan, dict):
                        run_extensions["execution_plan"] = execution_plan
            self._strategy_instances.transition(
                runtime_instance_id,
                target,
                configuration_snapshot_extensions=run_extensions,
            )
        except Exception as error:
            with self._lock, Session(self._database_engine) as session:
                record = self._deployment(session, deployment_id)
                record.status = "error"
                record.error_message = str(error)
                record.updated_at = datetime.now(UTC)
                session.commit()
            raise
        with self._lock, Session(self._database_engine) as session:
            record = self._deployment(session, deployment_id)
            now = datetime.now(UTC)
            record.status = target
            record.updated_at = now
            record.error_message = None
            if action in {"start", "monitor"} and record.started_at is None:
                record.started_at = now
            if action == "stop":
                record.ended_at = now
            session.commit()
            session.refresh(record)
            return self._deployment_to_domain(record)

    def ensure_instance_can_start(self, instance_id: str) -> BotDeployment:
        with Session(self._database_engine) as session:
            record = session.scalar(
                select(BotDeploymentRecord).where(
                    BotDeploymentRecord.runtime_instance_id == instance_id
                )
            )
            if record is None:
                raise RuntimeError(
                    "Start this bot from an approved coin setup so RangeBot can preserve an immutable deployment snapshot."
                )
            approval = self._active_approval(
                session,
                record.setup_id,
                record.setup_revision,
                record.environment,
            )
            if approval is None:
                raise RuntimeError(
                    "The deployment approval is missing or stale; backtest and approve the current setup again."
                )
            return self._deployment_to_domain(record)

    def deployment_for_instance(self, instance_id: str) -> BotDeployment | None:
        with Session(self._database_engine) as session:
            record = session.scalar(
                select(BotDeploymentRecord).where(
                    BotDeploymentRecord.runtime_instance_id == instance_id
                )
            )
            return self._deployment_to_domain(record) if record is not None else None

    def execution_plan_for_instance(
        self, instance_id: str
    ) -> StrategyExecutionPlan | None:
        deployment = self.deployment_for_instance(instance_id)
        if deployment is None:
            return None
        setup_defaults = deployment.configuration_snapshot.get("setup_defaults")
        if not isinstance(setup_defaults, dict):
            return None
        defaults = StrategySetupDefaults.model_validate(setup_defaults)
        return defaults.execution_plan

    def summary(self) -> WorkflowSummary:
        with Session(self._database_engine) as session:
            return WorkflowSummary(
                templates=session.scalar(
                    select(func.count())
                    .select_from(StrategyTemplateRecord)
                    .where(StrategyTemplateRecord.status != "archived")
                )
                or 0,
                setups=session.scalar(
                    select(func.count())
                    .select_from(StrategyCoinSetupRecord)
                    .where(StrategyCoinSetupRecord.status != "archived")
                )
                or 0,
                opportunities_new=session.scalar(
                    select(func.count())
                    .select_from(StrategyOpportunityRecord)
                    .where(
                        StrategyOpportunityRecord.status.in_(
                            ("new", "reviewed", "approved")
                        )
                    )
                )
                or 0,
                backtests_required=session.scalar(
                    select(func.count())
                    .select_from(StrategyCoinSetupRecord)
                    .where(
                        StrategyCoinSetupRecord.status.in_(
                            (
                                "ready_for_backtest",
                                "backtest_required",
                                "backtest_failed",
                            )
                        )
                    )
                )
                or 0,
                approvals_ready=session.scalar(
                    select(func.count())
                    .select_from(StrategyCoinSetupRecord)
                    .where(StrategyCoinSetupRecord.status == "backtest_passed")
                )
                or 0,
                deployments_running=session.scalar(
                    select(func.count())
                    .select_from(BotDeploymentRecord)
                    .where(BotDeploymentRecord.status.in_(("running", "monitoring")))
                )
                or 0,
            )

    # Helpers -----------------------------------------------------------
    def _validate_template(self, change: StrategyTemplateCreate) -> None:
        metadata = self._registry.get(change.type_id)
        if change.timeframe_minutes not in metadata.supported_timeframes:
            raise ValueError(
                "The selected timeframe is not supported by this strategy."
            )
        if change.direction == "long" and not metadata.supports_long:
            raise ValueError("This strategy type does not support Long entries.")
        if change.direction == "short" and not metadata.supports_short:
            raise ValueError("This strategy type does not support Short entries.")
        self._validate_configuration(
            change.type_id,
            change.configuration,
            change.timeframe_minutes,
            change.direction,
        )

    def _validate_configuration(
        self,
        type_id: str,
        configuration: dict[str, Any],
        timeframe_minutes: int,
        direction: str,
    ) -> None:
        metadata = self._registry.get(type_id)
        effective = dict(configuration)
        properties = metadata.configuration_schema.get("properties", {})
        if "timeframe_minutes" in properties:
            effective["timeframe_minutes"] = timeframe_minutes
        if "direction" in properties:
            effective["direction"] = {
                "long": "long_only",
                "short": "short_only",
                "both": "both",
            }[direction]
        self._registry.validate_configuration(type_id, effective)

    @staticmethod
    def _merge_configuration(
        inherited: dict[str, Any], overrides: dict[str, Any]
    ) -> dict[str, Any]:
        return {**inherited, **overrides}

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            to_jsonable_python(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def _template_version_record(
        self, record: StrategyTemplateRecord, created_at: datetime
    ) -> StrategyTemplateVersionRecord:
        return StrategyTemplateVersionRecord(
            template_id=record.template_id,
            revision=record.current_revision,
            timeframe_minutes=record.timeframe_minutes,
            direction=record.direction,
            configuration_json=record.configuration_json,
            setup_defaults_json=record.setup_defaults_json,
            created_at=created_at,
        )

    def _setup_version_record(
        self,
        session: Session,
        record: StrategyCoinSetupRecord,
        created_at: datetime,
    ) -> StrategyCoinSetupVersionRecord:
        setup = self._setup_to_domain(session, record)
        snapshot = setup.model_dump(
            mode="json",
            exclude={
                "current_price",
                "price_observed_at",
                "price_state",
                "warnings",
                "created_at",
                "updated_at",
                "archived_at",
            },
        )
        return StrategyCoinSetupVersionRecord(
            setup_id=record.setup_id,
            revision=record.revision,
            snapshot_json=self._json(snapshot),
            created_at=created_at,
        )

    def _invalidate_setup_evidence(
        self, session: Session, record: StrategyCoinSetupRecord
    ) -> None:
        now = datetime.now(UTC)
        self._invalidate_approvals(session, record.setup_id, now)
        record.status = "backtest_required"
        record.latest_backtest_id = None
        record.latest_backtest_revision = None
        record.latest_backtest_assessment = None
        record.runtime_instance_id = None

    @staticmethod
    def _invalidate_approvals(
        session: Session, setup_id: str, invalidated_at: datetime
    ) -> None:
        for approval in session.scalars(
            select(StrategySetupApprovalRecord).where(
                StrategySetupApprovalRecord.setup_id == setup_id,
                StrategySetupApprovalRecord.status == "approved",
            )
        ):
            approval.status = "stale"
            approval.invalidated_at = invalidated_at

    def _active_approval(
        self,
        session: Session,
        setup_id: str,
        setup_revision: int,
        mode: str,
    ) -> StrategySetupApprovalRecord | None:
        return session.scalar(
            select(StrategySetupApprovalRecord)
            .where(
                StrategySetupApprovalRecord.setup_id == setup_id,
                StrategySetupApprovalRecord.setup_revision == setup_revision,
                StrategySetupApprovalRecord.mode == mode,
                StrategySetupApprovalRecord.status == "approved",
            )
            .order_by(StrategySetupApprovalRecord.approved_at.desc())
        )

    def _active_deployment_for_setup(
        self, session: Session, setup_id: str
    ) -> BotDeploymentRecord | None:
        return session.scalar(
            select(BotDeploymentRecord).where(
                BotDeploymentRecord.setup_id == setup_id,
                BotDeploymentRecord.status.in_(
                    ("starting", "running", "monitoring", "paused")
                ),
            )
        )

    @staticmethod
    def _unsupported_execution_settings(
        type_id: str,
        defaults: StrategySetupDefaults,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        if defaults.dca.enabled and type_id != "fixed_price_ladder":
            issues.append(
                "DCA متعدد الدخول مدعوم حالياً فقط لاستراتيجية سلم الأسعار الثابت."
            )
        plan = defaults.execution_plan
        if plan.take_profit.order_type == "limit" and type_id != "fixed_price_ladder":
            issues.append(
                "جني الربح Limit غير مدعوم لهذا النوع؛ استخدم Market للحماية المضمونة."
            )
        for label, settings in (
            ("وقف الخسارة", plan.stop_loss),
            ("خروج الاستراتيجية", plan.strategy_exit),
            ("الخروج اليدوي", plan.manual_exit),
        ):
            if settings.order_type == "limit":
                issues.append(
                    f"{label} Limit غير مدعوم في مسار الحماية الحالي؛ استخدم Market."
                )
        return tuple(issues)

    @staticmethod
    def _deployment_snapshot(
        setup: StrategyCoinSetup, type_id: str, strategy_version: str
    ) -> dict[str, Any]:
        return {
            "setup_id": setup.setup_id,
            "setup_revision": setup.revision,
            "template_id": setup.template_id,
            "template_revision": setup.template_revision,
            "strategy_type_id": type_id,
            "strategy_version": strategy_version,
            "exchange": setup.exchange,
            "market_type": setup.market_type,
            "symbol": setup.symbol,
            "quote_currency": setup.quote_currency,
            "timeframe_minutes": setup.timeframe_minutes,
            "direction": setup.direction,
            "configuration": setup.effective_configuration,
            "setup_defaults": setup.effective_setup_defaults.model_dump(mode="json"),
            "approved_backtest_id": setup.latest_backtest_id,
        }

    def _expire_opportunities(self, session: Session) -> None:
        now = datetime.now(UTC)
        changed = False
        for record in session.scalars(
            select(StrategyOpportunityRecord).where(
                StrategyOpportunityRecord.expires_at <= now,
                StrategyOpportunityRecord.status.in_(("new", "reviewed", "approved")),
            )
        ):
            record.status = "expired"
            changed = True
        if changed:
            session.commit()

    @staticmethod
    def _template(session: Session, template_id: str) -> StrategyTemplateRecord:
        record = session.get(StrategyTemplateRecord, template_id)
        if record is None:
            raise LookupError(f"Unknown strategy template: {template_id}")
        return record

    @staticmethod
    def _template_version(
        session: Session, template_id: str, revision: int
    ) -> StrategyTemplateVersionRecord:
        record = session.scalar(
            select(StrategyTemplateVersionRecord).where(
                StrategyTemplateVersionRecord.template_id == template_id,
                StrategyTemplateVersionRecord.revision == revision,
            )
        )
        if record is None:
            raise LookupError(
                f"Unknown strategy template version: {template_id} revision {revision}"
            )
        return record

    @staticmethod
    def _setup(session: Session, setup_id: str) -> StrategyCoinSetupRecord:
        record = session.get(StrategyCoinSetupRecord, setup_id)
        if record is None:
            raise LookupError(f"Unknown strategy coin setup: {setup_id}")
        return record

    @staticmethod
    def _opportunity(
        session: Session, opportunity_id: str
    ) -> StrategyOpportunityRecord:
        record = session.get(StrategyOpportunityRecord, opportunity_id)
        if record is None:
            raise LookupError(f"Unknown strategy opportunity: {opportunity_id}")
        return record

    @staticmethod
    def _deployment(session: Session, deployment_id: str) -> BotDeploymentRecord:
        record = session.get(BotDeploymentRecord, deployment_id)
        if record is None:
            raise LookupError(f"Unknown bot deployment: {deployment_id}")
        return record

    def _template_to_domain(
        self, session: Session, record: StrategyTemplateRecord
    ) -> StrategyTemplate:
        setup_count = session.scalar(
            select(func.count())
            .select_from(StrategyCoinSetupRecord)
            .where(
                StrategyCoinSetupRecord.template_id == record.template_id,
                StrategyCoinSetupRecord.status != "archived",
            )
        )
        return StrategyTemplate(
            template_id=record.template_id,
            type_id=record.type_id,
            name=record.name,
            description=record.description,
            status=record.status,
            current_revision=record.current_revision,
            timeframe_minutes=record.timeframe_minutes,
            direction=record.direction,
            configuration=json.loads(record.configuration_json),
            setup_defaults=StrategySetupDefaults.model_validate_json(
                record.setup_defaults_json
            ),
            setup_count=setup_count or 0,
            created_at=self._utc(record.created_at),
            updated_at=self._utc(record.updated_at),
            archived_at=self._utc_optional(record.archived_at),
        )

    @classmethod
    def _template_version_to_domain(
        cls, record: StrategyTemplateVersionRecord
    ) -> StrategyTemplateVersion:
        return StrategyTemplateVersion(
            version_id=record.version_id,
            template_id=record.template_id,
            revision=record.revision,
            timeframe_minutes=record.timeframe_minutes,
            direction=record.direction,
            configuration=json.loads(record.configuration_json),
            setup_defaults=StrategySetupDefaults.model_validate_json(
                record.setup_defaults_json
            ),
            created_at=cls._utc(record.created_at),
        )

    def _setup_to_domain(
        self, session: Session, record: StrategyCoinSetupRecord
    ) -> StrategyCoinSetup:
        template = self._template(session, record.template_id)
        version = self._template_version(
            session, record.template_id, record.template_revision
        )
        inherited_configuration = json.loads(version.configuration_json)
        overrides = json.loads(record.configuration_overrides_json)
        inherited_defaults = StrategySetupDefaults.model_validate_json(
            version.setup_defaults_json
        )
        override_defaults = (
            StrategySetupDefaults.model_validate_json(
                record.setup_defaults_override_json
            )
            if record.setup_defaults_override_json is not None
            else None
        )
        effective_defaults = override_defaults or inherited_defaults
        approval = session.scalar(
            select(StrategySetupApprovalRecord)
            .where(
                StrategySetupApprovalRecord.setup_id == record.setup_id,
                StrategySetupApprovalRecord.setup_revision == record.revision,
                StrategySetupApprovalRecord.status == "approved",
            )
            .order_by(StrategySetupApprovalRecord.approved_at.desc())
        )
        warnings: list[str] = []
        plan = effective_defaults.execution_plan
        for label, exit_settings in (
            ("جني الربح", plan.take_profit),
            ("وقف الخسارة", plan.stop_loss),
            ("خروج الاستراتيجية", plan.strategy_exit),
            ("الخروج اليدوي", plan.manual_exit),
        ):
            if (
                exit_settings.order_type == "limit"
                and not exit_settings.fallback_to_market
            ):
                warnings.append(
                    f"{label} يستخدم Limit دون fallback إلى Market؛ قد لا يكتمل الخروج."
                )
        if record.price_state != "fresh":
            warnings.append(
                "السعر الحالي متأخر أو غير متاح؛ حدّث السعر قبل اتخاذ قرار الاعتماد."
            )
        warnings.extend(
            self._unsupported_execution_settings(template.type_id, effective_defaults)
        )
        return StrategyCoinSetup(
            setup_id=record.setup_id,
            template_id=record.template_id,
            template_revision=record.template_revision,
            runtime_instance_id=record.runtime_instance_id,
            exchange=record.exchange,
            market_type=record.market_type,
            symbol=record.symbol,
            quote_currency=record.quote_currency,
            current_price=record.current_price,
            price_observed_at=self._utc_optional(record.price_observed_at),
            price_state=record.price_state,
            timeframe_minutes=record.timeframe_minutes,
            direction=record.direction,
            inherited_configuration=inherited_configuration,
            configuration_overrides=overrides,
            effective_configuration=self._merge_configuration(
                inherited_configuration, overrides
            ),
            inherited_setup_defaults=inherited_defaults,
            setup_defaults_override=override_defaults,
            effective_setup_defaults=effective_defaults,
            status=record.status,
            latest_backtest_id=record.latest_backtest_id,
            latest_backtest_revision=record.latest_backtest_revision,
            latest_backtest_assessment=record.latest_backtest_assessment,
            active_approval_mode=approval.mode if approval is not None else None,
            source_opportunity_id=record.source_opportunity_id,
            revision=record.revision,
            warnings=tuple(warnings),
            created_at=self._utc(record.created_at),
            updated_at=self._utc(record.updated_at),
            archived_at=self._utc_optional(record.archived_at),
        )

    @classmethod
    def _setup_version_to_domain(
        cls, record: StrategyCoinSetupVersionRecord
    ) -> StrategyCoinSetupVersion:
        return StrategyCoinSetupVersion(
            version_id=record.version_id,
            setup_id=record.setup_id,
            revision=record.revision,
            snapshot=json.loads(record.snapshot_json),
            created_at=cls._utc(record.created_at),
        )

    @classmethod
    def _approval_to_domain(
        cls, record: StrategySetupApprovalRecord
    ) -> StrategySetupApproval:
        return StrategySetupApproval(
            approval_id=record.approval_id,
            setup_id=record.setup_id,
            setup_revision=record.setup_revision,
            mode=record.mode,
            status=record.status,
            note=record.note,
            approved_at=cls._utc(record.approved_at),
            invalidated_at=cls._utc_optional(record.invalidated_at),
        )

    @classmethod
    def _opportunity_to_domain(
        cls, record: StrategyOpportunityRecord
    ) -> StrategyOpportunity:
        return StrategyOpportunity(
            opportunity_id=record.opportunity_id,
            scan_id=record.scan_id,
            strategy_type_id=record.strategy_type_id,
            strategy_version=record.strategy_version,
            timeframe_minutes=record.timeframe_minutes,
            configuration=json.loads(record.configuration_json),
            symbol=record.symbol,
            exchange=record.exchange,
            market_type=record.market_type,
            quote_currency=record.quote_currency,
            current_price=record.current_price,
            price_observed_at=cls._utc_optional(record.price_observed_at),
            price_state=record.price_state,
            scanner_score=record.scanner_score,
            signal=record.signal,
            eligible_now=record.eligible_now,
            qualifying_factors=tuple(json.loads(record.qualifying_factors_json)),
            explanation_ar=record.explanation_ar,
            warnings=tuple(json.loads(record.warnings_json)),
            discovered_at=cls._utc(record.discovered_at),
            expires_at=cls._utc(record.expires_at),
            status=record.status,
            converted_setup_id=record.converted_setup_id,
        )

    @classmethod
    def _deployment_to_domain(cls, record: BotDeploymentRecord) -> BotDeployment:
        return BotDeployment(
            deployment_id=record.deployment_id,
            setup_id=record.setup_id,
            setup_revision=record.setup_revision,
            template_id=record.template_id,
            template_revision=record.template_revision,
            runtime_instance_id=record.runtime_instance_id,
            environment=record.environment,
            strategy_type_id=record.strategy_type_id,
            strategy_version=record.strategy_version,
            configuration_snapshot=json.loads(record.configuration_snapshot_json),
            status=record.status,
            created_at=cls._utc(record.created_at),
            updated_at=cls._utc(record.updated_at),
            started_at=cls._utc_optional(record.started_at),
            ended_at=cls._utc_optional(record.ended_at),
            error_message=record.error_message,
        )

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )

    @classmethod
    def _utc_optional(cls, value: datetime | None) -> datetime | None:
        return cls._utc(value) if value is not None else None
