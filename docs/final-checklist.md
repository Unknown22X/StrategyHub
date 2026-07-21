# RangeBot final end-to-end checklist

This checklist covers the external Windows, Gate.io, and packaging checks that cannot be replaced by unit tests. Never use a key with withdrawal permission and never use production funds merely to prove the software starts.

## 1. Build and installer

- Run `build_release.bat` on 64-bit Windows with `uv`, Node.js/npm, and Inno Setup 6 installed.
- Confirm the script stops on any backend test, frontend test, typecheck, Vite, PyInstaller, WinSW download, or Inno Setup failure.
- Confirm the exact output exists: `release\RangeBot-Setup.exe`.
- Inspect the installer contents and verify they exclude developer databases, logs, backups, credentials, `.env`, source files, and runtime state.
- Install on a clean Windows account with spaces and Arabic characters in the username/path.
- Confirm the end user needs no Python, Node.js, database server, Git, editor, terminal, or dependency installation.

## 2. Service and launcher

- Confirm `RangeBotEngine` is installed for automatic start, has no visible console, and restarts after a crash.
- Confirm the first installation configures the service under the selected Windows account and DPAPI credential storage works under that identity.
- Launch `RangeBot.exe`; confirm it checks health, starts or restarts the service, waits for initialization, and opens `http://127.0.0.1:8765/app/`.
- Close the browser and disconnect RDP; confirm the service, active strategy, reconciliation, and position protection continue.
- Attempt a duplicate engine process; confirm it exits while the owner engine remains healthy.
- Restart Windows and confirm persisted settings, strategies, Emergency Stop, and reconciliation state are restored safely.

## 3. Arabic React interface

- Verify RTL layout, keyboard order, focus indicators, dialogs, tables, cards, and mixed Arabic/Latin financial values at 375, 768, 1024, and 1440 pixel widths.
- Confirm all displayed numbers, prices, percentages, dates, durations, badges, and step labels use English Latin digits (`0-9`) with no Arabic-Indic digits.
- Confirm loading, unavailable, stale, reconnecting, historical, and error states never display fabricated fallback values.
- Confirm the persistent status bar clearly distinguishes Live, Testnet, and Paper and shows engine, REST, WebSocket, private-stream, freshness, synchronization, strategy, and Emergency Stop states where supported.
- Confirm the primary sidebar has distinct Home, Strategies, Opportunities, Backtesting, Trading, and Performance destinations rather than duplicate dashboard links.
- Create a reusable Strategy Template without choosing a coin or environment; confirm its schema-driven fields, execution defaults, DCA capability message, risk defaults, and revision are visible.
- Add at least two coin setups to one template and confirm each shows its own symbol, current price, price timestamp, freshness state, pinned template revision, status, and review link.
- Edit the template and confirm existing coin setups remain pinned until the operator explicitly rebases them.
- Edit one coin setup and confirm inherited values, coin-specific overrides, effective values, reset-to-template behavior, and a new setup revision are clear.
- Confirm used templates and setups offer archive rather than destructive deletion, while an unused draft can be deleted.
- Confirm Opportunities shows current Gate.io market price and timestamp, qualifying factors, warnings, expiry, and review/approve/reject/ignore/convert states without implying a historical result.
- Confirm Backtesting is a separate destination, selects a saved coin setup, identifies the exact setup revision, and never mixes simulated P&L into account Performance.
- Confirm Trading shows immutable Bot Deployment snapshots and offers only valid start, monitor, pause, and stop actions for each lifecycle state.
- Confirm manual Live trading always displays an unmistakable real-funds warning.

## 4. Paper acceptance

- Create and run each supported strategy type through the template → coin setup → backtest → approval → deployment workflow in Paper and Monitoring modes.
- Verify Range compatibility, closed-candle Trend behavior, prior-channel Breakout behavior, decision explanations, and run history.
- Run a setup-bound backtest and confirm its stored request includes both setup ID and setup revision.
- Confirm a normal approval is rejected until the current setup revision has a Promising result.
- Approve the current revision for Paper, create a deployment, and confirm the runtime remains stopped until the user explicitly starts or monitors it.
- Edit the setup after approval and confirm the previous approval becomes stale, deployment creation is blocked, and a new backtest plus approval are required.
- Confirm an existing deployment snapshot does not change when its template or setup later receives a new revision.
- Confirm Market entry and exit defaults are explicit. Where Limit is supported, verify TIF, expiry/cancellation, partial-fill behavior, fallback, and non-fill warning text.
- Confirm DCA controls are enabled only for a strategy with a real multi-entry implementation and appear unsupported/read-only elsewhere.
- Exercise centralized manual and automatic Market/Limit paths, pending-order fills/expiry, ownership, fees, cooldown, daily loss, losing-trade, and automatic-fill limits.
- Confirm Emergency Stop blocks new entries, cancels pending entries, keeps protection/reconciliation active, and persists after restart.

## 5. Gate.io Testnet acceptance

- Save Testnet credentials with trading permissions only and verify masked status, replacement, read-only test, removal, and persistence after service restart.
- Reconcile balance, One-way mode, margin mode, leverage, positions, open orders, TP, and SL.
- Verify public WebSocket reconnect, heartbeat timeout, resubscription, sequence-gap REST recovery, candle backfill, duplicate rejection, and the 10-second stale-data block.
- Verify private account stream behavior when implemented; until then mark it unavailable rather than fresh.
- Run Opportunities against current Gate.io USDT perpetual contracts and confirm every converted setup preserves exchange, market, quote currency, observed price, observation time, freshness, and source-opportunity link.
- Approve one current setup revision specifically for Testnet, create its deployment snapshot, and confirm Paper or Live approval cannot substitute for Testnet approval.
- Change the setup after Testnet approval and confirm the stale approval cannot authorize another deployment.
- Submit only controlled Testnet orders through the central Order Manager and verify persistent request identity, origin ownership, risk blocks, reconciliation after timeout, and protection restoration.

## 6. Backups and logs

- Create, list, restore, and delete backups through the React operations drawer.
- Confirm the newest ten backup files remain under `%LOCALAPPDATA%\RangeBot\backup`.
- Corrupt a copied backup and confirm validation rejects it before strategy or Emergency Stop state changes.
- Restore a valid controlled backup; confirm a pre-restore safety backup is created, strategies stop, migrations run, reconciliation occurs, and Emergency Stop remains active.
- Export support logs and inspect the ZIP. Confirm credentials, databases, backups, private keys, authentication headers, and sensitive values are absent or redacted.

## 7. Live readiness

- Confirm Live is selected by default and persists across engine and Windows restarts.
- Confirm there is no `LIVE` phrase, arming screen, unlock endpoint, restart relock, or UI-close lock.
- Confirm missing credentials, disconnection, stale data, Emergency Stop, risk limits, position/order conflicts, insufficient balance, contract restrictions, reconciliation failure, protection failure, spread, and liquidity still block entry.
- Confirm Gate.io remains the source of truth and no frontend code submits an exchange order directly.
- Real-funds execution is an operator decision and is not required merely to verify startup, persistence, or the installer.

## 8. Uninstall and update

- Upgrade over an existing installation; confirm the service refreshes without requesting its password again and personal data survives.
- Uninstall and choose **keep data**; confirm `%LOCALAPPDATA%\RangeBot` remains.
- Reinstall and confirm settings/history are restored.
- Uninstall again and explicitly choose **remove all data**; confirm the personal-data directory is deleted only after that choice.

Record exact commands, Windows version, screenshots, Gate environment, results, and known limitations. Do not mark any item VERIFIED without the corresponding evidence.
