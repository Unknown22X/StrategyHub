# StrategyHub Paper Demo Status

Last updated: 2026-07-21 UTC

## Current progress

The smallest reliable Paper demo is prepared and running on a completely separate data root. The existing profile was not reset, migrated, renamed, or overwritten.

The dedicated demo engine uses port `8876`, unauthenticated Gate.io public market data, and no private exchange adapter. It reports the required state:

- `configured_environment = paper`
- `requested_environment = paper`
- `active_engine_environment = paper`
- `exchange_adapter_environment = null`
- `transition_state = ready`
- `activated = true`
- `credential_profile = null`
- `private_websocket_environment = null`

Paper public price data uses Gate.io's public Live market feed by design. This does not use Live Credentials, private Account state, Live Orders, real transactions, or real funds.

## Root causes fixed

### Old profile could return during launcher fallback

The installed Windows service had an explicit `RANGEBOT_HOME`, but the packaged launcher's detached fallback previously inherited no data-root override. If service recovery failed, the fallback resolved the normal `%LOCALAPPDATA%\RangeBot` profile and could reopen the preserved Live state.

Fix commit: `48968edde45bd256e80950105ba7de3fdf1b65d3`

The fallback now reads the installed service XML and uses its exact `RANGEBOT_HOME`. If an installed XML exists but the root is missing or invalid, fallback startup is refused instead of opening the default profile.

### `context_unavailable:AttributeError` during Strategy Running

`StrategyRegistry.get()` returns `StrategyTypeMetadata` directly, but `StrategyRuntimeRunner` incorrectly accessed `descriptor.metadata.evaluation_cadence`. The first evaluation waited for candles with a normal `LookupError`; once candles arrived, the invalid nested attribute produced `context_unavailable:AttributeError`.

Fix commit: `ec70b3b7f9445f6bd86845b62b07d391a863bc31`

The rebuilt packaged engine now records normal `warming_up/history` decisions. A fresh Start/Run/Stop cycle produced no new `context_unavailable:*` decisions.

### Previous `market_data_unavailable`

The failure is not reproducible in the prepared profile. Current checks succeeded for:

- BTC_USDT contract lookup;
- fresh BTC_USDT price from `gate_websocket`;
- a real Gate.io historical request containing 672 completed 15-minute candles;
- a persisted completed Backtest.

The earlier failure was therefore most likely transient public Gate.io/network/DNS availability or the previous packaged/profile state. It is not currently an application-logic blocker. Public network access can still fail during a recording, so use the prepared result rather than starting a new Backtest live.

## Preserved existing data

Original profile, treated as read-only during this work:

`C:\Users\JORY\AppData\Local\RangeBot`

Verified backup:

`C:\Users\JORY\AppData\Local\RangeBot-Live-Preserved-20260721T1711Z`

Both copies contained 22 files and 5,727,168 bytes when verified. The original and backup database SHA-256 values matched:

`a9907a76ba00e0c3d14c619511d3b168565eef73998bd79cfadccffac8323a64`

The original database hash and modification time were checked again after launching and exercising the clean Paper profile and remained unchanged.

An older separate demo root also exists and was not deleted or reused:

`C:\Users\JORY\AppData\Local\StrategyHub-Demo`

## Clean Paper demo root

`C:\Users\JORY\AppData\Local\StrategyHub-Paper-Demo-20260721\RangeBot`

The root has its own database, runtime files, logs, backup directory, and empty Credential directory. It contains no copied Live database, no API Credentials, and no unmanaged exchange state.

Prepared safe data in this root:

- Paper Account initialized with 1,000 USDT;
- one completed Paper Order verification trade, now closed;
- no open Position;
- no pending Paper Order;
- Emergency Stop inactive;
- one stopped Strategy: `BTC Paper Range Demo`;
- five fresh Opportunities from a real public scan;
- one completed real-data Backtest.

## Exact launch instructions

### Current machine — shortest route

Double-click:

`D:\codes\projects\RangeBot\demo\StrategyHub-Paper-Demo.cmd`

Or run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\codes\projects\RangeBot\demo\Start-StrategyHub-Paper-Demo.ps1"
```

The script:

1. uses only the dedicated data root;
2. launches the rebuilt packaged engine on `127.0.0.1:8876`;
3. enables public market WebSocket data only;
4. validates every required Paper runtime field;
5. opens `http://127.0.0.1:8876/app/`.

