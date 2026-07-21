"""Database, backup, and migration helpers for restart-critical runtime state."""

from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from rangebot.engine.paths import application_paths, default_database_url


BACKUP_RETENTION = 10


def prune_sqlite_backups(
    backup_directory: Path,
    retention: int = BACKUP_RETENTION,
) -> None:
    """Keep the newest RangeBot SQLite backups regardless of backup kind."""
    if retention < 0:
        return
    backups = sorted(
        backup_directory.glob("rangebot-*.db"),
        key=lambda path: (path.stat().st_mtime_ns, path.name),
        reverse=True,
    )
    for expired in backups[retention:]:
        expired.unlink(missing_ok=True)


def create_database_engine(database_url: str) -> Engine:
    """Create the engine used by the local lifecycle-state repository."""
    url = make_url(database_url)
    if url.drivername == "sqlite" and url.database not in (None, ":memory:"):
        Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url)


def default_backup_directory(database_url: str) -> Path:
    url = make_url(database_url)
    database = Path(url.database or "").expanduser().resolve()
    default_database = Path(make_url(default_database_url()).database or "").resolve()
    if database == default_database:
        return application_paths().backup
    return database.parent / "backup"


def backup_sqlite_database(
    database_url: str,
    *,
    backup_directory: Path | None = None,
    retention: int = BACKUP_RETENTION,
) -> Path | None:
    """Create a consistent SQLite backup before migration and apply retention."""
    url = make_url(database_url)
    if url.drivername != "sqlite" or url.database in (None, ":memory:"):
        return None

    source = Path(url.database).expanduser().resolve()
    if not source.is_file():
        return None

    destination_directory = (
        backup_directory.expanduser().resolve()
        if backup_directory is not None
        else default_backup_directory(database_url)
    )
    destination_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_directory / f"rangebot-pre-migration-{timestamp}.db"

    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()

    prune_sqlite_backups(destination_directory, retention)
    return destination


def apply_migrations(database_url: str) -> None:
    """Back up SQLite and upgrade through RangeBot's Alembic migration path."""
    backup_sqlite_database(database_url)
    frozen_root = getattr(sys, "_MEIPASS", None)
    repository_root = (
        Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[3]
    )
    configuration = Config(str(repository_root / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)
    if frozen_root:
        configuration.set_main_option(
            "script_location",
            str(repository_root / "rangebot" / "engine" / "migrations"),
        )
    command.upgrade(configuration, "head")
