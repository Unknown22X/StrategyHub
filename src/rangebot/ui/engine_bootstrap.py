"""Start the bundled localhost engine when the desktop package is used alone."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys


LOCAL_ENGINE_PORT = 8765


def _localhost_engine_is_listening() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", LOCAL_ENGINE_PORT), timeout=0.15):
            return True
    except OSError:
        return False


def bundled_engine() -> tuple[Path, Path] | None:
    """Return the bundled engine executable and its RangeBot root, if present."""
    configured = os.environ.get("RANGEBOT_ENGINE_PATH")
    if configured:
        executable = Path(configured)
        return (executable, executable.parent.parent) if executable.is_file() else None
    if not getattr(sys, "frozen", False):
        return None

    ui_directory = Path(sys.executable).resolve().parent
    candidates = (
        (ui_directory.parent / "bot-engine" / "bot-engine.exe", ui_directory.parent.parent),
        (ui_directory.parent / "engine" / "bot-engine.exe", ui_directory.parent),
    )
    return next(((path, root) for path, root in candidates if path.is_file()), None)


def start_bundled_engine_if_needed() -> bool:
    """Start a local Paper-safe engine only when no localhost engine is available."""
    if _localhost_engine_is_listening():
        return False
    bundle = bundled_engine()
    if bundle is None:
        return False

    executable, root = bundle
    environment = os.environ.copy()
    config_file = root / "config" / ".env"
    environment.setdefault(
        "RANGEBOT_ENV_FILE",
        str(config_file if config_file.parent.exists() else root / "runtime" / ".env"),
    )
    subprocess.Popen(
        [str(executable), "--mode", "paper"],
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True
