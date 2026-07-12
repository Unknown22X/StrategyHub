# RangeBot

## 1. Product Summary

RangeBot is a private cryptocurrency futures trading application for Gate.io USDT-settled perpetual contracts.

It runs continuously on a Windows VPS and consists of:

* A Python trading engine running as a WinSW Windows Service.
* A separate PySide6/Qt Arabic RTL desktop control application.
* Gate.io API v4 integration using REST and WebSockets.
* FastAPI bound only to `127.0.0.1` for communication between the UI and engine.
* A local PostgreSQL database for settings, state, orders, positions, cooldowns, profiles, logs, and risk counters.

The engine must continue operating when the desktop UI is closed, Remote Desktop disconnects, or the user’s personal computer is turned off.

RangeBot does not promise profitability. Its purpose is to execute user-defined trading rules consistently while enforcing account, execution, and operational safeguards.

## 2. User Problem and Target User

### User problem

The user needs to:

* Monitor several Gate.io perpetual contracts.
* Understand whether each contract meets a range-based Long or Short condition.
* Allow one selected contract to trade automatically.
* Open manual Long or Short positions.
* Keep the bot running continuously on a VPS.
* Receive clear Arabic explanations of actions, rejected actions, and safety blocks.
* Reduce operational errors involving duplicate orders, stale data, missing protection, restarts, and conflicting exchange state.

### Target user

Version one is designed for a single private user who:

* Controls the Windows VPS.
* Has a Gate.io futures account.
* Understands the risks of futures, Cross margin, leverage, liquidation, fees, and disabling protection.
* Uses the Arabic desktop interface through Remote Desktop.

## 3. Goals

* Execute the confirmed range-and-proximity strategy consistently.
* Support Paper Trading, Gate.io Testnet, and Live Trading.
* Keep the trading engine independent from the control UI.
* Reconcile real Gate.io state before allowing entries.
* Enforce one open position or pending entry state per account.
* Provide configurable Take Profit, Stop Loss, leverage, sizing, and cooldown controls.
* Prevent duplicate entries and duplicate exchange requests.
* Block entries when market data, history, account state, protection, or risk state is unsafe.
* Provide clear Arabic explanations for every important bot decision.
* Recover safely after UI, engine, service, or VPS restarts.
* Preserve extensibility for future exchanges, Hedge mode, and multi-position policies.

## 4. Non-Goals

Version one will not include:

* Automatic coin discovery, ranking, recommendations, or backtesting.
* Automatic trading of multiple coins simultaneously.
* Exchanges other than Gate.io.
* Hedge-mode trading.
* Multiple simultaneous positions.
* A public web dashboard or public API.
* Mobile applications.
* Profitability claims or strategy optimization recommendations.
* Full Gate.io liquidation simulation in Paper Trading.
* Automated backup scheduling.
* Sentry or external telemetry.
* DPAPI or Windows Credential Manager.
* A dedicated Windows service account.
* Advanced NTFS permission architecture.
* A separate localhost API token.
* Automated update or uninstall systems.
* Windows Event Log integration.

## 5. Version-One Scope

### Supported market

* Gate.io USDT-settled perpetual futures only.
* One-way / Single position mode only.
* Cross margin only.
* Supported leverage choices: 1x, 5x, and 10x.

The engine must verify One-way mode before each entry. It must not automatically switch an account from Hedge mode.

Position models, database records, risk rules, and the ExchangeAdapter must remain extensible for future Hedge mode and multi-position support without partially enabling those features in version one.

### Operating modes

* Paper Trading.
* Gate.io Testnet.
* Live Trading.

Paper Trading and Gate.io Testnet verification are recommended before Live use.
Their results may be recorded as advisory Live Readiness status for the current
engine build and safety-critical configuration. Missing, stale, or incomplete
Paper or Testnet verification must not block the typed `LIVE` activation flow
when every current real safety check passes.

### Watchlist

