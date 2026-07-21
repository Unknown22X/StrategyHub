from argparse import ArgumentParser

import pytest

from rangebot.ui import main as ui_main


def test_launcher_accepts_only_plain_localhost_origins() -> None:
    parsed = ui_main.parse_arguments(
        ["--engine-url", "http://localhost:8765/", "--once"]
    )

    assert parsed.engine_url == "http://localhost:8765"
    assert parsed.once is True

    with pytest.raises(SystemExit):
        ui_main.parse_arguments(["--engine-url", "https://127.0.0.1:8765"])
    with pytest.raises(SystemExit):
        ui_main.parse_arguments(["--engine-url", "http://example.com:8765"])
    with pytest.raises(SystemExit):
        ui_main.parse_arguments(
            ["--engine-url", "http://user:password@127.0.0.1:8765"]
        )


def test_validated_engine_url_rejects_query_and_fragment() -> None:
    parser = ArgumentParser()

    with pytest.raises(SystemExit):
        ui_main._validated_engine_url(parser, "http://127.0.0.1:8765?token=x")
    with pytest.raises(SystemExit):
        ui_main._validated_engine_url(parser, "http://127.0.0.1:8765/#app")


def test_once_mode_checks_engine_without_requiring_dashboard(monkeypatch) -> None:
    started: list[bool] = []
    monkeypatch.setattr(
        ui_main,
        "start_bundled_engine_if_needed",
        lambda: started.append(True),
    )
    monkeypatch.setattr(ui_main, "_wait_for_engine", lambda *_: True)
    monkeypatch.setattr(
        ui_main,
        "_dashboard_is_available",
        lambda *_: pytest.fail("dashboard should not be checked in --once mode"),
    )

    with pytest.raises(SystemExit) as exit_info:
        ui_main.main(["--once"])

    assert exit_info.value.code == 0
    assert started == [True]


def test_no_browser_prints_dashboard_url(monkeypatch, capsys) -> None:
    monkeypatch.setattr(ui_main, "start_bundled_engine_if_needed", lambda: False)
    monkeypatch.setattr(ui_main, "_wait_for_engine", lambda *_: True)
    monkeypatch.setattr(ui_main, "_dashboard_is_available", lambda *_: True)
    monkeypatch.setattr(
        ui_main.webbrowser,
        "open",
        lambda *_args, **_kwargs: pytest.fail("browser should remain closed"),
    )

    with pytest.raises(SystemExit) as exit_info:
        ui_main.main(["--no-browser"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == "http://127.0.0.1:8765/app/"


def test_launcher_fails_clearly_when_dashboard_assets_are_missing(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(ui_main, "start_bundled_engine_if_needed", lambda: False)
    monkeypatch.setattr(ui_main, "_wait_for_engine", lambda *_: True)
    monkeypatch.setattr(ui_main, "_dashboard_is_available", lambda *_: False)

    with pytest.raises(SystemExit) as exit_info:
        ui_main.main([])

    assert exit_info.value.code == 2
    assert "compiled dashboard assets are unavailable" in capsys.readouterr().err
