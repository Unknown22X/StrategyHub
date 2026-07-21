import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_script_is_fail_fast_and_requires_exact_installer_output() -> None:
    script = (ROOT / "build_release.bat").read_text(encoding="utf-8")

    assert "uv sync --group dev" in script
    assert 'set "UV_PROJECT_ENVIRONMENT=.venv-release"' in script
    assert 'set "TEMP=%ROOT%\\.release-tmp"' in script
    assert 'set "TMP=%TEMP%"' in script
    assert "Node.js 20.19+, 22.12+, or 24+" in script
    assert "if (!ok)" not in script
    assert "if (ok === false) process.exit(1)" in script
    assert "frontend\\package-lock.json is required" in script
    assert "call npm ci" in script
    assert "npm install" not in script
    assert "npm run typecheck" in script
    assert "npm test" in script
    assert "npm run build" in script
    assert "uv run pytest -q" in script
    assert "deploy\\engine.spec" in script
    assert "deploy\\ui.spec" in script
    assert "deploy\\RangeBot.iss" in script
    assert "%LocalAppData%\\Programs\\Inno Setup 6\\ISCC.exe" in script
    assert "release\\RangeBot-Setup.exe" in script
    assert "if errorlevel 1 goto :failed" in script
    assert "v2.12.0" not in script
    assert "WIN_SW_VERSION=2.12.0" in script


def test_release_script_removes_stale_installer_before_prerequisite_checks() -> None:
    script = (ROOT / "build_release.bat").read_text(encoding="utf-8")

    removal = 'if exist "release\\RangeBot-Setup.exe" del /q "release\\RangeBot-Setup.exe"'
    assert removal in script
    assert script.index(removal) < script.index("call :require_command uv.exe")
    assert "Could not remove the previous RangeBot installer" in script
    assert script.index("Could not remove the previous RangeBot installer") < script.index(
        "call :require_command uv.exe"
    )


def test_engine_package_includes_dynamically_discovered_strategy_modules() -> None:
    specification = (ROOT / "deploy" / "engine.spec").read_text(encoding="utf-8")

    assert 'collect_submodules("rangebot.strategies")' in specification
    assert "hiddenimports=" in specification


def test_frontend_direct_dependencies_are_pinned_and_testing_peers_are_complete() -> None:
    package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    dependencies = {
        **package["dependencies"],
        **package["devDependencies"],
    }

    assert dependencies
    assert all(value != "latest" for value in dependencies.values())
    assert all(
        not value.startswith(("^", "~", ">", "<", "*"))
        for value in dependencies.values()
    )
    assert package["devDependencies"]["@testing-library/dom"] == "10.4.1"
    assert package["devDependencies"]["@testing-library/react"] == "16.3.2"


def test_inno_installer_packages_only_built_application_and_preserves_user_data() -> None:
    installer = (ROOT / "deploy" / "RangeBot.iss").read_text(encoding="utf-8")

    assert "OutputBaseFilename=RangeBot-Setup" in installer
    assert "dist\\bot-engine\\*" in installer
    assert "dist\\RangeBot\\*" in installer
    assert "RangeBot.Engine.exe" in installer
    assert "RangeBot.exe" in installer
    assert "CreateDesktopIcon" in installer
    assert "RemovePersonalData" in installer
    assert "UninstallSilent" in installer
    assert "MB_DEFBUTTON2" in installer
    assert "{localappdata}\\RangeBot" in installer
    assert "CurStepChanged(CurStep: TSetupStep)" in installer
    assert "PrepareToInstall(var NeedsRestart: Boolean)" in installer
    assert "uninstall-service.ps1" in installer
    assert "stop-engine-for-upgrade.ps1" in installer
    assert "Flags: dontcopy" in installer
    assert "ExtractTemporaryFile('stop-engine-for-upgrade.ps1')" in installer
    assert "ExistingDataRoot" in installer
    assert "LoadStringsFromFile" in installer
    assert "CreateInputDirPage" in installer
    assert "DataDirectoryPage" in installer
    assert "ShouldSkipPage" in installer
    assert "UpgradeInstall" in installer
    assert "CurUninstallStepChanged" in installer
    assert "ewWaitUntilTerminated" in installer
    assert "ResultCode <> 0" in installer
    assert "RaiseException(ServiceActionFailureMessage" in installer
    assert "ExpandConstant('{localappdata}\\RangeBot')" in installer
    assert "Parameters := Parameters + ' -RemovePersonalData'" in installer
    assert "DelTree(ExpandConstant('{localappdata}\\RangeBot')" not in installer
    assert "[UninstallRun]" not in installer
    assert "runtime\\" not in installer
    assert "rangebot.db" not in installer
    assert ".env" not in installer


def test_inno_does_not_expand_app_constant_before_wizard_directory_is_ready() -> None:
    installer = (ROOT / "deploy" / "RangeBot.iss").read_text(encoding="utf-8")

    initialize_start = installer.index("procedure InitializeWizard;")
    initialize_end = installer.index("function ShouldSkipPage", initialize_start)
    initialize_body = installer[initialize_start:initialize_end]

    assert "ExpandConstant('{app}" not in initialize_body
    assert "WizardDirValue" in installer


def test_upgrade_script_waits_for_exact_engine_process_before_file_replacement() -> None:
    script = (ROOT / "deploy" / "uninstall-service.ps1").read_text(
        encoding="utf-8"
    )

    assert '$engineExecutable = Join-Path $InstallRoot "engine\\bot-engine.exe"' in script
    assert "Get-CimInstance Win32_Process" in script
    assert ".CommandLine" not in script
    assert "Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop" in script
    assert "Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue" in script
    assert "RangeBot engine process remained after service removal" in script
    assert ".rangebot-data-root" in script
    assert "resolvedInstallRoot.StartsWith" in script
    assert "dataRoot.StartsWith" in script


def test_installer_owned_upgrade_helper_preserves_data_root_and_unlocks_engine() -> None:
    script = (ROOT / "deploy" / "stop-engine-for-upgrade.ps1").read_text(
        encoding="utf-8"
    )

    assert 'Join-Path $InstallRoot "service\\RangeBot.Engine.xml"' in script
    assert "RANGEBOT_HOME" in script
    assert "WriteAllText($DataRootOutputFile" in script
    assert 'Join-Path $InstallRoot "engine\\bot-engine.exe"' in script
    assert "Get-CimInstance Win32_Process" in script
    assert ".CommandLine" not in script
    assert "Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop" in script
    assert "Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue" in script
    assert "RangeBot engine process remained locked during upgrade" in script


def test_build_and_user_documents_describe_no_developer_tool_end_user_flow() -> None:
    build = (ROOT / "BUILD.md").read_text(encoding="utf-8")
    guide = (ROOT / "USER_GUIDE.md").read_text(encoding="utf-8")

    assert "release\\RangeBot-Setup.exe" in build
    assert "No Python" in guide
    assert "http://127.0.0.1:8765/app/" in guide
    assert "DPAPI" in guide
    assert "RESTORE RANGEBOT" not in guide
    assert "%LOCALAPPDATA%\\RangeBot" in build + guide
