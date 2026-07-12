from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_winsw_service_is_automatic_restartable_and_separate_from_ui() -> None:
    xml = (ROOT / "deploy" / "RangeBot.Engine.xml").read_text(encoding="utf-8")

    assert "<startmode>Automatic</startmode>" in xml
    assert "bot-engine.exe" in xml
    assert "rangebot-control" not in xml
    assert '<onfailure action="restart"' in xml
    assert "<stoptimeout>30 sec</stoptimeout>" in xml


def test_packaging_and_operations_assets_exclude_credentials() -> None:
    engine_spec = (ROOT / "deploy" / "engine.spec").read_text(encoding="utf-8")
    ui_spec = (ROOT / "deploy" / "ui.spec").read_text(encoding="utf-8")
    restore = (ROOT / "deploy" / "restore-postgresql.ps1").read_text(encoding="utf-8")

    assert ".env" not in engine_spec + ui_spec
    assert "bot-engine" in engine_spec
    assert "rangebot-control" in ui_spec
    assert "--restored-state" in restore
    assert "RESTORE RANGEBOT" in restore
