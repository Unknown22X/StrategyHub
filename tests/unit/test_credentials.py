from subprocess import CompletedProcess

import pytest

from rangebot.engine.credentials import load_gate_credentials, save_gate_credentials


def test_local_env_credentials_round_trip_without_exposing_other_mode(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / ".env"
    monkeypatch.setenv("RANGEBOT_ENV_FILE", str(path))
    monkeypatch.setattr(
        "rangebot.engine.credentials.subprocess.run",
        lambda args, **kwargs: CompletedProcess(args, 0, stdout="user:(F)"),
    )

    save_gate_credentials("testnet", "test-key", "test-secret")

    stored = load_gate_credentials("testnet")
    assert stored is not None
    assert stored.api_key == "test-key"
    assert stored.api_secret == "test-secret"
    assert load_gate_credentials("live") is None
    assert "GATE_TESTNET_KEY=test-key" in path.read_text(encoding="utf-8")

    save_gate_credentials("testnet", "second-key", "second-secret")
    assert load_gate_credentials("testnet").api_key == "second-key"  # type: ignore[union-attr]


def test_acl_failure_leaves_no_credential_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / ".env"
    monkeypatch.setenv("RANGEBOT_ENV_FILE", str(path))
    monkeypatch.setattr(
        "rangebot.engine.credentials.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    with pytest.raises(PermissionError):
        save_gate_credentials("live", "key", "secret")

    assert not path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
