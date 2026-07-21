"""Cross-process duplicate-engine prevention for the local service port."""

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO

from rangebot.engine.paths import application_paths


class EngineAlreadyRunningError(RuntimeError):
    """Raised when another engine process owns the requested instance lock."""


class EngineInstanceLock:
    """Hold an operating-system file lock for the lifetime of one engine."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        if self._file is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            self._lock(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()).encode("ascii"))
            handle.flush()
        except Exception:
            handle.close()
            raise
        self._file = handle

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        try:
            self._unlock(handle)
        finally:
            handle.close()
            self._file = None

    def __enter__(self) -> "EngineInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()

    @staticmethod
    def _lock(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise EngineAlreadyRunningError(
                    "Another RangeBot engine instance is already running."
                ) from error
            return

        import fcntl

        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise EngineAlreadyRunningError(
                "Another RangeBot engine instance is already running."
            ) from error

    @staticmethod
    def _unlock(handle: BinaryIO) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return

        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def engine_lock_path(port: int) -> Path:
    """Return the current-user lock path for one localhost engine port."""
    if not 1 <= port <= 65535:
        raise ValueError("Engine port must be between 1 and 65535.")
    return application_paths().runtime / f"engine-{port}.lock"
