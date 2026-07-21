# Building StrategyHub for Windows

## Output

StrategyHub is the public project name. Stable Windows and internal identifiers remain RangeBot during submission finalization.

A successful release build creates:

```text
release\RangeBot-Setup.exe
```

The installer contains the React dashboard, Python engine, `RangeBot.exe` launcher, WinSW service wrapper, migrations, and all runtime dependencies. End users do not install Python, Node.js, PostgreSQL, Git, or developer tools.

## Build-machine requirements

Use 64-bit Windows 10/11 or Windows Server with:

- `uv` on `PATH`
- Node.js `20.19+`, `22.12+`, or `24+`, with `npm` on `PATH`; the Build Week release is verified with Node `v22.22.0`
- Inno Setup 6, including `ISCC.exe`
- Internet access for Python/npm dependencies and the pinned WinSW binary

No Live API credentials are required or permitted during the build.

## Build command

From the repository root, double-click or run:

```bat
build_release.bat
```

The script performs these fail-fast steps:

1. Removes prior `build`, `dist`, `release`, and `frontend\dist` outputs.
2. Runs `uv sync --group dev`.
3. Requires the committed `frontend\package-lock.json` and runs `npm ci`; the build fails rather than resolving a floating dependency tree.
4. Runs frontend type checking, Vitest, and the Vite production build.
5. Runs the complete Python test suite.
6. Generates `deploy\RangeBot.ico` from source.
7. Builds silent PyInstaller onedir packages for the engine and launcher.
8. Downloads pinned WinSW `v2.12.0` and its license when absent.
9. Compiles `deploy\RangeBot.iss` with Inno Setup.
10. Verifies the exact installer output path.

Any failed command stops the build and no completion claim should be made.

## Runtime layout

The installer uses this immutable installation layout:

```text
%ProgramFiles%\RangeBot\
├── engine\
├── launcher\
├── service\
├── licenses\
└── docs\
```

Mutable data is never stored there. It remains under:

```text
%LOCALAPPDATA%\RangeBot\
├── data\rangebot.db
├── config\
├── logs\
├── backup\
└── runtime\
```

## Service installation

The background service runs as the built-in passwordless `NT AUTHORITY\LocalService` identity. The service installer resolves the active Explorer user in the same Windows/RDP session, derives that SID’s profile path, and uses the user’s absolute `%LOCALAPPDATA%\RangeBot` root even when separate administrator credentials were entered at UAC. The Inno value is retained only as a fallback. ACLs grant access to that user, LocalService, SYSTEM, and local administrators. Gate.io credentials are encrypted with Windows DPAPI machine scope (`CRYPTPROTECT_LOCAL_MACHINE`) and remain ciphertext on disk, so the service can recover after restart without storing a Windows password or plaintext secrets.

Upgrades stop, refresh, and restart the existing service without requesting a password. Uninstall stops and removes the service while preserving `%LOCALAPPDATA%\RangeBot` by default.

## Verification before release

On a clean Windows account, verify:

1. `RangeBot-Setup.exe` installs without Python or Node.js present.
2. `RangeBotEngine` starts automatically and has no visible console.
3. `RangeBot.exe` opens `http://127.0.0.1:8765/app/`.
4. Closing the browser and disconnecting RDP do not stop the service.
5. Reboot restores the service, settings, strategy state, and Emergency Stop state.
6. Uninstall keeps `%LOCALAPPDATA%\RangeBot` unless the user explicitly chooses removal.

Record the exact Windows version, commands, screenshots, and results in the final implementation evidence.