* Fetch all eligible Gate.io USDT perpetual contracts.
* Provide searchable contract selection.
* Allow the user to add and remove contracts manually.
* Support a maximum of 20 watched contracts.
* Allow one Active Auto-Trading Coin at a time.
* Keep all other watched contracts in monitoring-only mode.
* Allow a user-assigned watchlist priority that affects display order only in version one and does not affect trading decisions.

### Core controls

* Start and stop automatic trading.
* Select the active automatic-trading contract.
* Open manual Long or Short entries.
* Close the current position.
* Cancel pending entry orders.
* Activate Emergency Stop.
* Perform Emergency Close Position.
* Update or disable TP and SL for an open position through explicit confirmed actions.

## 6. User Workflows

### WF-001: Configure and monitor contracts

1. User opens the Arabic control UI.
2. UI connects to the localhost engine.
3. User searches available Gate.io USDT perpetual contracts.
4. User adds up to 20 contracts to the watchlist.
5. UI displays range calculations, signal conditions, freshness, status, and explanations.
6. User may assign display priority.
7. User selects one contract as the Active Auto-Trading Coin.

### WF-002: Start automatic trading

1. User selects Paper, Testnet, or Live mode.
2. User reviews the active contract and configuration.
3. Engine verifies account mode, Cross margin, leverage, market data, history, balance, reserves, risk limits, positions, and orders.
4. User starts automatic trading.
5. Engine evaluates the active contract on every fresh Last Price update.
6. Engine submits an entry only when every required condition passes.

Changing the Active Auto-Trading Coin stops automatic trading and requires the user to explicitly restart it.

### WF-003: Manual entry

1. User selects Long or Short.
2. Manual entry bypasses automatic range, proximity, cooldown, and automatic-trading-enabled conditions.
3. It must still pass central locks, one-position rules, pending-order lock, balance, reserves, exchange rules, market freshness, mode restrictions, and daily risk limits.
4. UI presents a final confirmation.
5. Engine submits the selected Market or Limit entry.
6. TP and enabled SL protection are placed after entry fills.

### WF-004: Live activation

1. User selects Live mode.
2. Engine confirms no Paper or Testnet position or pending order exists.
3. UI presents a clear risk warning.
4. User types `LIVE`.
5. User presses Enable Live Trading.

Live becomes Live Locked after:

* Engine restart.
* VPS or Windows restart.
* Intentional service stop.
* Emergency Stop activation.

Live Locked blocks new entries but does not stop reconciliation or protection of an existing Live position.

### WF-005: Emergency Stop

1. User confirms Emergency Stop.
2. Engine persistently blocks all automatic and manual entries.
3. Engine cancels pending entry orders.
4. Existing positions remain protected by TP and SL.
5. Emergency Stop persists across UI, engine, and VPS restarts.
6. To resume, the user resolves errors, types `RESUME`, and presses Resume Trading.

After resuming:

* Paper and Testnet automatic trading remain disabled until explicitly restarted.
* Live returns to Live Locked.

## 7. Functional Requirements

* **FUNC-001:** The engine and UI must run as separate processes.
* **FUNC-002:** Closing the UI must not stop the engine.
* **FUNC-003:** The UI must reconnect automatically after temporary engine unavailability.
* **FUNC-004:** Settings must be validated before acceptance.
* **FUNC-005:** Runtime-critical state must persist across restarts.
* **FUNC-006:** The user must be able to save, duplicate, rename, edit, apply, and delete named configuration profiles.
* **FUNC-007:** Applying a profile must show a change summary and require confirmation.
* **FUNC-008:** Profiles must not store credentials, positions, orders, history, cooldown state, or runtime locks.
* **FUNC-009:** Applying a profile affects future activity only and must never automatically enable Live Trading.
* **FUNC-010:** The app must save the last active settings automatically.
* **FUNC-011:** The UI must show the profile currently in use.
* **FUNC-012:** Mode changes must be blocked while positions, pending entries, protective orders, Emergency Stop, reconciliation errors, or protection errors exist.
* **FUNC-013:** Paper and Testnet mode selections persist across restarts.
* **FUNC-014:** Paper and Testnet automatic trading resumes after an ordinary restart only if it was previously enabled and all reconciliation, market-data, history, protection, risk, and active-contract checks pass.
* **FUNC-015:** Live always returns to Live Locked after an engine or VPS restart.

