"""Transactional persistence for backend-owned application settings."""

from datetime import UTC, datetime
import json

from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from rangebot.domain.application import ApplicationSettings, ApplicationSettingsUpdate


class ApplicationSettingsBase(DeclarativeBase):
    pass


class ApplicationSettingsRecord(ApplicationSettingsBase):
    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    ui_language: Mapped[str] = mapped_column(String(8), nullable=False)
    dashboard_layout_json: Mapped[str] = mapped_column(Text, nullable=False)
    dashboard_filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    sidebar_preferences_json: Mapped[str] = mapped_column(Text, nullable=False)
    application_preferences_json: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApplicationSettingsRepository:
    """Store one committed application-settings document for the local user."""

    def __init__(self, database_engine: Engine) -> None:
        self._database_engine = database_engine

    def get(self) -> ApplicationSettings:
        with Session(self._database_engine) as session:
            record = session.scalar(
                select(ApplicationSettingsRecord).where(ApplicationSettingsRecord.id == 1)
            )
            if record is None:
                return ApplicationSettings(revision=0)
            return self._to_domain(record)

    def save(self, settings: ApplicationSettingsUpdate) -> ApplicationSettings:
        now = datetime.now(UTC)
        with Session(self._database_engine) as session:
            record = session.get(ApplicationSettingsRecord, 1)
            serialized = self._serialize(settings)
            if record is None:
                record = ApplicationSettingsRecord(
                    id=1,
                    environment=settings.environment,
                    ui_language=settings.ui_language,
                    revision=1,
                    updated_at=now,
                    **serialized,
                )
                session.add(record)
            else:
                record.environment = settings.environment
                record.ui_language = settings.ui_language
                record.dashboard_layout_json = serialized["dashboard_layout_json"]
                record.dashboard_filters_json = serialized["dashboard_filters_json"]
                record.sidebar_preferences_json = serialized[
                    "sidebar_preferences_json"
                ]
                record.application_preferences_json = serialized[
                    "application_preferences_json"
                ]
                record.revision += 1
                record.updated_at = now
            session.commit()
            session.refresh(record)
            return self._to_domain(record)

    @staticmethod
    def _serialize(settings: ApplicationSettingsUpdate) -> dict[str, str]:
        compact = {"sort_keys": True, "separators": (",", ":"), "ensure_ascii": False}
        return {
            "dashboard_layout_json": json.dumps(settings.dashboard_layout, **compact),
            "dashboard_filters_json": json.dumps(settings.dashboard_filters, **compact),
            "sidebar_preferences_json": json.dumps(
                settings.sidebar_preferences, **compact
            ),
            "application_preferences_json": json.dumps(
                settings.application_preferences, **compact
            ),
        }

    @staticmethod
    def _to_domain(record: ApplicationSettingsRecord) -> ApplicationSettings:
        updated_at = record.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return ApplicationSettings(
            environment=record.environment,
            ui_language=record.ui_language,
            dashboard_layout=json.loads(record.dashboard_layout_json),
            dashboard_filters=json.loads(record.dashboard_filters_json),
            sidebar_preferences=json.loads(record.sidebar_preferences_json),
            application_preferences=json.loads(record.application_preferences_json),
            revision=record.revision,
            updated_at=updated_at,
        )
