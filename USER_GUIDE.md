# RangeBot User Guide

## Install

1. Double-click `RangeBot-Setup.exe`.
2. Choose the installation language and destination.
3. On the first installation, enter the Windows account credentials requested for the background engine service.
4. Optionally create a desktop shortcut.
5. Finish the wizard. RangeBot opens automatically unless that option is cleared.

No Python, Node.js, PostgreSQL, terminal, or `.env` file is required.

## Open RangeBot

Open **RangeBot** from the Start menu or desktop. `RangeBot.exe` checks the localhost engine, starts or restarts the background service when needed, waits for initialization, and opens:

```text
http://127.0.0.1:8765/app/
```

The control panel is localhost-only. Closing the browser does not stop the engine or active strategy.

## First setup

1. Open **Settings → Gate.io Connection**.
2. Select Live or Testnet credentials.
3. Enter the API key and API secret.
4. Save, then use **Test Credentials**.
5. Do not grant withdrawal permission to the API key.

Credentials are protected by Windows DPAPI and the full secret is never returned to the browser.

Live is the default environment. There is no `LIVE` phrase, arming page, or restart unlock. Real entries are still blocked when credentials, reconciliation, market freshness, balance, contract rules, risk limits, protection, or Emergency Stop are unsafe.

## Add and run a strategy

1. Select **Add Strategy**.
2. Choose a dynamically registered strategy type.
3. Enter a name, contract, timeframe, direction, and validated settings.
4. Save the instance.
5. Choose **Start** for automatic control or **Monitoring** for analysis only.

Only one strategy may control automatic entries. Other strategies may monitor. RangeBot never silently replaces the active controller.

## Manual futures trading

Open **Manual Trade** and choose:

- Market or Limit
- Long or Short
- Gate.io USDT perpetual contract
- Quantity, margin, or balance percentage
- Leverage within contract limits
- Supported time in force

Review Last Price, Mark Price, bid, ask, quantity, notional, fee, liquidation estimate, balance, and validation messages before submission. Live submission is clearly marked as using real funds. Manual orders cannot bypass Emergency Stop or account risk limits.

## Emergency Stop

Emergency Stop is available throughout the control panel. When active, it blocks new entries and cancels pending entry orders while reconciliation and position protection continue. It persists after restart and requires a deliberate manual resume after safety checks pass.

## Backups

The Backups page can:

- Create a safe SQLite backup
- List existing backups
- Restore a selected backup
- Delete a backup

Restore requires the exact confirmation text shown by the UI. RangeBot validates the backup before changing state, stops running/monitoring strategies, creates a pre-restore safety backup, restores and migrates the database, reconciles the configured Gate.io mode, and leaves Emergency Stop active for manual review.

The newest ten backups are retained under `%LOCALAPPDATA%\RangeBot\backup`.

## Export support logs

Use **Export Logs** to download a support ZIP. The export excludes databases, backups, credentials, private keys, and sensitive filenames, and redacts common authentication headers and values.

## Data location

Mutable application data is stored under:

```text
%LOCALAPPDATA%\RangeBot\
```

Normal application upgrades preserve this directory.

## Uninstall

Windows uninstall removes the application and background service. The uninstaller asks whether to keep settings and trading history or remove all personal RangeBot data. **No** is the safe default and keeps `%LOCALAPPDATA%\RangeBot`.

## Troubleshooting

- **Engine unavailable:** reopen RangeBot. The launcher attempts to start or restart the service.
- **Dashboard assets unavailable:** reinstall using a complete `RangeBot-Setup.exe` build.
- **Order blocked:** read the exact validation reason; do not work around stale data, reconciliation, risk, or protection failures.
- **Gate.io disconnected:** allow reconciliation to complete before attempting another entry.
- **Service will not start:** open Windows Services and confirm `RangeBot Engine` runs under the account chosen during setup.
