from pathlib import Path

from rangebot.ui import engine_bootstrap


def test_bundled_engine_starts_paper_safe_when_local_engine_is_offline(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "bot-engine.exe"
    executable.touch()
    calls: dict[str, object] = {}

    monkeypatch.setattr(engine_bootstrap, "_localhost_engine_is_listening", lambda: False)
    monkeypatch.setattr(engine_bootstrap, "bundled_engine", lambda: (executable, tmp_path))
    monkeypatch.setattr(
        engine_bootstrap.subprocess,
        "Popen",
        lambda command, **kwargs: calls.update(command=command, **kwargs),
    )

    assert engine_bootstrap.start_bundled_engine_if_needed() is True
    assert calls["command"] == [str(executable), "--mode", "paper"]
    assert "--enable-read-only-exchange" not in calls["command"]
    assert "--enable-order-submission" not in calls["command"]
    assert calls["env"]["RANGEBOT_ENV_FILE"].endswith("runtime\\.env")


def test_bundled_engine_does_not_start_when_local_engine_already_listens(monkeypatch) -> None:
    monkeypatch.setattr(engine_bootstrap, "_localhost_engine_is_listening", lambda: True)

    assert engine_bootstrap.start_bundled_engine_if_needed() is False
