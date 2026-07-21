# StrategyHub Known Limitations

This file is intentionally direct. It lists limitations that remain after the Build Week submission freeze and explains whether they affect the recommended Paper demo.

## 1. Real Gate.io Testnet acceptance is not complete

Automated and mocked tests verify environment isolation, endpoint selection, Credential-profile separation, reconciliation readiness, Preview routing, submission routing, Position/protection lifecycle, and no cross-environment state reuse.

A real Gate.io Futures Testnet Order was not submitted from this environment because no real Testnet Credentials or external manual Gate.io session were available.

**Demo impact:** none. The recommended demo uses Paper.

**Required follow-up:** run the manual Testnet checklist in the project operations documentation using Testnet-only Credentials and confirm no Live request occurs.

## 2. Live was not tested

No Live Credentials were loaded. No Live Order, real transaction, or real funds were used.

Live remains fail-closed behind explicit confirmation, environment matching, Credentials, reconciliation, market freshness, account/risk readiness, balance, Quantity, unmanaged-state, and protection checks.

**Demo impact:** none. Do not enter Live during the recording.

## 3. Public market data requires internet access

Paper does not require private Gate.io Credentials, but the contract catalog and current prices rely on Gate.io public market endpoints and optional public WebSocket updates.

When public data is unavailable, StrategyHub displays unavailable/stale state rather than fabricating a healthy price. Manual symbol entry remains available, but validation or Preview may still need contract rules and a trustworthy reference price.

**Demo impact:** prepare internet access and verify `BTC_USDT` immediately before recording. Use the backup demo route if public data is unavailable.

## 4. Paper is a simulation

Paper fills, PnL, fees, liquidation estimates, Take Profit, Stop Loss, and timing cannot reproduce every aspect of exchange execution, latency, queue position, slippage, funding, or liquidation behavior.

**Demo impact:** explicitly describe the Order and Position as Paper simulation.

## 5. Backtesting is research, not a prediction

Historical results depend on available candles, fees, spread, slippage, execution assumptions, Strategy rules, and contract data. Historical-scanner mode may use the current surviving Gate contract universe when an exact historical listing universe is unavailable; the run displays this warning.

Public-data requests can still fail because of internet outages or Gate.io availability. The application now bounds polling, retries temporary requests, stores a failure stage/code, and supports cancellation, but it cannot guarantee that an external data provider responds.

**Demo impact:** open a prepared completed Backtest result rather than waiting for a network-dependent run during the video.

## 6. Strategy ownership is never guessed

The Strategy operations page displays Positions and Orders only when authoritative ownership attribution exists. Some Paper pending-entry responses do not currently include complete Strategy ownership metadata.

**Demo impact:** the page may correctly show no attributed Order even when another non-attributed Paper action exists. Do not verbally claim ownership that is not shown.

## 7. Public and internal project names differ

The public submission name is **StrategyHub**. For release stability, the Python package, executable, Windows service, installer filename, install folder, database identifiers, and local data folder retain **RangeBot**.

Expected examples:

```text
RangeBot-Setup.exe
RangeBot.exe
RangeBotEngine
%LOCALAPPDATA%\RangeBot
```

**Demo impact:** explain once that StrategyHub is powered by the stable RangeBot engine.

## 8. Some terminology and advanced screens remain mixed-language

The application intentionally keeps recognized trading terms such as Position, Long, Short, Entry, Stop Loss, Take Profit, Leverage, Margin, Market, Limit, DCA, Backtest, Paper, Testnet, Live, PnL, Win Rate, Drawdown, Strategy, Order, Trade, and Timeframe in English.

Some surrounding explanations and older advanced screens remain Arabic or mixed Arabic/English. Full terminology and localization redesign was frozen for the submission.

**Demo impact:** the primary Paper, Strategy, Opportunity, Backtest, and Risk routes are usable, but some advanced labels may remain inconsistent.

## 9. Browser-level visual acceptance is partly manual

Unit, integration, process, frontend component, typecheck, and production build tests cover core behavior. Final installed-app layout, browser console, responsive behavior, and screenshots still require a manual Windows/browser pass.

**Demo impact:** rehearse the exact installed demo route before recording.

## 10. Windows installation and uninstall require final manual confirmation

The release pipeline tests packaging assets and can build the PyInstaller application and Inno Setup installer. Installing with administrator elevation, confirming the Windows service, running the exact Paper demo in the installed build, and uninstalling while preserving user data are manual OS actions.

**Demo impact:** do not claim installed acceptance until those steps are actually completed and recorded.

## 11. One engine instance per configured port

StrategyHub uses a local instance lock to prevent multiple engine processes from controlling the same local runtime. Starting a second development or packaged engine on port `8765` is intentionally blocked.

**Demo impact:** close old development engines and installed launchers before starting the final build.

## 12. Historical data and performance are not profit guarantees

No screenshot, Paper Trade, Strategy statistic, or Backtest should be presented as evidence that the Strategy will make money. The project is an operations and safety tool, not financial advice.

## Build Week safety statement

No Live Credentials, Live Orders, real Gate.io transactions, or real funds were used during Build Week implementation or automated verification.
