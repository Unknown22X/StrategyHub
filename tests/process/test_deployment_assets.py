from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_winsw_service_is_automatic_restartable_and_separate_from_ui() -> None:
    xml = (ROOT / "deploy" / "RangeBot.Engine.xml").read_text(encoding="utf-8")

    assert "<startmode>Automatic</startmode>" in xml
    assert "<autoRefresh>false</autoRefresh>" in xml
    assert "bot-engine.exe" in xml
    assert "rangebot-control" not in xml
    assert '<onfailure action="restart"' in xml
    assert "<pattern>yyyyMMdd</pattern>" in xml
    assert "<stoptimeout>30 sec</stoptimeout>" in xml
    assert "--mode paper" in xml
    assert "--mode live" not in xml
    assert "--enable-order-submission" in xml
    assert "--enable-public-websocket" in xml
    assert "--enable-private-websocket" in xml
    assert "__RANGEBOT_LOG_ROOT__" in xml
    assert "NT AUTHORITY\\LocalService" in xml
    assert 'RANGEBOT_HOME" value="__RANGEBOT_DATA_ROOT__"' in xml
    assert "%ProgramData%" not in xml
    assert "RANGEBOT_ENV_FILE" not in xml
    assert "RANGEBOT_DATABASE_URL" not in xml


def test_service_installer_uses_passwordless_local_service_without_writing_credentials() -> (
    None
):
    installer = (ROOT / "deploy" / "install-service.ps1").read_text(encoding="utf-8")

    assert "PSCredential" not in installer
    assert "Get-Credential" not in installer
    assert "Start-Process -FilePath sc.exe" in installer
    assert "NT AUTHORITY\\LocalService" in installer
    assert "icacls.exe" in installer
    assert "[string]$DataRoot" in installer
    assert "IsPathRooted" in installer
    assert "GetPathRoot($resolvedDataRoot)" in installer
    assert "unexpectedItems" in installer
    assert ".rangebot-data-root" in installer
    assert "installRootWithSeparator" in installer
    assert "Get-CimInstance Win32_Process" in installer
    assert "SessionId -eq $sessionId" in installer
    assert "GetOwner" in installer
    assert "ProfileList\\$interactiveUserSid" in installer
    assert '"*${interactiveUserSid}:(OI)(CI)(F)"' in installer
    assert 'SetAttribute("value", $resolvedDataRoot)' in installer
    assert "$serviceXml.Save($configuration)" in installer
    assert "& $winsw stop" in installer
    assert "& $winsw uninstall" in installer
    assert "& sc.exe delete $serviceName" in installer
    assert "remained registered after upgrade removal" in installer
    assert "$env:ProgramData" not in installer
    assert "Set-Content" not in installer
    assert "Add-Content" not in installer


def test_service_uninstaller_fails_closed_if_the_engine_cannot_be_removed() -> None:
    uninstaller = (ROOT / "deploy" / "uninstall-service.ps1").read_text(
        encoding="utf-8"
    )

    assert '$ErrorActionPreference = "Stop"' in uninstaller
    assert "Get-Service -Name $serviceName" in uninstaller
    assert "& $winsw stop" in uninstaller
    assert "& $winsw uninstall" in uninstaller
    assert "$LASTEXITCODE -ne 0" in uninstaller
    assert "remained registered after removal" in uninstaller
    assert "AddSeconds(45)" in uninstaller
    assert "[switch]$RemovePersonalData" in uninstaller
    assert "SelectSingleNode(\"/service/env[@name='RANGEBOT_HOME']\")" in uninstaller
    assert 'GetFileName($dataRoot) -ne "RangeBot"' in uninstaller
    assert "Remove-Item -LiteralPath $dataRoot -Recurse -Force" in uninstaller
    assert '$ErrorActionPreference = "Continue"' not in uninstaller


def test_packaging_and_operations_assets_exclude_credentials_and_legacy_database_tools() -> (
    None
):
    engine_spec = (ROOT / "deploy" / "engine.spec").read_text(encoding="utf-8")
    ui_spec = (ROOT / "deploy" / "ui.spec").read_text(encoding="utf-8")
    installer = (ROOT / "deploy" / "RangeBot.iss").read_text(encoding="utf-8")
    operations = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")

    assert ".env" not in engine_spec + ui_spec + installer
    assert "bot-engine" in engine_spec
    assert '"frontend/dist"' in engine_spec
    assert 'frontend_dist / "index.html"' in engine_spec
    assert 'name="RangeBot"' in ui_spec
    assert "console=True" in engine_spec
    assert 'hide_console="hide-early"' in engine_spec
    assert "console=False" in ui_spec
    assert "backup-postgresql" not in installer + operations
    assert "restore-postgresql" not in installer + operations
    assert "pg_dump" not in installer + operations
    assert "pg_restore" not in installer + operations