## 8. Trading Strategy Requirements

### Analysis modes

* **STRAT-001:** Version one supports one global Analysis Mode for all watched contracts.
* **STRAT-002:** Supported modes are Rolling Window and Current Gate Candle.
* **STRAT-003:** Supported periods are 5 minutes, 15 minutes, 60 minutes, and 24 hours.

### Rolling Window

Rolling Window uses Gate.io one-minute candles:

* 5 minutes: latest 5 candles.
* 15 minutes: latest 15 candles.
* 60 minutes: latest 60 candles.
* 24 hours: latest 1,440 candles.

The current forming one-minute candle is included.

* Opening price: open of the oldest included candle.
* High: highest included candle high.
* Low: lowest included candle low.
* Current price: latest Gate.io Last Price.

Missing, invalid, out-of-sequence, or insufficient candles place the contract in Warming Up / History Gap status and block manual and automatic entries.

Protective Close Position and Cancel Orders actions remain available.

### Current Gate Candle

Opening, high, and low come from the current active Gate.io candle for the selected interval. Values update while the candle is forming. Current price remains Gate.io Last Price.

Gate-provided candle timestamps and interval boundaries must be used consistently for strategy calculations. The UI may convert timestamps to Asia/Riyadh for display, but displayed timezone conversion must not alter candle membership or strategy boundaries.

### Range and proximity conditions

* **STRAT-004:** `Range percentage = ((high - low) / low) * 100`
* **STRAT-005:** `Long proximity = ((last_price - low) / low) * 100`
* **STRAT-006:** `Short proximity = ((high - last_price) / high) * 100`
* **STRAT-007:** The user may choose Exact Percentage Mode or Percentage Interval Mode.
* **STRAT-008:** Exact mode uses a target percentage and configurable tolerance in percentage points.
* **STRAT-009:** Interval mode defaults to 20% minimum and 25% maximum.
* **STRAT-010:** Proximity is editable and defaults to 3%.

Long qualifies when Long proximity is non-negative and less than or equal to the configured proximity.

Short qualifies when Short proximity is non-negative and less than or equal to the configured proximity.

### Direction

Each watchlist contract stores:

* Long Only.
* Short Only.
* Both Long and Short.

Default: Both.

If Long and Short are simultaneously valid for the Active Auto-Trading Coin, the engine must reject both for that evaluation and log Conflicting Long and Short Signal.

### Signal state

Signal states:

* Eligible.
* Retry Delayed.
* Pending / Unknown.
* Used.

The engine must persist a signal snapshot containing:

* Contract.
* Direction.
* Analysis mode.
* Timeframe.
* Window or candle identifier.
* Range.
* High.
* Low.
* Proximity.
* Trigger-zone boundaries.

A Used signal becomes eligible only after:

1. Position and pending entry state are clear.
2. Cooldown ends.
3. Price exits the original saved trigger zone by the configured reset distance.
4. Price later re-enters a valid current trigger zone.
5. All current entry conditions pass.

Default reset distance: 1%, editable.

Starting automatic trading while price is already inside a valid unused trigger zone may cause immediate entry.

## 9. Coin Scanner Requirements

