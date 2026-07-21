"""Safe user-facing SQLite backup creation, validation, rotation, and restore."""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from sqlalchemy.engine import Engine, make_url

from rangebot.domain.backups import BackupKind, BackupRecord
from rangebot.engine.database import (
    BACKUP_RETENTION,
    apply_migrations,
    default_backup_directory,
    prune_sqlite_backups,
)


class SQLiteBackupError(RuntimeError):
    """Raised when a backup cannot be safely created, validated, or restored."""


class SQLiteBackupManager:
    """Own all mutable backup operations for one local SQLite database."""

    def __init__(
        self,
        database_url: str,
        database_engine: Engine,
        *,
        backup_directory: Path | None = None,
        retention: int = BACKUP_RETENTION,
    ) -> None:
        url = make_url(database_url)
        if url.drivername != "sqlite" or url.database in (None, ":memory:"):
            raise ValueError("User-facing backup operations require a file SQLite database.")
        if retention < 1:
            raise ValueError("Backup retention must keep at least one backup.")
        self._database_url = database_url
        self._database_engine = database_engine
        self._database_path = Path(url.database).expanduser().resolve()
        self._backup_directory = (
            backup_directory.expanduser().resolve()
            if backup_directory is not None
            else default_backup_directory(database_url)
        )
        self._backup_directory.mkdir(parents=True, exist_ok=True)
        self._retention = retention
        self._lock = RLock()

    def list(self) -> list[BackupRecord]:
        with self._lock:
            records = [
                self._record(path)
                for path in self._backup_directory.glob("rangebot-*.db")
                if path.is_file()
            ]
        return sorted(records, key=lambda item: (item.created_at, item.name), reverse=True)

    def create(self, kind: BackupKind = "manual") -> BackupRecord:
        with self._lock:
            if not self._database_path.is_file():
                raise SQLiteBackupError("RangeBot database does not exist yet.")
            destination = self._new_path(kind)
            self._copy_database(self._database_path, destination)
            self._validate_path(destination)
            prune_sqlite_backups(self._backup_directory, self._retention)
            return self._record(destination)

    def delete(self, name: str) -> bool:
        path = self._resolve_name(name)
        with self._lock:
            if not path.exists():
                return False
            path.unlink()
            return True

    def validate(self, name: str) -> BackupRecord:
        path = self._resolve_name(name)
        with self._lock:
            self._validate_path(path)
            return self._record(path)

    def restore(self, name: str) -> tuple[BackupRecord, BackupRecord]:
        selected = self._resolve_name(name)
        with self._lock:
            self._validate_path(selected)
            safety_backup = self.create("pre_restore")
            temporary = self._database_path.with_name(
                f".{self._database_path.name}.{uuid4().hex}.restore.tmp"
            )
            try:
                self._copy_database(selected, temporary)
                self._validate_path(temporary)
                self._database_engine.dispose(close=True)
                if os.name == "nt":
                    self._copy_database(temporary, self._database_path)
                else:
                    os.replace(temporary, self._database_path)
                apply_migrations(self._database_url)
                self._database_engine.dispose(close=True)
            except Exception as error:
                temporary.unlink(missing_ok=True)
                raise SQLiteBackupError("RangeBot backup restore failed safely.") from error
            return self._record(selected), safety_backup

    def _new_path(self, kind: BackupKind) -> Path:
        slug = kind.replace("_", "-")
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return self._backup_directory / f"rangebot-{slug}-{timestamp}.db"

    def _resolve_name(self, name: str) -> Path:
        if not name or Path(name).name != name:
            raise ValueError("Backup name must not contain a path.")
        if not name.startswith("rangebot-") or not name.endswith(".db"):
            raise ValueError("Backup name is not a RangeBot SQLite backup.")
        path = (self._backup_directory / name).resolve()
        if path.parent != self._backup_directory:
            raise ValueError("Backup path escaped the RangeBot backup directory.")
        return path

    @staticmethod
    def _copy_database(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_connection = sqlite3.connect(source)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()

    @staticmethod
    def _validate_path(path: Path) -> None:
        if not path.is_file():
            raise LookupError(f"Backup does not exist: {path.name}")
        connection = None
        try:
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            migration_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
            ).fetchone()
        except sqlite3.DatabaseError as error:
            raise SQLiteBackupError("Selected file is not a valid SQLite database.") from error
        finally:
            if connection is not None:
                connection.close()
        if integrity is None or integrity[0] != "ok":
            raise SQLiteBackupError("Selected SQLite backup failed integrity validation.")
        if migration_table is None:
            raise SQLiteBackupError("Selected database is not a RangeBot backup.")

    @staticmethod
    def _kind(path: Path) -> BackupKind:
        name = path.name
        if name.startswith("rangebot-pre-migration-"):
            return "pre_migration"
        if name.startswith("rangebot-pre-restore-"):
            return "pre_restore"
        if name.startswith("rangebot-lifecycle-"):
            return "lifecycle"
        return "manual"

    def _record(self, path: Path) -> BackupRecord:
        stat = path.stat()
        return BackupRecord(
            name=path.name,
            kind=self._kind(path),
            created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            size_bytes=stat.st_size,
        )
