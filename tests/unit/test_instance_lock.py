from pathlib import Path

import pytest

from rangebot.engine.instance_lock import (
    EngineAlreadyRunningError,
    EngineInstanceLock,
    engine_lock_path,
)


def test_engine_instance_lock_rejects_duplicate_and_releases_after_exit(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime" / "engine.lock"
    first = EngineInstanceLock(path)
    second = EngineInstanceLock(path)

    first.acquire()
    try:
        with pytest.raises(EngineAlreadyRunningError):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()


def test_engine_lock_path_uses_application_runtime_directory(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))

    path = engine_lock_path(8765)

    assert path == (tmp_path / "RangeBot" / "runtime" / "engine-8765.lock").resolve()
    assert path.parent.is_dir()


@pytest.mark.parametrize("port", [0, 65536])
def test_engine_lock_path_rejects_invalid_ports(port: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 65535"):
        engine_lock_path(port)