* **SCAN-001:** Version one must not automatically discover, rank, backtest, recommend, add, or enable contracts.
* **SCAN-002:** It must fetch eligible Gate.io USDT perpetual contracts for a searchable selector.
* **SCAN-003:** The user manually controls watchlist membership.
* **SCAN-004:** Maximum watchlist size is 20.
* **SCAN-005:** Exactly one watched contract may be the Active Auto-Trading Coin.
* **SCAN-006:** All other contracts remain monitoring-only.
* **SCAN-007:** Watchlist priority affects display order only.
* **SCAN-008:** Future scanner functionality may evaluate proximity, liquidity, volume, volatility, and backtest metrics, but must require user approval before adding or enabling a contract.

## 10. Risk-Management Requirements

### Allocation

Allocation options: 25%, 50%, 75%, and 100%.

The selected percentage applies to usable available USDT futures balance, not total account equity.

Usable balance equals available balance minus:

* Estimated entry fee.
* Estimated exit fee.
* Margin-safety reserve.

Default safety reserve: 10%.

Minimum reserve:

* Paper: 0%.
* Testnet: 5%.
* Live: 10%.

Live reserve cannot be set below 10%.

Notional position value equals allocated margin multiplied by leverage.

Quantity must be calculated from the expected entry price, rounded according to Gate.io rules, and rejected if the remaining balance is insufficient after all checks.

### Fee reserve

* Store Maker and Taker rates separately.
* Retrieve current applicable Gate.io futures fee rates when available.
* Refresh them periodically.
* Use Taker fees for both entry and exit when sizing conservatively.
* Fallback Maker rate: 0.10% per side.
* Fallback Taker rate: 0.10% per side.
* Paper Trading persists its own local Maker/Taker fee schedule, initially
  0.10% for each rate. It must never query, display, use, or alter a real
  Gate.io account to obtain Paper fee rates.

### Daily limits

Daily reset occurs at 00:00 Asia/Riyadh.

Defaults:

* Maximum realized daily net loss: 5% of adjusted daily baseline.
* Maximum fully closed losing trades: 3.
* Maximum automatic entries receiving any fill: 5.

Realized daily net loss includes realized P&L, trading fees, and funding fees or credits.

Reaching the daily-loss or losing-trade limit blocks automatic and manual entries.

Reaching the automatic-trade limit blocks automatic entries only.

Close Position and Cancel Orders remain available.

Live daily-loss percentage:

* Cannot be disabled.
* Must be between 1% and 5%.
* Defaults to 5%.

### Daily baseline

The baseline is total Gate.io futures equity recorded at 00:00 Asia/Riyadh, including wallet balance and unrealized P&L at that moment.

Later unrealized P&L changes do not alter the baseline and do not count toward realized daily loss.

Confirmed deposits increase the baseline. Confirmed withdrawals reduce it.

If the engine starts after 00:00 Asia/Riyadh and no daily baseline exists, it must:

1. Fetch a fresh Gate.io equity snapshot.
2. Store it as a Late Daily Baseline.
3. Clearly log and display that it was created late.
4. Block new Live and automatic entries until the baseline is stored.

If deposits or withdrawals cannot be reliably reconciled, new entries must be blocked with Daily Risk Baseline Requires Review.

## 11. Order-Execution Requirements

### Persistent request identity and idempotency

* **EXEC-001:** Every entry, TP, SL, cancellation, and close request must have a persistent client-generated request or order identifier.
* **EXEC-002:** The engine must persist the intent and identifier before sending the request to Gate.io.
* **EXEC-003:** A timeout or missing response must not cause the engine to submit the request again immediately.
* **EXEC-004:** The engine must reconcile Gate.io using the persistent identifier and real order or fill state before deciding whether a retry is safe.
* **EXEC-005:** RangeBot must never create a duplicate order merely because a response was delayed or not received.

### Entry types

* Market and Limit entries are supported.
* Market is the default for automatic trading.
* Automatic Limit offset defaults to 0%.
* Limit expiry defaults to 60 seconds.

Long Limit price equals current price reduced by the configured offset.

Short Limit price equals current price increased by the configured offset.

An unfilled Limit order is cancelled at expiry and marks the signal Used.

A partially filled Limit order:

* Marks the signal Used.
* Cancels the unfilled remainder.
* Manages the filled position using the actual quantity and average fill.

A pending entry order counts as the account’s one active trade state.

### Market-entry protection

Immediately before submission:

* Capture a fresh Last Price.
* Fetch a fresh Gate.io order-book snapshot.
* Require both to be less than one second old.
* Estimate volume-weighted execution using Ask liquidity for Long and Bid liquidity for Short.
* Enforce a maximum expected deviation of 0.30% from the captured Last Price.

Reject the entry before submission if liquidity is insufficient or expected deviation exceeds the limit.

Do not automatically resize, convert, or retry the order.

A blocked pre-submission signal remains Eligible and may retry no more than once every five seconds.

A definitive exchange rejection becomes Retry Delayed and may retry after 30 seconds if the cause is resolved.

An uncertain result becomes Pending / Unknown. No retry is allowed until reconciliation confirms whether an order or fill exists.

### Paper Trading execution

* **PAPER-001:** Paper Trading must use the same strategy, sizing, rounding, reserves, one-position rule, cooldown, TP, and SL logic as Testnet and Live.
* **PAPER-002:** Paper Market Long fill equals Last Price plus configured adverse slippage.
* **PAPER-003:** Paper Market Short fill equals Last Price minus configured adverse slippage.
* **PAPER-004:** Default Paper Trading slippage is 0.10%.
* **PAPER-005:** A Paper Limit Long fills when Last Price is less than or equal to the limit price.
* **PAPER-006:** A Paper Limit Short fills when Last Price is greater than or equal to the limit price.
* **PAPER-007:** Paper Limit orders fill fully or not at all in version one.
* **PAPER-008:** Paper Limit orders use the same configured expiry rule.
* **PAPER-009:** Paper mode uses configured Maker and Taker fees.
* **PAPER-010:** Market entries and Stop Loss exits use the Taker rate.
* **PAPER-011:** Limit entries and Take Profit exits use the Maker rate unless the order would execute immediately, in which case the Taker rate applies.
* **PAPER-012:** Paper mode displays estimated liquidation price and Cross-margin risk.
* **PAPER-013:** Paper mode does not simulate Gate.io’s complete liquidation engine or forced-liquidation behavior.

### Take Profit and Stop Loss

* TP is enabled by default.
* Default TP is an expected net return equal to 30% of allocated margin.
* SL is enabled by default.
* Default SL is an expected net loss equal to 10% of allocated margin.

Calculations must use:

* Actual average fill price.
* Actual filled quantity.
* Selected leverage.
* Actual entry fees.
* Estimated closing fees.
* Gate.io futures contract and P&L rules.

TP uses a reduce-only limit order.

SL uses a Mark Price-triggered reduce-only stop-market order.

Neither order may open or increase a reverse position.

Protection rejection or external cancellation must trigger reconciliation and restoration unless protection was explicitly disabled for that open position.

Until Gate.io confirms protection exists, the position must be marked TP Protection Error or Stop Loss Protection Error. The error must block new entries and be displayed prominently.

If TP partially fills:

* Reconcile the real remaining position size.
* Resize TP for the remaining position.
* Ensure SL protection remains correctly sized.

If SL triggers but only partially closes:

* Reconcile the remaining position size.
* Immediately submit reduce-only market closes for the remainder.
* Continue reconciling until position size is zero or Gate.io reports an unrecoverable error.

Global TP or SL changes affect future trades only. Updating protection for an open position requires a separate confirmed action.

### Disabling protection

* **EXEC-006:** TP and SL may be disabled globally for future trades.
* **EXEC-007:** TP or SL may be disabled for an open position only through an explicit confirmed action.
* **EXEC-008:** Disabling TP on an open Live position requires typed confirmation `DISABLE TP`.
* **EXEC-009:** Disabling SL on an open Live position requires typed confirmation `DISABLE SL`.
* **EXEC-010:** Disabling either protection must produce a persistent high-risk warning.
* **EXEC-011:** If both are disabled, the UI must display `NO AUTOMATIC EXIT PROTECTION`.
* **EXEC-012:** Opening a Live trade with both TP and SL disabled requires typed confirmation `UNPROTECTED POSITION`.

