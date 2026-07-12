"""Database and migration helpers for restart-critical runtime state."""

from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def create_database_engine(database_url: str) -> Engine:
    """Create the engine used by the local lifecycle-state repository."""
    url = make_url(database_url)
    if url.drivername == "sqlite" and url.database not in (None, ":memory:"):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url)


def apply_migrations(database_url: str) -> None:
    """Upgrade the supplied database through RangeBot's Alembic migration path."""
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
