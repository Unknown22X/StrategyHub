"""Absolute, user-owned runtime paths for the locally installed application."""

from dataclasses import dataclass
import os
from pathlib import Path

from sqlalchemy.engine import URL


@dataclass(frozen=True)
class ApplicationPaths:
    """The mutable application directories owned by the current Windows user."""

    root: Path
    data: Path
    config: Path
    logs: Path
    backup: Path
    runtime: Path

    def directories(self) -> tuple[Path, ...]:
        return (
            self.root,
            self.data,
            self.config,
            self.logs,
            self.backup,
            self.runtime,
        )


def _default_root() -> Path:
    override = os.getenv("RANGEBOT_HOME")
    if override:
        return Path(override).expanduser().resolve()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return (Path(local_app_data).expanduser() / "RangeBot").resolve()

    xdg_data_home = os.getenv("XDG_DATA_HOME")
    base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
    return (base / "RangeBot").resolve()


def application_paths() -> ApplicationPaths:
    """Resolve and create all mutable application directories."""
    root = _default_root()
    paths = ApplicationPaths(
        root=root,
        data=root / "data",
        config=root / "config",
        logs=root / "logs",
        backup=root / "backup",
        runtime=root / "runtime",
    )
    for directory in paths.directories():
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def default_database_url() -> str:
    """Return the SQLite URL used by the installed engine by default."""
    database = application_paths().data / "rangebot.db"
    return str(URL.create("sqlite", database=str(database)))