### Manual Close Position

Manual Close Position must:

1. Take the central trading lock and block new entries.
2. Reconcile the real current Gate.io position quantity.
3. Cancel active TP and SL orders for the position.
4. Reconcile again because protection may have filled during cancellation.
5. Submit a reduce-only market close for the actual remaining quantity.
6. Reconcile and repeat reduce-only closing after a partial fill until the position is zero or Gate.io reports an unrecoverable error.
7. Verify all old protective orders are absent before cleanup completes.

### Protection-triggered closure

If TP or SL fully closes a position, the engine must:

1. Take the central trading lock.
2. Reconcile the real position size.
3. Cancel the opposite protective order.
4. Verify the position size is zero.
5. Verify both old protective orders are absent.
6. Record the closure reason.
7. Begin cooldown.

No new entry may open until this cleanup is complete.

Cooldown must not begin after a partial reduction.

## 12. Exchange Integration Requirements

* **EXCH-001:** Use Gate.io API v4.
* **EXCH-002:** Use WebSockets for live prices and order or position updates.
* **EXCH-003:** Use REST for snapshots, candle history, balances, fee rates, configuration, reconciliation, and order operations as appropriate.
* **EXCH-004:** Gate.io-specific payloads must remain inside the Gate.io adapter.
* **EXCH-005:** Domain models must support future position modes and multiple position legs without enabling them in version one.
* **EXCH-006:** Before every entry, verify One-way mode, Cross margin, leverage, positions, and pending orders.
* **EXCH-007:** Cross margin and leverage may be set automatically only when no conflicting position or order exists.
* **EXCH-008:** Never assume a requested configuration change succeeded until Gate.io confirms it.
* **EXCH-009:** Use Last Price for signals and proximity.
* **EXCH-010:** Use Mark Price for SL trigger.
* **EXCH-011:** Before entry, display a clearly labelled estimated liquidation price.
* **EXCH-012:** After a Testnet or Live position opens, use Gate.io’s reported liquidation price as the source of truth.
* **EXCH-013:** Do not automatically cancel an unrelated order or close a position merely to force a margin-mode or leverage change.

## 13. User Interface Requirements

* **UI-001:** Full Arabic RTL layout.
* **UI-002:** Modern, polished visual design suitable for daily use.
* **UI-003:** Correct mixed-direction display for Arabic text, English symbols, prices, percentages, and contract names.
* **UI-004:** Centralized font configuration supporting a bundled custom Arabic font later.
* **UI-005:** Main dashboard must show engine status, connection, operating mode, Live Locked state, balance, active contract, position, cooldown, daily risk, protection state, and Emergency Stop.
* **UI-006:** Each watched contract must show opening price, Last Price, high, low, range, Long proximity, Short proximity, direction setting, auto status, freshness, and decision status.
* **UI-007:** A details view must list every passed and failed entry condition.
* **UI-008:** Manual Live confirmation must show contract, direction, mode, order type, price, allocated margin, leverage, notional value, rounded quantity, fees, estimated liquidation price, TP, SL, and remaining balance.
* **UI-009:** Persistent warnings are required when TP or SL is disabled.
* **UI-010:** If both are disabled, show `NO AUTOMATIC EXIT PROTECTION`.
* **UI-011:** Opening an unprotected Live trade requires `UNPROTECTED POSITION`.
* **UI-012:** Disabling TP on an open Live position requires `DISABLE TP`.
* **UI-013:** Disabling SL on an open Live position requires `DISABLE SL`.
* **UI-014:** The UI must contain an Arabic Help Center covering modes, strategy, Long and Short signals, TP, SL, Cross margin, leverage, liquidation, fees, manual versus automatic trading, cooldown, Emergency Stop, and order rejection reasons.
* **UI-015:** Every watched contract must show a clear Arabic decision explanation.
* **UI-016:** Every submitted, rejected, cancelled, restored, or recovered order must have a human-readable Arabic activity-log explanation.

