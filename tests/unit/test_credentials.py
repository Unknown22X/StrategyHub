from pathlib import Path

import pytest

from rangebot.engine.credentials import (
    load_gate_credentials,
    masked_gate_api_key,
    remove_gate_credentials,
    save_gate_credentials,
)


def _install_test_protector(monkeypatch) -> None:
    monkeypatch.setattr(
        "rangebot.engine.credentials._protect_for_current_user",
        lambda value: b"protected:" + value[::-1],
    )
    monkeypatch.setattr(
        "rangebot.engine.credentials._unprotect_for_current_user",
        lambda value: value.removeprefix(b"protected:")[::-1],
    )


def test_protected_credentials_round_trip_replace_and_isolate_modes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    _install_test_protector(monkeypatch)

    save_gate_credentials("testnet", "test-key", "test-secret")

    stored = load_gate_credentials("testnet")
    assert stored is not None
    assert stored.api_key == "test-key"
    assert stored.api_secret == "test-secret"
    assert load_gate_credentials("live") is None
    assert masked_gate_api_key("testnet") == "tes••••ey"

    credential_file = (
        tmp_path / "RangeBot" / "config" / "credentials" / "gate-testnet.bin"
    )
    raw = credential_file.read_bytes()
    assert b"test-key" not in raw
    assert b"test-secret" not in raw
    assert not list((tmp_path / "RangeBot").rglob(".env"))

    save_gate_credentials("testnet", "second-key", "second-secret")
    replaced = load_gate_credentials("testnet")
    assert replaced is not None
    assert replaced.api_key == "second-key"
    assert replaced.api_secret == "second-secret"


def test_remove_credentials_deletes_protected_file_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    _install_test_protector(monkeypatch)
    save_gate_credentials("live", "live-key", "live-secret")

    assert remove_gate_credentials("live") is True
    assert load_gate_credentials("live") is None
    assert remove_gate_credentials("live") is False


def test_protection_failure_leaves_no_credential_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    monkeypatch.setattr(
        "rangebot.engine.credentials._protect_for_current_user",
        lambda value: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(PermissionError):
        save_gate_credentials("live", "key", "secret")

    credential_directory = tmp_path / "RangeBot" / "config" / "credentials"
    assert not list(credential_directory.glob("gate-live.bin*"))


def test_corrupt_protected_credentials_are_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("RANGEBOT_HOME", str(tmp_path / "RangeBot"))
    _install_test_protector(monkeypatch)
    credential_directory = tmp_path / "RangeBot" / "config" / "credentials"
    credential_directory.mkdir(parents=True)
    (credential_directory / "gate-live.bin").write_bytes(b"not-valid-protected-json")

    with pytest.raises(ValueError, match="invalid"):
        load_gate_credentials("live")
