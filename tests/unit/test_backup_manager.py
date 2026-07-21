import sqlite3

import pytest

from rangebot.engine.backups import SQLiteBackupError, SQLiteBackupManager
from rangebot.engine.database import apply_migrations, create_database_engine


def _database(tmp_path):
    path = tmp_path / "rangebot.db"
    database_url = f"sqlite:///{path}"
    apply_migrations(database_url)
    return path, database_url, create_database_engine(database_url)


def test_backup_manager_rotates_all_backup_kinds_together(tmp_path) -> None:
    _, database_url, engine = _database(tmp_path)
    manager = SQLiteBackupManager(
        database_url,
        engine,
        backup_directory=tmp_path / "backup",
        retention=3,
    )

    manager.create("manual")
    manager.create("lifecycle")
    manager.create("manual")
    manager.create("pre_restore")

    backups = manager.list()

    assert len(backups) == 3
    assert {item.kind for item in backups} <= {"manual", "lifecycle", "pre_restore"}


def test_backup_manager_rejects_traversal_and_non_rangebot_databases(tmp_path) -> None:
    _, database_url, engine = _database(tmp_path)
    backup_directory = tmp_path / "backup"
    manager = SQLiteBackupManager(
        database_url,
        engine,
        backup_directory=backup_directory,
    )
    invalid = backup_directory / "rangebot-manual-invalid.db"
    invalid.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(ValueError):
        manager.delete("../rangebot.db")
    with pytest.raises(SQLiteBackupError):
        manager.validate(invalid.name)


def test_restore_creates_safety_backup_and_replaces_database_contents(tmp_path) -> None:
    database_path, database_url, engine = _database(tmp_path)
    manager = SQLiteBackupManager(
        database_url,
        engine,
        backup_directory=tmp_path / "backup",
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE restore_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO restore_marker VALUES ('before')")
        connection.commit()
    selected = manager.create("manual")
    with sqlite3.connect(database_path) as connection:
        connection.execute("UPDATE restore_marker SET value = 'after'")
        connection.commit()

    restored, safety_backup = manager.restore(selected.name)

    with sqlite3.connect(database_path) as connection:
        value = connection.execute("SELECT value FROM restore_marker").fetchone()
    assert value == ("before",)
    assert restored.name == selected.name
    assert safety_backup.kind == "pre_restore"
    assert manager.validate(safety_backup.name).size_bytes > 0
