# StrategyHub User Guide

StrategyHub is the public project name. The packaged executable, Windows service, data folder, and some internal messages still use the stable **RangeBot** name.

## Install on Windows

1. Run `RangeBot-Setup.exe` as an administrator.
2. Choose the installation language and application destination.
3. Choose where StrategyHub should keep its database, logs, and backups. The default is `%LOCALAPPDATA%\RangeBot`.
4. Optionally create a desktop shortcut.
5. Finish the installer and launch the application.

The background engine runs as Windows `LocalService`; the installer does not ask for a Windows account password. **No Python, Node.js, PostgreSQL, Git, or `.env` file is required for end users.**

## Open StrategyHub

Open **RangeBot** from the Start menu or desktop. The launcher verifies the localhost engine, safely starts or restarts the installed service when needed, and opens:

```text
http://127.0.0.1:8765/app/
```

The API and dashboard bind to localhost only. Closing the browser does not stop the service or an active Strategy Run.

## Start safely in Paper

A fresh engine starts in **Paper** unless an explicit startup configuration says otherwise.

Paper:

- does not require Gate.io API Credentials;
- uses local simulated Orders, Positions, PnL, protection, and account state;
- may read public Gate.io market data for contract options and prices;
- never sends a private account request or real Order to Gate.io.

Confirm the persistent environment badge says **PAPER** before the demo. The active badge comes from the authoritative running engine state, not only a saved preference.

## Paper manual Order flow

1. Open **Manual Trade**.
2. Confirm the drawer says **PAPER**.
3. Search for `BTC_USDT`, or type it manually.
4. Choose **Market** and **Long**.
5. Choose a size mode, a small Margin, and conservative Leverage such as `1x`.
6. Select **Preview**.
7. Review Quantity, Margin, notional, fees, estimated liquidation, Take Profit, Stop Loss, and validation messages.
8. Select **Submit** only when the preview says it can submit.
9. Open the Position card to view Entry, Quantity, protection, and PnL.
10. Use **Close Position** to finish the Paper Trade.

A size that rounds to zero or is below the Gate contract minimum returns a structured validation message. StrategyHub never rounds the requested Quantity upward merely to make it valid.

## Strategy model

### Strategy Template

An immutable built-in Strategy definition registered by the engine. Built-in names remain in English.

### Strategy Preset

A reusable editable set of Strategy configuration values. Existing persisted template records from older versions are preserved as Presets.

### Strategy Instance

A user-created Strategy with its own name, symbol, timeframe, environment, configuration, status, performance, and history.

A Strategy Instance can be:

- started or stopped;
- placed in Monitoring or Paused state;
- pinned to the sidebar;
- duplicated;
- archived and restored;
- permanently deleted only when it has no runtime, trading, Backtest, deployment, ownership, or audit history.

Used Strategies are archived rather than destroyed so history and ownership remain trustworthy.

## Direct Paper Strategy start

Backtesting is optional.

1. Open **Strategies** or an existing Strategy Instance.
2. Confirm its environment is Paper.
3. Review the readiness panel.
4. A **Never Backtested** warning is informational; it is not a Paper blocker.
5. Select **Start**.
6. StrategyHub creates an immutable Strategy Run snapshot and changes the Instance to Running.
7. View the symbol, live price state, PnL, Win Rate, Drawdown, Position, Orders, health, and recent activity where authoritative data exists.
8. Select **Stop** when finished.

Changing the Template, Preset, or Instance later does not mutate the configuration snapshot of an already-running or historical Run.

## Backtesting

Backtesting is a research tool, not a requirement for Paper.

The wizard includes **Beginner — realistic and conservative**, which applies conservative defaults while keeping advanced execution assumptions collapsed. Step 5 is explicitly the final step. The hypothesis and Setup Review link are optional.

Backtests have bounded polling, cancellation, sanitized failure codes, visible failure stage, network timeouts, and retry/backoff for temporary public-data failures. A historical-scanner run may use the current surviving Gate contract universe when an exact historical listing universe is unavailable; the result displays that limitation.