## 14. Technical Constraints

* Python trading engine.
* PySide6/Qt desktop UI.
* FastAPI bound to `127.0.0.1`.
* PostgreSQL bound locally only.
* SQLAlchemy 2.x and Alembic.
* Pydantic validation.
* Asyncio runtime.
* Decimal-safe financial calculations.
* Structlog with rotating local files.
* Pytest and Hypothesis.
* Development managed with `pyproject.toml`, `uv`, and `uv.lock`.
* Separate PyInstaller `onedir` builds for engine and UI.
* WinSW launches `bot-engine.exe`.
* Core strategy, risk, execution, and exchange-domain logic must remain operating-system independent.
* Source files and documentation must be stored as UTF-8.

## 15. Security Requirements

* **SEC-001:** Store version-one credentials in a local `.env`.
* **SEC-002:** Exclude `.env` from Git and executable builds.
* **SEC-003:** Never display or log complete credentials.
* **SEC-004:** Apply basic Windows file permissions to `.env`.
* **SEC-005:** Gate.io keys must have withdrawals disabled.
* **SEC-006:** Grant only required trading permissions.
* **SEC-007:** Use VPS IP whitelisting where Gate.io supports it.
* **SEC-008:** PostgreSQL and FastAPI must not be publicly exposed.
* **SEC-009:** The control UI must never submit Gate.io orders directly.
* **SEC-010:** Live mode must require the confirmed typed activation procedure.

## 16. Failure Handling and Recovery

* **SAFE-001:** On startup and reconnection, reconcile real Gate.io positions, orders, partial fills, protection, and database state before new entries.
* **SAFE-002:** Gate.io state is authoritative for real positions and orders.
* **SAFE-003:** Unresolved reconciliation blocks entries.
* **SAFE-004:** Market data becomes stale after 10 seconds without a valid live update.
* **SAFE-005:** After reconnecting, require subscription confirmation, a fresh REST snapshot, at least two newer WebSocket price updates within 10 seconds, and account reconciliation.
* **SAFE-006:** Manual and automatic entries are blocked during stale or incomplete market data.
* **SAFE-007:** Close Position and Cancel Orders remain available during stale or disconnected states.
* **SAFE-008:** Cooldown begins only after real position size is zero and old protection is confirmed absent.
* **SAFE-009:** Cooldown persists across restarts.
* **SAFE-010:** A full external Gate.io closure must be detected, recorded as External Gate.io Closure, and cleaned up.
* **SAFE-011:** A partial external position reduction must resize remaining TP and SL protection.
* **SAFE-012:** Live remains locked after engine restart, VPS restart, service stop, or Emergency Stop.
* **SAFE-013:** Paper and Testnet automatic trading may resume after an ordinary restart only when previously enabled and all required safety checks pass.
* **SAFE-014:** Unknown order outcomes must block new entries until reconciled.
* **SAFE-015:** A request timeout must never cause an unverified duplicate order.

## 17. Logging and Reporting

Record:

* Engine and service lifecycle events.
* Mode changes and Live activation or lock.
* Market connection and freshness changes.
* Reconciliation results.
* Strategy conditions and decision reasons.
* Signal-state transitions.
* Client request and order identifiers.
* Entry attempts, blocks, submissions, fills, cancellations, and rejections.
* Actual slippage.
* TP and SL placement, restoration, updates, disabling, partial fills, and errors.
* Manual actions.
* Emergency actions.
* Position closures and closure reasons.
* Realized P&L, trading fees, funding, and daily risk counters.
* Daily baseline creation and adjustment.
* Cooldown start and expiry.
* Profile changes.

