"""Restricted local .env storage for Gate.io API credentials."""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class StoredGateCredentials:
    api_key: str
    api_secret: str


def credential_file() -> Path:
    return Path(os.getenv("RANGEBOT_ENV_FILE", "runtime/.env"))


def _names(mode: str) -> tuple[str, str]:
    if mode not in {"testnet", "live"}:
        raise ValueError("Credentials are supported only for Testnet and Live.")
    prefix = "GATE_TESTNET" if mode == "testnet" else "GATE_LIVE"
    return f"{prefix}_KEY", f"{prefix}_SECRET"


def _read_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values


def save_gate_credentials(mode: str, api_key: str, api_secret: str) -> None:
    """Write credentials locally and restrict the file to the current Windows user."""
    if not api_key.strip() or not api_secret.strip():
        raise ValueError("API key and secret are required.")
    key_name, secret_name = _names(mode)
    path = credential_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    values = _read_values(path)
    values[key_name] = api_key.strip()
    values[secret_name] = api_secret.strip()
    temporary = path.with_suffix(path.suffix + ".tmp")
    replaced = False
    try:
        temporary.write_text(
            "".join(f"{name}={value}\n" for name, value in sorted(values.items())),
            encoding="utf-8",
        )
        _restrict_windows_file(temporary)
        temporary.replace(path)
        replaced = True
        _verify_windows_file(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        if replaced:
            path.unlink(missing_ok=True)
        raise


def _restrict_windows_file(path: Path) -> None:
    if os.name != "nt" or not (username := os.environ.get("USERNAME")):
        return
    subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{username}:(F)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _verify_windows_file(path: Path) -> None:
    if os.name != "nt":
        return
    result = subprocess.run(
        ["icacls", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    if "(F)" not in result.stdout:
        raise PermissionError("Credential file ACL verification failed.")


def load_gate_credentials(mode: str) -> StoredGateCredentials | None:
    """Read the local credential file without exporting secrets to UI or logs."""
    key_name, secret_name = _names(mode)
    values = _read_values(credential_file())
    key = os.getenv(key_name, values.get(key_name, ""))
    secret = os.getenv(secret_name, values.get(secret_name, ""))
    if not key or not secret:
        return None
    return StoredGateCredentials(api_key=key, api_secret=secret)