## Opportunities

An Opportunity is a scanner research lead. It is not an Order and does not start trading.

- **Review details** opens the qualifying factors, warnings, source Strategy, price time, and expiry.
- **Shortlist** saves interest only.
- **Ignore** hides the item from the active queue and supports Undo.
- **Create Coin Setup** creates configuration for the matching scanner Strategy.
- **Create Strategy Instance for this coin** lets the user choose another compatible built-in Strategy, including Fixed Price Ladder. The new Paper Instance is stopped and does not claim that the selected Strategy discovered the coin.

Unsupported scanner Strategies remain visible but disabled with an explanation.

## Risk Management

The global daily policy has explicit toggles for:

- daily equity-loss limit;
- daily losing-Trades limit;
- daily automatic-entry limit.

Disabled limits are stored as disabled, not simulated with huge numbers. Paper and Testnet can disable optional limits normally. Live requires explicit real-funds confirmation before disabling an important policy limit.

These optional policy toggles never disable fundamental safety checks such as environment matching, valid Credentials, fresh account data, sufficient balance, valid Quantity, unmanaged-state protection, or protection-order validation.

The UI distinguishes:

- limit disabled;
- enabled and not reached;
- actually reached;
- risk data unavailable;
- synchronization incomplete.

## Emergency Stop

Emergency Stop blocks new entries and cancels pending entry Orders while allowing reconciliation and protection management to continue. It persists after restart and requires deliberate manual resume.

## Paper, Testnet, and Live

### Paper

Local simulation. No private Gate Credentials and no real funds.

### Testnet

Gate.io Futures Testnet. It requires the Testnet Credential profile, authoritative Testnet engine/adapter mode, fresh reconciliation, account readiness, market data, risk readiness, and protection readiness.

### Live

Real Gate.io funds. Live requires explicit real-funds confirmation and all mandatory safety checks. The application never removes the adapter-mode mismatch blocker.

The Credential drawer selector chooses which Credential profile is edited. It does not silently change the active trading environment.

## Credentials

Credentials are optional for Paper. For Testnet or Live:

1. Open **Settings → Gate.io Connection**.
2. Choose the Credential profile to edit.
3. Enter the API key and secret.
4. Save and test the profile.
5. Do not grant withdrawal permission.

Stored Credentials are protected using Windows DPAPI. The full secret is never returned to the browser or included in support exports.

## Backups and support logs

Backups are stored under `%LOCALAPPDATA%\RangeBot\backup`. Restore validates the selected backup, creates a safety backup, restores and migrates the database, invalidates stale exchange readiness, and leaves Emergency Stop active for review.

Support exports exclude databases, backups, Credentials, private keys, and sensitive filenames, and redact common authentication values.

## Uninstall

Uninstall removes the application and Windows service. The uninstaller asks whether to remove personal data. **No** is the safe default and preserves `%LOCALAPPDATA%\RangeBot`.

## Troubleshooting

- **Engine unavailable:** reopen the installed launcher and allow the service health check to complete.
- **Dashboard assets unavailable:** reinstall from a complete `RangeBot-Setup.exe` release.
- **Paper contract options unavailable:** verify internet access; manual symbol entry still works and is validated on Preview or save.
- **Price unavailable or stale:** wait for public market refresh. Do not present stale data as healthy.
- **Order blocked:** follow the main reason and next action. Do not work around environment, Quantity, balance, protection, or freshness blockers.
- **Backtest failed:** open its stored failure stage and sanitized reason; retry temporary public-data failures rather than starting an infinite poll.
- **Testnet or Live not ready:** confirm the authoritative environment badge, correct Credential profile, reconciliation, and account readiness.

## Safety notice

Trading derivatives can result in rapid losses. Backtests and Paper results do not guarantee future performance. Use Paper first, then Testnet. Never test a release with Live funds.