Every user-facing event must have a clear Arabic explanation.

Logs must redact API credentials, request signatures, authentication headers, database passwords, and `.env` contents.

## 18. Installation and Deployment Constraints

Production layout must remain simple:

* Engine directory containing the engine `onedir` build.
* Control UI directory containing the UI `onedir` build.
* Config directory containing `.env` and non-sensitive configuration.
* Logs directory.
* Service directory containing WinSW executable and XML.

The WinSW service must:

* Start automatically with Windows.
* Restart the engine if it crashes.
* Stop cleanly when intentionally stopped.
* Continue running after Remote Desktop disconnects.

Stopping the service must not automatically close an existing position.

Before Live Trading, documentation must include and test a manual PostgreSQL backup and restore procedure using standard PostgreSQL tools.

Restoration must be followed by:

1. Engine restart.
2. Database-state validation.
3. Gate.io position and order reconciliation.
4. Protection validation.
5. Entry blocking until reconciliation succeeds.

## 19. Testing and Acceptance Criteria

### Core acceptance criteria

* **TEST-001:** Engine continues running after UI closure and Remote Desktop disconnection.
* **TEST-002:** Paper and Testnet reconcile and resume correctly after restart when previously enabled.
* **TEST-003:** Live returns to Live Locked after restart.
* **TEST-004:** No new entry occurs when a real position or pending entry exists.
* **TEST-005:** Missing or non-contiguous candle history blocks entries.
* **TEST-006:** Current Gate Candle calculations follow Gate interval boundaries.
* **TEST-007:** Stale data blocks entries within 10 seconds.
* **TEST-008:** Duplicate Used signals cannot re-enter before full reset.
* **TEST-009:** Duplicate exchange requests are not submitted after timeouts or missing responses.
* **TEST-010:** Market entries exceeding 0.30% expected deviation are rejected before submission.
* **TEST-011:** Paper Market fills apply configured adverse slippage.
* **TEST-012:** Paper Limit entries follow the confirmed full-fill-or-no-fill rules.
* **TEST-013:** Partial real fills produce correctly sized TP and SL protection.
* **TEST-014:** TP or SL cannot reverse a position.
* **TEST-015:** Manual Close Position follows the lock, cancellation, reconciliation, reduce-only close, and cleanup sequence.
* **TEST-016:** TP or SL closure cancels opposite protection and completes cleanup before cooldown.
* **TEST-017:** External position changes are detected and reconciled.
* **TEST-018:** Cooldown survives engine and VPS restart.
* **TEST-019:** Emergency Stop persists across restart.
* **TEST-020:** Daily limits reset at 00:00 Asia/Riyadh and persist across restart.
* **TEST-021:** Late Daily Baseline creation blocks required entries until storage succeeds.
* **TEST-022:** Profiles never contain credentials or active trading state.
* **TEST-023:** Live cannot be enabled without the required confirmation.
* **TEST-024:** Mode switching is blocked during unresolved activity.
* **TEST-025:** Manual protective actions remain available during stale-data states.
* **TEST-026:** Disabling TP or SL on an open Live position requires the correct typed confirmation.
* **TEST-027:** A Live entry with TP and SL disabled requires `UNPROTECTED POSITION`.

Testing must include:

* Unit tests for calculations and state transitions.
* Property-based tests for financial precision, formulas, and quantity rounding.
* Mocked Gate.io REST and WebSocket tests.
* Idempotency and uncertain-order-outcome tests.
* Paper execution tests.
* Testnet integration tests.
* Restart, timeout, partial-fill, disconnection, and reconciliation scenarios.
* Manual backup and restore validation before advisory Live Readiness is marked Verified.

## 20. Open Decisions

No blocking product decisions remain.

Non-blocking implementation choices:

* Final Arabic font.
* Final visual theme and icon set.
* Whether user-facing alerts include optional sounds.
* Exact fee-rate refresh interval.
* Final Arabic Help Center wording.
