"""Create sanitized support archives without credentials or mutable user databases."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import re
from threading import RLock
from zipfile import ZIP_DEFLATED, ZipFile


_ALLOWED_SUFFIXES = {".log", ".txt", ".json", ".jsonl"}
_BLOCKED_NAME_FRAGMENTS = {
    "credential",
    "secret",
    "password",
    "private",
    "database",
    "backup",
    "rangebot.db",
    ".env",
}
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_ARCHIVE_INPUT_BYTES = 50 * 1024 * 1024

_REDACTION_PATTERNS = (
    re.compile(
        r"(?im)^(\s*(?:authorization|x-gate-key|key|sign|signature)\s*[:=]\s*).+$"
    ),
    re.compile(
        r"(?i)([\"']?(?:api[_-]?key|api[_-]?secret|password|passphrase|token|secret|signature)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"']+"
    ),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
)


class SupportLogExporter:
    """Collect bounded text logs and redact common authentication material."""

    def __init__(
        self,
        log_directory: Path,
        *,
        export_directory: Path | None = None,
    ) -> None:
        self._log_directory = log_directory.expanduser().resolve()
        self._export_directory = (
            export_directory.expanduser().resolve()
            if export_directory is not None
            else self._log_directory / "exports"
        )
        self._log_directory.mkdir(parents=True, exist_ok=True)
        self._export_directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def export(self) -> Path:
        with self._lock:
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            destination = self._export_directory / f"rangebot-support-{timestamp}.zip"
            total_bytes = 0
            with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
                for path in self._candidate_files():
                    size = path.stat().st_size
                    if size > _MAX_FILE_BYTES or total_bytes + size > _MAX_ARCHIVE_INPUT_BYTES:
                        continue
                    content = path.read_text(encoding="utf-8", errors="replace")
                    redacted = self._redact(content)
                    archive.writestr(path.relative_to(self._log_directory).as_posix(), redacted)
                    total_bytes += size
                archive.writestr(
                    "SUPPORT-ARCHIVE.txt",
                    "RangeBot support logs. Credentials, database files, backups, and authentication material are excluded or redacted.\n",
                )
            return destination

    def _candidate_files(self) -> list[Path]:
        candidates: list[Path] = []
        for path in self._log_directory.rglob("*"):
            if not path.is_file() or self._export_directory in path.parents:
                continue
            normalized_name = path.name.casefold()
            if path.suffix.casefold() not in _ALLOWED_SUFFIXES:
                continue
            if any(fragment in normalized_name for fragment in _BLOCKED_NAME_FRAGMENTS):
                continue
            candidates.append(path)
        return sorted(candidates, key=lambda item: item.relative_to(self._log_directory).as_posix())

    @staticmethod
    def _redact(content: str) -> str:
        redacted = content
        for pattern in _REDACTION_PATTERNS:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", redacted)
        return redacted
