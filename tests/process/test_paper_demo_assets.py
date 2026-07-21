from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
START = ROOT / "demo" / "Start-StrategyHub-Paper-Demo.ps1"
STOP = ROOT / "demo" / "Stop-StrategyHub-Paper-Demo.ps1"
COMMAND = ROOT / "demo" / "StrategyHub-Paper-Demo.cmd"
INSTALLER = ROOT / "deploy" / "RangeBot.iss"
STATUS = ROOT / "PAPER_DEMO_STATUS.md"


def test_paper_demo_launcher_is_isolated_and_safety_validated() -> None:
    start = START.read_text(encoding="utf-8")
    stop = STOP.read_text(encoding="utf-8")
    command = COMMAND.read_text(encoding="utf-8")

    assert "StrategyHub-Paper-Demo-20260721\\RangeBot" in start
    assert '"--mode", "paper"' in start
    assert '"--port", "$Port"' in start
    assert "$Port = 8876" in start
    assert "--enable-public-websocket" in start
    assert "--enable-private-websocket" not in start
    assert "--enable-read-only-exchange" not in start
    assert "--enable-order-submission" not in start
    assert "configured_environment" in start
    assert "requested_environment" in start
    assert "active_engine_environment" in start
    assert "exchange_adapter_environment" in start
    assert "transition_state" in start
    assert "credential_profile" in start
    assert "Stop-Process" in stop
    assert "Remove-Item" in stop
    assert "-Recurse" not in stop
    assert "Start-StrategyHub-Paper-Demo.ps1" in command


def test_installer_includes_separate_paper_demo_shortcuts() -> None:
    installer = INSTALLER.read_text(encoding="utf-8-sig")
    assert 'Source: "..\\demo\\*"' in installer
    assert installer.count("StrategyHub Paper Demo") >= 2
    assert "Start-StrategyHub-Paper-Demo.ps1" in installer
    assert "RangeBot.Engine.xml" in installer


def test_status_records_preserved_and_clean_roots() -> None:
    status = STATUS.read_text(encoding="utf-8")
    assert "C:\\Users\\JORY\\AppData\\Local\\RangeBot" in status
    assert "RangeBot-Live-Preserved-20260721T1711Z" in status
    assert "StrategyHub-Paper-Demo-20260721\\RangeBot" in status
    assert "a9907a76ba00e0c3d14c619511d3b168565eef73998bd79cfadccffac8323a64" in status
    assert "context_unavailable:AttributeError" in status
    assert "4c68447c-450c-490a-8f3e-cb7b7c3346ad" in status
