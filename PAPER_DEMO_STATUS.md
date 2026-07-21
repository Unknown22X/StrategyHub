# StrategyHub Paper Demo Status

Last updated: 2026-07-21 UTC

## Current progress

- Feature scope is frozen. Work is limited to the smallest reliable Paper demo.
- The installed Windows service is located at `C:\Program Files\RangeBot`.
- The preserved existing profile is `C:\Users\JORY\AppData\Local\RangeBot`.
- A verified non-destructive backup was created at `C:\Users\JORY\AppData\Local\RangeBot-Live-Preserved-20260721T1711Z`.
- Original and backup contain 22 files and 5,727,168 bytes. Their `data\rangebot.db` SHA-256 values match.
- The currently installed service points to `C:\Users\JORY\AppData\Local\StrategyHub-Demo`, but that profile is not clean and will not be reused or deleted.
- The running service currently reports Paper, ready, activated, no exchange adapter, and no Credential Profile.
- Root cause identified: if Windows service recovery fails, the packaged launcher fallback starts without the service-configured `RANGEBOT_HOME`, so it can resolve the old `%LOCALAPPDATA%\RangeBot` profile. A focused code fix is in progress.

## Exact root cause

The installed Windows service has an explicit `RANGEBOT_HOME`, but `src/rangebot/ui/engine_bootstrap.py` previously launched its detached emergency fallback with inherited environment only. When the service could not be started or restarted, that fallback used the normal default `%LOCALAPPDATA%\RangeBot`. This could restore the preserved Live profile even though the service XML pointed at a separate Paper profile.

## Preserved old data root

`C:\Users\JORY\AppData\Local\RangeBot`

Verified backup:

`C:\Users\JORY\AppData\Local\RangeBot-Live-Preserved-20260721T1711Z`

Do not delete, rename, reset, migrate, or overwrite either directory during demo preparation.

## New clean demo data root

Planned and not yet activated:

`C:\Users\JORY\AppData\Local\StrategyHub-Paper-Demo-20260721\RangeBot`

The final path ends in `RangeBot` so it remains compatible with the service installation safety checks while staying completely separate from the preserved profile.

## Current installed runtime state

Verified through `http://127.0.0.1:8765/v1/runtime/environment`:

- `configured_environment = paper`
- `requested_environment = paper`
- `active_engine_environment = paper`
- `exchange_adapter_environment = null`
- `transition_state = ready`
- `activated = true`
- `credential_profile = null`

Paper intentionally uses unauthenticated public Live market data for prices; this does not use Live Credentials or submit Live Orders.

## Exact launch instructions

Current temporary route before the clean profile is activated:

1. Ensure the `RangeBotEngine` Windows service is running.
2. Launch RangeBot from the Start menu or desktop shortcut.
3. Open `http://127.0.0.1:8765/app/` if the browser does not open automatically.
4. Confirm the environment badge says `PAPER` before any demo action.

Final launch instructions will be updated after the clean profile and rebuilt launcher are verified.

## Features passed

- Installed engine `/health` responds.
- Installed runtime reports the required Paper/ready/activated/no-adapter/no-Credential state.
- The existing packaged Paper engine smoke test passed previously with a fresh isolated database.
- Launcher fallback unit suite passes after the focused root-isolation fix: 6 tests passed.

## Features still to verify on the new clean profile

- No old Strategies, Orders, Positions, Credentials, or unmanaged state.
- BTC_USDT public price and freshness.
- Manual Order Preview.
- Paper Order submission and Position creation.
- Take Profit and Stop Loss.
- Position close.
- Direct Paper Strategy start, Running state, and stop.
- Opportunities.
- Prepared completed Backtest result from real historical data if available.
- Risk Management and Emergency Stop.
- `context_unavailable:AttributeError` impact on Paper.
- Backtest `market_data_unavailable` root cause.

## Tests run

- `uv run pytest tests/unit/test_ui_engine_bootstrap.py -q` — 6 passed.
- Installed `/health` and `/v1/runtime/environment` — healthy and Paper-ready.
- Live-profile backup verification — source and backup metadata and database SHA-256 match.

## Latest commit hash

Before the current focused fix: `c92a7e030a740e39c2674bead39a11b9bebc028c`

The fallback isolation fix is not committed yet.

## Installer

- Rebuilt for this overnight task: no, not yet.
- Current installer: `D:\codes\projects\RangeBot\release\RangeBot-Setup.exe`
- Previously verified size: 38,424,924 bytes.
- Previously verified SHA-256: `4b2329154ad325c0836c8057496d919e984ca9be783745a96d2a74c1b164127c`.

The installer will be rebuilt only because the launcher fallback fix affects installed-profile safety.

## Shortest reliable demo route

Pending final clean-profile verification. Intended route:

1. Launch in Paper.
2. Preview and submit one small BTC_USDT Market Long Paper Order.
3. Show Position, Take Profit, Stop Loss, and close it.
4. Open one prepared Paper Strategy, start it directly, show Running, then stop it.
5. Show Opportunities.
6. Open one prepared completed Backtest result.
7. Show Risk Management and Emergency Stop.

## Backup demo route

If public market data or Backtesting is unavailable:

1. Launch in Paper and show the authoritative environment state.
2. Use a previously prepared valid public price snapshot only if the app still marks it accurately as stale; do not call it live.
3. Demonstrate Strategy readiness/start/stop, Opportunities, and Risk Management.
4. Omit the live Backtest run and show a previously completed real-data result if available.

## Exact next action if work stops early

1. Finish and commit the launcher fallback `RANGEBOT_HOME` isolation fix.
2. Create `C:\Users\JORY\AppData\Local\StrategyHub-Paper-Demo-20260721\RangeBot` without copying any old database or Credentials.
3. Point the installed service XML and log path at that root, restart the service, and verify the required runtime fields.
4. Run the focused Paper demo flow against the clean profile.
5. Rebuild and smoke-test the installer because the launcher binary changed.
