@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "ROOT=%CD%"
set "WIN_SW_VERSION=2.12.0"
set "UV_PROJECT_ENVIRONMENT=.venv-release"
set "TEMP=%ROOT%\.release-tmp"
set "TMP=%TEMP%"

if not exist "%TEMP%" mkdir "%TEMP%"

if exist "release\RangeBot-Setup.exe" del /q "release\RangeBot-Setup.exe"
if exist "release\RangeBot-Setup.exe" (
    echo ERROR: Could not remove the previous RangeBot installer. Close it and try again.
    goto :failed
)

call :require_command uv.exe || exit /b 1
call :require_command node.exe || exit /b 1
call :require_command npm.cmd || exit /b 1
node -e "const [major, minor] = process.versions.node.split('.').map(Number); const ok = (major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major >= 24; if (ok === false) process.exit(1);"
if errorlevel 1 (
    echo ERROR: Node.js 20.19+, 22.12+, or 24+ is required to build the frontend.
    exit /b 1
)

set "ISCC="
where ISCC.exe >nul 2>nul && set "ISCC=ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo ERROR: Inno Setup 6 command-line compiler ISCC.exe was not found.
    echo Install Inno Setup 6, then run build_release.bat again.
    exit /b 1
)

for %%D in (build dist release frontend\dist) do (
    if exist "%%D" rmdir /s /q "%%D"
)
if exist "deploy\RangeBot.ico" del /q "deploy\RangeBot.ico"
if not exist "vendor" mkdir "vendor"

call uv sync --group dev
if errorlevel 1 goto :failed

pushd frontend
if not exist package-lock.json (
    echo ERROR: frontend\package-lock.json is required for a reproducible release build.
    popd
    goto :failed
)
call npm ci
if errorlevel 1 (
    popd
    goto :failed
)
call npm run typecheck
if errorlevel 1 (
    popd
    goto :failed
)
call npm test
if errorlevel 1 (
    popd
    goto :failed
)
call npm run build
if errorlevel 1 (
    popd
    goto :failed
)
popd

if not exist "frontend\dist\index.html" (
    echo ERROR: The React production build did not produce frontend\dist\index.html.
    goto :failed
)

call uv run pytest -q
if errorlevel 1 goto :failed

call uv run python deploy\generate_icon.py
if errorlevel 1 goto :failed
if not exist "deploy\RangeBot.ico" (
    echo ERROR: RangeBot.ico was not generated.
    goto :failed
)

call uv run pyinstaller --noconfirm --clean deploy\engine.spec
if errorlevel 1 goto :failed
call uv run pyinstaller --noconfirm --clean deploy\ui.spec
if errorlevel 1 goto :failed

if not exist "dist\bot-engine\bot-engine.exe" (
    echo ERROR: The packaged engine executable is missing.
    goto :failed
)
if not exist "dist\RangeBot\RangeBot.exe" (
    echo ERROR: The packaged RangeBot launcher is missing.
    goto :failed
)

if not exist "vendor\WinSW-x64.exe" (
    echo Downloading pinned WinSW v%WIN_SW_VERSION%...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/winsw/winsw/releases/download/v%WIN_SW_VERSION%/WinSW-x64.exe' -OutFile '%ROOT%\vendor\WinSW-x64.exe'"
    if errorlevel 1 goto :failed
)
if not exist "vendor\WinSW-LICENSE.txt" (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/winsw/winsw/v%WIN_SW_VERSION%/LICENSE.txt' -OutFile '%ROOT%\vendor\WinSW-LICENSE.txt'"
    if errorlevel 1 goto :failed
)

"%ISCC%" deploy\RangeBot.iss
if errorlevel 1 goto :failed

if not exist "release\RangeBot-Setup.exe" (
    echo ERROR: Inno Setup finished without producing release\RangeBot-Setup.exe.
    goto :failed
)

echo.
echo VERIFIED BUILD OUTPUT: %ROOT%\release\RangeBot-Setup.exe
exit /b 0

:require_command
where %~1 >nul 2>nul
if errorlevel 1 (
    echo ERROR: Required developer command %~1 was not found on PATH.
    exit /b 1
)
exit /b 0

:failed
echo.
echo ERROR: RangeBot release build failed. No completion claim should be made.
exit /b 1
