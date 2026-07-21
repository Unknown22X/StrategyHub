"""Windows machine-protected storage for Gate.io API credentials."""

from ctypes import POINTER, Structure, byref, c_char, c_void_p, cast, memmove
from ctypes import wintypes
from dataclasses import dataclass
import ctypes
import json
import os
from pathlib import Path

from rangebot.engine.paths import application_paths


@dataclass(frozen=True)
class StoredGateCredentials:
    api_key: str
    api_secret: str


class _DataBlob(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(c_char))]


def _credential_path(mode: str) -> Path:
    _validate_mode(mode)
    override = os.getenv("RANGEBOT_CREDENTIAL_DIRECTORY")
    directory = (
        Path(override).expanduser().resolve()
        if override
        else application_paths().config / "credentials"
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"gate-{mode}.bin"


def _validate_mode(mode: str) -> None:
    if mode not in {"testnet", "live"}:
        raise ValueError("Credentials are supported only for Testnet and Live.")


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array[c_char]]:
    buffer = (c_char * len(data))()
    if data:
        memmove(buffer, data, len(data))
    return _DataBlob(len(data), cast(buffer, POINTER(c_char))), buffer


def _bytes_from_blob(blob: _DataBlob) -> bytes:
    if not blob.pbData or blob.cbData == 0:
        return b""
    return bytes(cast(blob.pbData, POINTER(c_char * blob.cbData)).contents)


def _protect_for_current_user(data: bytes) -> bytes:
    """Protect bytes with machine DPAPI for the LocalService engine identity."""
    if os.name != "nt":
        raise OSError("Windows DPAPI is required for product credential storage.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, source_buffer = _blob_from_bytes(data)
    destination = _DataBlob()
    crypt32.CryptProtectData.argtypes = [
        POINTER(_DataBlob),
        wintypes.LPCWSTR,
        POINTER(_DataBlob),
        c_void_p,
        c_void_p,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(
        byref(source),
        "RangeBot Gate.io credentials",
        None,
        None,
        None,
        0x4,  # CRYPTPROTECT_LOCAL_MACHINE
        byref(destination),
    ):
        raise ctypes.WinError()
    try:
        return _bytes_from_blob(destination)
    finally:
        kernel32.LocalFree(destination.pbData)
        del source_buffer


def _unprotect_for_current_user(data: bytes) -> bytes:
    """Unprotect machine-scoped DPAPI bytes for the engine service identity."""
    if os.name != "nt":
        raise OSError("Windows DPAPI is required for product credential storage.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, source_buffer = _blob_from_bytes(data)
    destination = _DataBlob()
    crypt32.CryptUnprotectData.argtypes = [
        POINTER(_DataBlob),
        POINTER(wintypes.LPWSTR),
        POINTER(_DataBlob),
        c_void_p,
        c_void_p,
        wintypes.DWORD,
        POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    description = wintypes.LPWSTR()
    if not crypt32.CryptUnprotectData(
        byref(source),
        byref(description),
        None,
        None,
        None,
        0,
        byref(destination),
    ):
        raise ctypes.WinError()
    try:
        return _bytes_from_blob(destination)
    finally:
        if description:
            kernel32.LocalFree(description)
        kernel32.LocalFree(destination.pbData)
        del source_buffer


def save_gate_credentials(mode: str, api_key: str, api_secret: str) -> None:
    """Atomically save credentials encrypted for the local machine."""
    _validate_mode(mode)
    key = api_key.strip()
    secret = api_secret.strip()
    if not key or not secret:
        raise ValueError("API key and secret are required.")

    payload = json.dumps(
        {"api_key": key, "api_secret": secret},
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    protected = _protect_for_current_user(payload)
    path = _credential_path(mode)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_bytes(protected)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def load_gate_credentials(mode: str) -> StoredGateCredentials | None:
    """Load protected credentials without exposing them to UI responses or logs."""
    path = _credential_path(mode)
    if not path.exists():
        return None
    try:
        payload = json.loads(_unprotect_for_current_user(path.read_bytes()).decode("utf-8"))
        key = str(payload["api_key"])
        secret = str(payload["api_secret"])
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Stored Gate.io credentials are invalid.") from error
    if not key or not secret:
        raise ValueError("Stored Gate.io credentials are incomplete.")
    return StoredGateCredentials(api_key=key, api_secret=secret)


def remove_gate_credentials(mode: str) -> bool:
    """Remove credentials for one environment and any interrupted temporary write."""
    path = _credential_path(mode)
    existed = path.exists()
    path.unlink(missing_ok=True)
    path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)
    return existed


def masked_gate_api_key(mode: str) -> str | None:
    """Return a non-sensitive key hint suitable for a settings screen."""
    stored = load_gate_credentials(mode)
    if stored is None:
        return None
    if len(stored.api_key) <= 4:
        return "••••"
    return f"{stored.api_key[:3]}••••{stored.api_key[-2:]}"
