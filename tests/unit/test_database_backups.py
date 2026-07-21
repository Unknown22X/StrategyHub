import sqlite3
from pathlib import Path

from rangebot.engine.database import apply_migrations, backup_sqlite_database


def _write_database(path: Path, value: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS marker (value TEXT NOT NULL)")
        connection.execute("DELETE FROM marker")
        connection.execute("INSERT INTO marker(value) VALUES (?)", (value,))
        connection.commit()


def test_pre_migration_backup_is_valid_and_preserves_source_database(
    tmp_path: Path,
) -> None:
    database = tmp_path / "rangebot.db"
    backup_directory = tmp_path / "backup"
    _write_database(database, "before-migration")

    backup = backup_sqlite_database(
        f"sqlite:///{database}", backup_directory=backup_directory
    )

    assert backup is not None
    assert backup.parent == backup_directory
    assert backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == (
            "before-migration",
        )


def test_pre_migration_backup_keeps_only_the_newest_ten(tmp_path: Path) -> None:
    database = tmp_path / "rangebot.db"
    backup_directory = tmp_path / "backup"
    _write_database(database, "value")

    for _ in range(12):
        backup_sqlite_database(
            f"sqlite:///{database}", backup_directory=backup_directory
        )

    backups = sorted(backup_directory.glob("rangebot-pre-migration-*.db"))
    assert len(backups) == 10


def test_backup_skips_memory_and_non_sqlite_databases(tmp_path: Path) -> None:
    assert backup_sqlite_database(
        "sqlite:///:memory:", backup_directory=tmp_path
    ) is None
    assert backup_sqlite_database(
        "postgresql://user:password@localhost/rangebot", backup_directory=tmp_path
    ) is None


def test_apply_migrations_creates_backup_before_upgrade(
    tmp_path: Path, monkeypatch
) -> None:
    database = tmp_path / "rangebot.db"
    _write_database(database, "before-upgrade")
    observed: dict[str, object] = {}

    def verify_backup_exists(*args, **kwargs) -> None:
        backups = list((tmp_path / "backup").glob("rangebot-pre-migration-*.db"))
        observed["backup_count"] = len(backups)

    monkeypatch.setattr("rangebot.engine.database.command.upgrade", verify_backup_exists)

    apply_migrations(f"sqlite:///{database}")

    assert observed["backup_count"] == 1