To stop only the dedicated demo engine:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\codes\projects\RangeBot\demo\Stop-StrategyHub-Paper-Demo.ps1"
```

Stopping the demo preserves its prepared data. It does not stop, edit, or migrate the normal installed `RangeBotEngine` service.

### Rebuilt installer

The rebuilt installer includes a separate **StrategyHub Paper Demo** Start-menu shortcut and optional Desktop shortcut. The normal RangeBot shortcut remains separate and retains its normal profile behavior.

## Verified demo features

### Launch and isolation

- Packaged engine launches from a fresh/separate root.
- Exact Paper/ready/activated/no-adapter/no-Credential state verified.
- Preserved database hash and modification time unchanged.

### Public market data

- BTC_USDT appears in the contract picker API.
- BTC_USDT price was fresh from `gate_websocket`.
- Price response included source, timestamp, environment policy, and freshness state.

### Manual Paper Order

Verified end to end using a small Market Long:

- Preview succeeds;
- Quantity is positive;
- Margin and Leverage are shown;
- estimated fee is shown;
- Take Profit and Stop Loss are calculated;
- `uses_real_funds = false`;
- submission is accepted by Paper only;
- Position is created and marked managed;
- TP and SL protection state is `protected`;
- Position closes successfully;
- final Position quantity is zero.

### Strategy

Prepared Instance:

- Name: `BTC Paper Range Demo`
- Symbol: `BTC_USDT`
- Environment: Paper
- Instance ID: `572919a7-5920-42ac-a5e5-11a5815d7b9c`
- Final state: `stopped`

Verified:

- direct Paper start without Backtesting;
- `never_backtested` appears as a warning, not a blocker;
- Running state;
- immutable Run configuration snapshot;
- background evaluation after the AttributeError fix;
- Stop returns the Strategy to stopped.

The evaluator currently reports `warming_up/history` until enough live candles accumulate. This is honest and safe; it is not an error and no ownership is fabricated.

### Opportunities

A real public scan completed:

- Scan ID: `f2aa200d-cd0f-44ff-a1ba-5181f34db9a8`
- 5 symbols scanned;
- 5 Opportunities stored;
- 0 scan failures;
- BTC_USDT Opportunity price state: fresh.

The Opportunities screen can demonstrate Review, Shortlist, Ignore/Undo, and compatible Strategy selection. Do not say the candidate is an active trade signal when `eligible_now` is false.

### Prepared Backtest

Backtest ID:

`4c68447c-450c-490a-8f3e-cb7b7c3346ad`

Verified facts:

- BTC_USDT;
- Range Strategy;
- 15-minute timeframe;
- 2026-07-14 through 2026-07-21 UTC;
- 672 real historical candles;
- completed and persisted;
- zero qualifying Trades;
- start/end balance 1,000 USDT;
- assessment `insufficient_data`.

This result is intentionally honest and not a performance claim. During the demo, say that real data loaded successfully but the configured rules produced no qualifying entries in that short window.

### Risk Management and Emergency Stop

Verified:

- all three explicit global Limit states load;
- Paper risk snapshot loads;
- Emergency Stop activates only with `EMERGENCY STOP`;
- Resume succeeds only with `RESUME`;
- final Emergency Stop state is inactive.

## Features that still fail or remain limited

- The prepared Backtest has zero Trades and is not suitable for claiming Strategy performance. It is suitable for demonstrating real-data execution, metrics, warnings, and honest insufficient-data handling.
- The Strategy begins in `warming_up/history` because a fresh live process has limited candle history. Use Running state and recent activity; do not promise an immediate Position.
- A new Backtest or scan still depends on public internet/Gate.io availability. Use the prepared records during recording.
- The attempted non-elevated service-root change was blocked by Windows Program Files permissions before changing the service XML. The dedicated port-8876 launcher avoids UAC and leaves the installed service untouched.
- Creating a Windows COM desktop shortcut directly through the WSL bridge was unreliable. The installer is configured to create the shortcut during a normal elevated install, and the repository `.cmd` launcher is already double-clickable. Interactive installer acceptance remains manual.

## Tests and verification run

Focused source suites:

- Launcher fallback unit suite — 6 passed.
- Strategy runtime fix and lifespan suite — 10 passed.
- Paper Order, Preview, Position, protection, closing, and Order Manager regressions — 40 passed.
- Strategy direct start, runtime, immutable snapshots, lifecycle, and migration regressions — 24 passed.
- Opportunities, Backtesting, Risk Management, environment, and market-data regressions — 27 passed.
- Release assets, deployment assets, Paper-demo assets, and focused Ruff/format checks — 22 passed.
- One attempted regression command referenced two nonexistent filenames and therefore ran zero tests; it was corrected to the actual current test inventory. This was not a code failure.

Prepared packaged demo checks:

- clean root launch and exact runtime state — passed;
- original Live database hash/mtime isolation — passed;
- BTC_USDT contract and fresh price — passed;
- Manual Preview/submit/Position/TP/SL/close — passed;
- direct Strategy start/snapshot/stop — passed;
- rebuilt Strategy evaluator with no new `context_unavailable:*` — passed;
- Opportunities public scan — passed;
- real historical Backtest — passed;
- Risk Management and Emergency Stop/Resume — passed;
- final prepared-state, preserved-profile hash, fresh market, Backtest, Opportunity, and installer-integrity verifier — passed;
- Inno Setup final installer compilation — passed.

## Commits

- `48968edde45bd256e80950105ba7de3fdf1b65d3` — isolate packaged fallback data root.
- `ec70b3b7f9445f6bd86845b62b07d391a863bc31` — fix Strategy runtime registry metadata access.
- `c74b96db9cf15c1f1cdf2dcde8e5fbb71e229a7c` — add the isolated Paper launcher, installer shortcuts, tests, and status handoff.
- `b1296a4c24c463b1a46f4bbb82bb4c3f702ad897` — make optional release documentation nonblocking.
- `0918be7a86e15b7b4f0fd038a745bc52c7b21a4d` — keep the status report outside the installer checksum boundary.

Latest implementation/release commit used to build the installer:

`0918be7a86e15b7b4f0fd038a745bc52c7b21a4d`

The final status-only commit containing these exact artifact details is reported in the final response.

## Installer

The installer was rebuilt because both the packaged engine and launcher safety behavior changed.

Path:

`D:\codes\projects\RangeBot\release\RangeBot-Setup.exe`

Size:

`38,507,906 bytes`

SHA-256:

`aec73df6b0deb798a4bbaaa5aa294a670143db7561fb9009c5a0b4a22131c544`

The installer contains the rebuilt engine, rebuilt launcher, isolated Paper-demo scripts, and separate Start-menu/optional Desktop shortcuts. Installing it still requires normal Windows elevation because the standard Windows service is installed under Program Files.

## Shortest reliable demo route

1. Double-click `demo\StrategyHub-Paper-Demo.cmd`.
2. Point to the `PAPER` badge and explain that no Credentials or real funds are used.
3. Open Manual Trade and choose BTC_USDT.
4. Use Market, Long, Margin 25 USDT, Leverage 2x.
5. Preview and show Quantity, Margin, fee, TP, and SL.
6. Submit the Paper Order.
7. Show the managed Position and protection, then close it.
8. Open `BTC Paper Range Demo`.
9. Show readiness and the honest Never Backtested warning.
10. Start it, show Running and recent `warming_up/history` activity, then stop it.
11. Open Opportunities and Review the BTC_USDT result. Explain that Shortlist does not trade.
12. Open Backtesting and select Backtest `4c68447c-450c-490a-8f3e-cb7b7c3346ad`. Explain that 672 real candles loaded but the short window produced no qualifying Trades.
13. Open Risk Management, show the three Limit toggles and Emergency Stop, but leave Emergency Stop inactive when finished.

## Backup demo route

If public Gate.io data is temporarily unavailable:

1. Launch and show the exact Paper environment state.
2. Open the prepared Strategy and demonstrate readiness, Start, Running, recent activity, and Stop.
3. Show the five stored Opportunities, clearly noting the saved observation time/freshness state.
4. Show the prepared completed Backtest and its honest insufficient-data warning.
5. Show Risk Management and Emergency Stop.
6. Omit creating a new Order if the app correctly marks current price as unavailable or stale.

## Exact next action if work stops early

1. Double-click `D:\codes\projects\RangeBot\demo\StrategyHub-Paper-Demo.cmd`.
2. Confirm the browser opens `http://127.0.0.1:8876/app/` and the badge says `PAPER`.
3. Follow the shortest reliable demo route above.
4. Install `D:\codes\projects\RangeBot\release\RangeBot-Setup.exe` later with Windows elevation if the installer shortcuts are needed; the repository launcher already works without changing the normal service profile.
