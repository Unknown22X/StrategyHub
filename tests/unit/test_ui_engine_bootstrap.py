from pathlib import Path
from subprocess import CompletedProcess

from rangebot.ui import engine_bootstrap


def test_bundled_engine_fallback_starts_paper_with_real_safety_boundaries(
    monkeypatch, tmp_path: Path
) -> None:
    executable = tmp_path / "bot-engine.exe"
    executable.touch()
    calls: dict[str, object] = {}

    monkeypatch.setattr(
        engine_bootstrap, "_localhost_engine_is_listening", lambda: False
    )
    monkeypatch.setattr(engine_bootstrap, "bundled_service_wrapper", lambda: None)
    monkeypatch.setattr(
        engine_bootstrap, "bundled_engine", lambda: (executable, tmp_path)
    )
    monkeypatch.setattr(
        engine_bootstrap.subprocess,
        "Popen",
        lambda command, **kwargs: calls.update(command=command, **kwargs),
    )

    assert engine_bootstrap.start_bundled_engine_if_needed() is True
    assert calls["command"] == [
        str(executable),
        "--mode",
        "paper",
        "--enable-read-only-exchange",
        "--enable-order-submission",
        "--enable-public-websocket",
        "--enable-private-websocket",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert "RANGEBOT_ENV_FILE" not in calls["env"]


def test_launcher_recovers_installed_service_before_using_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    wrapper = tmp_path / "RangeBot.Engine.exe"
    wrapper.touch()
    service_calls: list[list[str]] = []

    monkeypatch.setattr(
        engine_bootstrap, "_localhost_engine_is_listening", lambda: False
    )
    monkeypatch.setattr(engine_bootstrap, "bundled_service_wrapper", lambda: wrapper)
    monkeypatch.setattr(engine_bootstrap, "bundled_engine", lambda: None)
    monkeypatch.setattr(
        engine_bootstrap.subprocess,
        "run",
        lambda command, **kwargs: (
            service_calls.append(command) or CompletedProcess(command, 0, "Started", "")
        ),
    )

    assert engine_bootstrap.start_bundled_engine_if_needed() is True
    assert service_calls == [[str(wrapper), "start"]]


def test_launcher_restarts_service_when_start_reports_failure(
    monkeypatch, tmp_path: Path
) -> None:
    wrapper = tmp_path / "RangeBot.Engine.exe"
    wrapper.touch()
    service_calls: list[list[str]] = []

    monkeypatch.setattr(
        engine_bootstrap, "_localhost_engine_is_listening", lambda: False
    )
    monkeypatch.setattr(engine_bootstrap, "bundled_service_wrapper", lambda: wrapper)
    monkeypatch.setattr(engine_bootstrap, "bundled_engine", lambda: None)

    def service_command(command, **kwargs):
        service_calls.append(command)
        return CompletedProcess(command, 1 if command[-1] == "start" else 0, "", "")

    monkeypatch.setattr(engine_bootstrap.subprocess, "run", service_command)

    assert engine_bootstrap.start_bundled_engine_if_needed() is True
    assert service_calls == [[str(wrapper), "start"], [str(wrapper), "restart"]]


def test_bundled_engine_does_not_start_when_local_engine_already_listens(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        engine_bootstrap, "_localhost_engine_is_listening", lambda: True
    )

    assert engine_bootstrap.start_bundled_engine_if_needed() is False
