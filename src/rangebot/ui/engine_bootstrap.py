"""Start or recover the installed localhost engine without owning its lifetime."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET


LOCAL_ENGINE_PORT = 8765
_ENGINE_ARGUMENTS = (
    "--mode",
    "paper",
    "--enable-read-only-exchange",
    "--enable-order-submission",
    "--enable-public-websocket",
    "--enable-private-websocket",
    "--host",
    "127.0.0.1",
    "--port",
    str(LOCAL_ENGINE_PORT),
)


def _localhost_engine_is_listening() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", LOCAL_ENGINE_PORT), timeout=0.15):
            return True
    except OSError:
        return False


def bundled_engine() -> tuple[Path, Path] | None:
    """Return the bundled engine executable and RangeBot installation root."""
    configured = os.environ.get("RANGEBOT_ENGINE_PATH")
    if configured:
        executable = Path(configured).expanduser().resolve()
        return (executable, executable.parent.parent) if executable.is_file() else None
    if not getattr(sys, "frozen", False):
        return None

    launcher_directory = Path(sys.executable).resolve().parent
    candidates = (
        (
            launcher_directory.parent / "engine" / "bot-engine.exe",
            launcher_directory.parent,
        ),
        (
            launcher_directory.parent / "bot-engine" / "bot-engine.exe",
            launcher_directory.parent.parent,
        ),
    )
    return next(((path, root) for path, root in candidates if path.is_file()), None)


def bundled_service_wrapper() -> Path | None:
    """Return the installed WinSW wrapper when available."""
    configured = os.environ.get("RANGEBOT_SERVICE_PATH")
    if configured:
        wrapper = Path(configured).expanduser().resolve()
        return wrapper if wrapper.is_file() else None
    if not getattr(sys, "frozen", False):
        return None
    launcher_directory = Path(sys.executable).resolve().parent
    wrapper = launcher_directory.parent / "service" / "RangeBot.Engine.exe"
    return wrapper if wrapper.is_file() else None


def _run_service_command(
    wrapper: Path, action: str
) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            [str(wrapper), action],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _recover_windows_service(wrapper: Path) -> bool:
    """Start the service, or restart it when WinSW reports it is already running."""
    started = _run_service_command(wrapper, "start")
    if started is not None and started.returncode == 0:
        return True
    restarted = _run_service_command(wrapper, "restart")
    return restarted is not None and restarted.returncode == 0


def _installed_data_root(root: Path) -> Path | None:
    """Read the installed service's authoritative mutable-data root.

    The packaged launcher must not silently fall back to the current user's
    default ``%LOCALAPPDATA%\\RangeBot`` profile when the service was installed
    with a separate demo or production root.
    """

    configuration = root / "service" / "RangeBot.Engine.xml"
    if not configuration.is_file():
        return None
    try:
        document = ET.parse(configuration)
    except (OSError, ET.ParseError):
        return None
    for node in document.getroot().findall("env"):
        if node.get("name") != "RANGEBOT_HOME":
            continue
        value = (node.get("value") or "").strip()
        if not value:
            return None
        candidate = Path(value).expanduser()
        return candidate if candidate.is_absolute() else None
    return None


def _start_detached_fallback(executable: Path, root: Path) -> bool:
    environment = os.environ.copy()
    environment.pop("RANGEBOT_ENV_FILE", None)
    service_configuration = root / "service" / "RangeBot.Engine.xml"
    if service_configuration.exists():
        data_root = _installed_data_root(root)
        if data_root is None:
            return False
        environment["RANGEBOT_HOME"] = str(data_root)
    try:
        subprocess.Popen(
            [str(executable), *_ENGINE_ARGUMENTS],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        return False
    return True


def start_bundled_engine_if_needed() -> bool:
    """Recover the service first, then use a detached Paper-configured fallback."""
    if _localhost_engine_is_listening():
        return False

    wrapper = bundled_service_wrapper()
    if wrapper is not None and _recover_windows_service(wrapper):
        return True

    bundle = bundled_engine()
    if bundle is None:
        return False
    executable, root = bundle
    return _start_detached_fallback(executable, root)
