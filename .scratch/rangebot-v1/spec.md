# RangeBot Version One Technical Implementation Specification

Status: ready-for-agent
Labels: ready-for-agent

## Problem Statement

A single private operator needs to monitor Gate.io USDT-settled perpetual
contracts and execute a confirmed range-and-proximity strategy continuously on
a Windows VPS. The operator needs one selected contract to trade automatically,
must also be able to place controlled manual Long and Short entries, and needs
clear Arabic RTL explanations for every decision and safety block.

The system must reduce the operational risks inherent in leveraged futures
trading. In particular, it must prevent duplicate or conflicting orders, refuse
entries when data or account state is unsafe, preserve protection around open
positions, reconcile uncertain exchange outcomes, survive process and VPS
restarts, and keep the trading engine running independently of the desktop UI.
It must do this consistently across an isolated Paper Account, Gate.io Testnet,
and Gate.io Live without implying profitability or silently taking control of
exchange state that RangeBot does not own.

## Solution

Build RangeBot as two separately deployable Python applications: an asynchronous
trading engine that runs continuously as a Windows service, and a PySide6 Arabic
RTL desktop control UI. The UI communicates only with the engine through a
localhost FastAPI boundary. The engine owns strategy evaluation, risk checks,
exchange interaction, state transitions, persistence, reconciliation, and all
order submission.

The engine monitors a user-managed watchlist of at most 20 eligible Gate.io USDT
perpetual contracts. It calculates Rolling Window or Current Gate Candle range
conditions for every watched contract and may automatically trade exactly one
Active Auto-Trading Coin. A central entry gate applies account, data, history,
risk, balance, sizing, execution, and protection checks to every entry, while
manual entries bypass only the automatic strategy, proximity, cooldown, and
automatic-enabled conditions explicitly identified in the requirements.

All safety-critical intent and runtime state is persisted before external side
effects. Real exchange state is reconciled against persistent RangeBot identity;
unknown outcomes block new entries until resolved. Paper Trading uses the same
domain rules through a persistent, fully isolated Paper Account. The UI presents
the resulting state, confirmations, warnings, condition breakdowns, and activity
explanations in Arabic RTL without becoming a trading authority.

## User Stories

1. As the operator, I want the trading engine to run as a Windows service, so that trading and protection continue when the UI is closed or Remote Desktop disconnects.
2. As the operator, I want the desktop UI to reconnect automatically, so that temporary engine unavailability does not require restarting the application.
3. As the operator, I want all controls and explanations presented in Arabic RTL, so that I can operate the system confidently.
4. As the operator, I want English contract symbols, numbers, and percentages to render correctly inside Arabic text, so that market information remains unambiguous.
5. As the operator, I want to search eligible Gate.io USDT perpetual contracts, so that I can choose what to monitor.
6. As the operator, I want to add and remove contracts manually up to a limit of 20, so that RangeBot never changes my watchlist without consent.
7. As the operator, I want watchlist priority to control display order only, so that presentation preferences cannot influence trades.
8. As the operator, I want to designate exactly one Active Auto-Trading Coin, so that only one contract can generate automatic entries.
9. As the operator, I want changing the Active Auto-Trading Coin to stop automatic trading, so that a new contract cannot begin trading without an explicit restart.
10. As the operator, I want all other watched contracts to remain monitoring-only, so that I can compare signals without risking multiple automatic trades.
11. As the operator, I want each watched contract to show opening price, Last Price, high, low, range, Long and Short proximity, freshness, direction, signal status, and decision status, so that I can understand its current evaluation.
12. As the operator, I want a condition-details view showing every passed and failed entry condition, so that rejected or eligible decisions are explainable.
13. As the operator, I want one global Analysis Mode and timeframe, so that all monitored contracts are evaluated consistently.
14. As the operator, I want Rolling Window analysis over 5, 15, 60, or 1,440 one-minute candles, so that I can measure the selected recent range including the forming candle.
15. As the operator, I want Current Gate Candle analysis for 5-minute, 15-minute, 60-minute, or 24-hour intervals, so that calculations follow Gate.io's active candle boundaries.
16. As the operator, I want incomplete, invalid, missing, or out-of-sequence candle history to block entries, so that decisions are not based on corrupt ranges.
17. As the operator, I want Exact Percentage Mode with a tolerance, so that ranges can qualify near a specific target.
18. As the operator, I want Percentage Interval Mode, defaulting to 20% through 25%, so that ranges can qualify inside a band.
19. As the operator, I want configurable Long and Short proximity with a 3% default, so that entries occur only near the relevant range edge.
20. As the operator, I want each contract set to Long Only, Short Only, or Both, so that allowed directions match my intent.
21. As the operator, I want simultaneous Long and Short qualification rejected and explained, so that an ambiguous signal cannot trade.
22. As the operator, I want an unused valid signal already in its trigger zone to be eligible when automatic trading starts, so that startup does not require an artificial price movement.
23. As the operator, I want an accepted, expired, or partially filled signal to become a Used Signal, so that it cannot cause duplicate entries.
24. As the operator, I want a Used Signal to retain its original Signal Trigger Zone, so that later range movement cannot manufacture a reset.
25. As the operator, I want a Long Used Signal to reset only after an upward Directional Reset and a Short Used Signal only after a downward Directional Reset, so that further movement into the entry side does not reset it.
26. As the operator, I want cooldown, Directional Reset, a later valid current zone, and all current entry checks to pass before reuse, so that re-entry is deliberate.
27. As the operator, I want to select Paper Trading, Gate.io Testnet, or Live Trading, so that I can progress through increasingly consequential environments.
28. As the operator, I want Paper Trading to use an isolated persistent Paper Account, so that simulation never reads or changes my real Gate.io account state.
29. As the operator, I want to choose or reset the Paper Starting Balance with confirmation only when no Paper position or pending entry exists, so that simulated accounting remains coherent.
30. As the operator, I want Paper Trading to share strategy, sizing, rounding, reserve, protection, cooldown, and risk logic with exchange-backed modes, so that it is meaningful preparation.
31. As the operator, I want adverse slippage and Maker/Taker fees simulated in Paper Trading, so that Paper results are not unrealistically favorable.
32. As the operator, I want Paper Limit orders to fill fully or not at all under the confirmed Last Price rules and expiry, so that version-one simulation behavior is deterministic.
33. As the operator, I want Paper liquidation information clearly identified as an estimate, so that I do not mistake it for Gate.io's full liquidation engine.
34. As the operator, I want Live readiness confirmations for Paper and Testnet to be recorded against the engine build and Safety-Critical Profile Fingerprint, so that I can see whether the current configuration was verified.
35. As the operator, I want missing or stale Paper/Testnet evidence to produce a prominent warning but never block the typed `LIVE` activation flow when all current real safety checks pass, so that advisory verification is distinct from current account safety.
36. As the operator, I want Live activation to require the exact typed confirmation `LIVE`, so that real-money activation cannot be accidental.
37. As the operator, I want Live to return to Live Locked after engine, service, Windows, or VPS restart and after Emergency Stop, so that entries require fresh authorization.
38. As the operator, I want Live Locked to preserve reconciliation and existing-position protection, so that locking entries does not abandon risk management.
39. As the operator, I want Paper and Testnet automatic trading to resume after an ordinary restart only when previously enabled and every safety check passes, so that safe continuity is possible.
40. As the operator, I want manual Market and Manual Limit Entry controls with final confirmation, so that I can enter a chosen direction without enabling the automatic strategy.
41. As the operator, I want a Manual Limit Entry to use my absolute entered price and be validated without silent adjustment, so that the submitted intent matches my confirmation.
42. As the operator, I want a Marketable Limit Order identified as Taker execution, so that fee and confirmation estimates reflect likely immediate execution.
43. As the operator, I want manual entry to bypass only automatic signal, proximity, cooldown, and automatic-enabled checks, so that all account and execution safeguards still apply.
44. As the operator, I want every entry to verify One-way mode, Cross margin, selected leverage, current positions, and pending orders, so that RangeBot does not trade incompatible account state.
45. As the operator, I want the system never to switch Hedge mode automatically, so that an incompatible account is blocked rather than silently altered.
46. As the operator, I want Cross margin and leverage changed only when no conflicting state exists and confirmed afterward, so that requested configuration is never assumed effective.
47. As the operator, I want one open position or pending entry state per account, so that concurrent trades cannot bypass the version-one risk policy.
48. As the operator, I want allocation choices of 25%, 50%, 75%, or 100% applied to Available Futures Balance after the Safety Reserve, so that sizing follows my configured exposure.
49. As the operator, I want the Allocation Budget to include Allocated Margin and estimated round-trip fees, so that 100% allocation cannot overspend the account.
50. As the operator, I want quantity rounded down using Gate.io contract rules and rechecked after rounding, so that submitted size is valid and affordable.
51. As the operator, I want conservative Taker rates used for sizing with explicit fallbacks, so that missing fee data cannot under-budget costs.
52. As the operator, I want a clearly labelled estimated liquidation price before entry and Gate.io's reported value afterward, so that I can assess Cross-margin risk using the best available source.
53. As the operator, I want Market entries checked against a Last Price and order book less than one second old, so that expected execution is based on current liquidity.
54. As the operator, I want Market entries rejected above 0.30% expected volume-weighted deviation or when liquidity is insufficient, so that the engine does not accept excessive expected slippage.
55. As the operator, I want blocked pre-submission signals rate-limited without being consumed, so that transient liquidity conditions can recover without request storms.
56. As the operator, I want definitive exchange rejections delayed before retry and unknown outcomes prevented from retrying, so that failure handling cannot duplicate orders.
57. As the operator, I want every external request to have a persistent client identity saved before submission, so that timeouts can be reconciled idempotently.
58. As the operator, I want pending Limit expiry to cancel the remainder and consume the signal, so that an expired opportunity cannot submit repeatedly.
59. As the operator, I want a partially filled real Limit entry to cancel its remainder and protect the actual filled quantity, so that residual exposure is managed correctly.
60. As the operator, I want enabled TP and SL calculated from actual fill, quantity, leverage, fees, and Gate.io P&L rules, so that expected net return and loss targets are meaningful.
61. As the operator, I want TP submitted as reduce-only Limit and SL as Mark Price-triggered reduce-only stop-market, so that protection cannot open or enlarge a reverse position.
62. As the operator, I want missing or externally cancelled protection restored after reconciliation unless I explicitly disabled it, so that open positions remain protected.
63. As the operator, I want protection errors displayed prominently and to block entries, so that the system does not compound unprotected exposure.
64. As the operator, I want partial TP fills to resize remaining TP and SL and partial SL closure to drive reduce-only closes to zero, so that residual positions are not overlooked.
65. As the operator, I want global TP and SL changes to affect future trades only, so that an open position is never modified implicitly.
66. As the operator, I want separate confirmation to update or disable protection on an open position, so that changes to current risk are explicit.
67. As the operator, I want typed `DISABLE TP` or `DISABLE SL` confirmations for Live positions, so that removal of protection is deliberate.
68. As the operator, I want persistent warnings when either protection is disabled and `NO AUTOMATIC EXIT PROTECTION` when both are disabled, so that elevated risk remains visible.
69. As the operator, I want typed `UNPROTECTED POSITION` confirmation before opening an entirely unprotected Live trade, so that I explicitly accept that risk.
70. As the operator, I want Manual Close Position to reconcile, cancel old protection, close only the actual remainder reduce-only, and verify cleanup, so that closing cannot reverse or race the position.
71. As the operator, I want Emergency Close Position to activate Emergency Stop first and then perform the close workflow, so that no new entry can race an emergency exit.
72. As the operator, I want a failed or disconnected Emergency Close Position never queued for later execution, so that a stale close cannot fire without fresh action and reconciliation.
73. As the operator, I want protection-triggered closure to cancel opposite protection and verify zero position before cooldown, so that old orders cannot affect a later trade.
74. As the operator, I want cooldown to start only after zero position and absence of old protection are confirmed, so that a partial reduction is not treated as closure.
75. As the operator, I want cooldown to persist through restarts, so that restarting cannot bypass the waiting period.
76. As the operator, I want Emergency Stop to persistently block automatic and manual entries and cancel managed pending entries, so that it is an account-level safety lock.
77. As the operator, I want resuming to require `RESUME`, so that Emergency Stop cannot be cleared accidentally.
78. As the operator, I want Paper and Testnet automatic trading left disabled after resume and Live returned to Live Locked, so that clearing Emergency Stop does not itself restart entries.
79. As the operator, I want RangeBot to recognize Unmanaged Exchange State and remain read-only toward it, so that it never cancels or closes exchange activity it cannot prove it owns.
80. As the operator, I want Unmanaged Exchange State to block entries, mode changes, and managed close/cancel workflows until I resolve it on Gate.io, so that conflicting state cannot be hidden.
81. As the operator, I want Refresh Reconciliation after resolving Unmanaged Exchange State, so that RangeBot can safely confirm the account is clear without adopting external state.
82. As the operator, I want startup and reconnect reconciliation before new entries, so that database assumptions are checked against authoritative real exchange state.
83. As the operator, I want market data stale after 10 seconds without a valid update, so that both automatic and manual entries stop promptly.
84. As the operator, I want reconnection to require subscription confirmation, a REST snapshot, two newer WebSocket updates within 10 seconds, and account reconciliation, so that a socket reconnect alone is not treated as readiness.
85. As the operator, I want Close Position and Cancel Orders available during stale or disconnected market-data states when reconciliation permits, so that protective actions remain possible.
86. As the operator, I want external full closures and partial reductions detected and reconciled, so that RangeBot's records and protection match Gate.io.
87. As the operator, I want daily risk measured from a baseline at 00:00 Asia/Riyadh, so that limits reset on a predictable local-day boundary.
88. As the operator, I want realized net loss to include realized P&L, trading fees, and funding, so that daily loss reflects actual account impact.
89. As the operator, I want daily loss and losing-trade limits to block all entries while the automatic-fill limit blocks automatic entries only, so that risk controls match their purpose.
90. As the operator, I want confirmed deposits and withdrawals to adjust the daily baseline, so that cash movement is not mistaken for trading performance.
91. As the operator, I want a Late Daily Baseline stored from fresh equity when necessary and entries blocked until storage succeeds, so that a restart cannot leave risk limits undefined.
92. As the operator, I want ambiguous deposits or withdrawals to produce Daily Risk Baseline Requires Review, so that uncertain accounting blocks new risk.
93. As the operator, I want named profiles that can be saved, duplicated, renamed, edited, applied, and deleted, so that I can manage configurations safely.
94. As the operator, I want profile application to show a change summary and require confirmation, so that configuration changes are visible before use.
95. As the operator, I want profiles to exclude credentials and runtime trading state, so that applying a profile cannot adopt or overwrite active activity.
96. As the operator, I want profile changes to affect future activity only and never enable Live, so that configuration cannot bypass live authorization.
97. As the operator, I want all submitted, blocked, rejected, filled, cancelled, restored, reconciled, and recovered actions explained in Arabic, so that the audit trail is understandable.
98. As the operator, I want secrets and request authentication material redacted from every log path, so that diagnostics cannot expose credentials.
99. As the operator, I want PostgreSQL and the engine API bound locally only, so that version one does not expose a public control surface.
100. As the operator, I want a documented and tested manual PostgreSQL backup and restore procedure before Live use, so that persistent safety state can be recovered and reconciled.

## Implementation Decisions

### System boundaries and authority

- The trading engine and desktop UI are separate processes and separate
  PyInstaller `onedir` deliverables. WinSW owns engine service lifecycle; the UI
  may disappear and reconnect without changing engine behavior.
- FastAPI is the only UI-to-engine command and query boundary and binds to
  `127.0.0.1`. PostgreSQL also binds locally. There is no public API and no
  separate localhost API token in version one.
- The UI is a presentation and confirmation client. It never holds exchange
  authority and never submits Gate.io orders directly.
- Core domain, strategy, risk, execution, and exchange-port logic remains
  independent from Windows, WinSW, Qt, FastAPI, SQLAlchemy, and Gate.io payload
  shapes. Operating-system, transport, persistence, and vendor concerns remain
  adapters at the edges.
- The asynchronous engine is the sole writer of trading runtime state. Commands
  that can conflict use a central account-scoped trading lock and durable state
  transitions.

### Domain and persistence model

- PostgreSQL stores validated settings, named profiles, watchlist configuration,
  active mode and contract, automatic-trading intent, request intents, orders,
  fills, positions, protection, Signal Trigger Zones, Used Signals, cooldowns,
  Emergency Stop, Live Locked state, daily baselines and counters, reconciliation
  state, Live Readiness Records, and user-facing activity records.
- Schema evolution is migration-backed with SQLAlchemy 2.x and Alembic. Pydantic
  validates all external commands, settings, API inputs, exchange payloads, and
  persisted configuration boundaries.
- Prices, quantities, balances, margin, fees, funding, P&L, percentages, and all
  derived financial values use `Decimal`; `float` is forbidden in financial
  paths. Timestamps are timezone-aware.
- Persistent identities distinguish RangeBot-managed intents and orders from
  Unmanaged Exchange State. No position or order is adopted merely because its
  contract, direction, or size resembles a RangeBot record.
- Runtime state is separated by Paper Account, Testnet account, and Live account.
  A mode change cannot reinterpret or transfer positions, orders, cooldowns,
  baselines, signals, or protection between accounts.
- Position and exchange-port models include explicit position mode and leg
  identity so future Hedge mode and multiple-leg policies can be added, while
  version one validates and permits only One-way mode and a single active trade
  state per account.

### Engine application services and localhost contract

- The engine exposes versioned command/query contracts for engine health,
  current state snapshots, available contracts, watchlist management, profile
  management, settings validation, mode selection, Active Auto-Trading Coin
  selection, automatic-trading start/stop, entry preview, confirmed manual
  entry, managed order cancellation, Manual Close Position, Emergency Stop,
  Emergency Close Position, resume, open-position protection changes, Live
  activation, verification records, and Refresh Reconciliation.
- Mutating commands carry a client command identity. The engine validates
  idempotency, current state, required typed confirmation, and optimistic state
  version where stale confirmation would be dangerous.
- Entry preview returns the exact state the user must confirm: mode, account,
  contract, direction, order type, absolute or derived Limit price, expected
  entry price, Allocated Margin, leverage, notional value, rounded quantity,
  entry and exit fees, remaining balance, estimated liquidation price, TP, SL,
  protection warnings, market-data age, and passed/failed safety conditions.
  Submission rejects a preview whose safety-critical inputs or state version are
  no longer current.
- Queries return structured reason codes plus Arabic display text. Stable reason
  codes drive tests and UI behavior; Arabic text remains user-facing content and
  is not parsed to determine logic.
- The UI receives a complete state snapshot after connecting and incremental
  updates thereafter. It tolerates gaps by fetching a new snapshot rather than
  inferring missing state.

### Market data, analysis, and signals

- Gate.io WebSockets provide live Last Price and order/position updates. REST
  provides authoritative snapshots, contract rules, candle history, balances,
  fee data, configuration checks, and reconciliation.
- Rolling Window uses the latest 5, 15, 60, or 1,440 one-minute candles,
  including the forming candle. The oldest included open, maximum high, and
  minimum low define the range; current price is the latest Last Price.
- Current Gate Candle uses Gate.io's active interval open, high, low, timestamp,
  and boundary for 5-minute, 15-minute, 60-minute, or 24-hour analysis. Riyadh
  conversion is display-only and never changes candle membership.
- Any insufficient, invalid, missing, duplicate, or out-of-sequence candle set
  produces Warming Up / History Gap and blocks both manual and automatic entry.
- Range percentage is `((high - low) / low) * 100`; Long proximity is
  `((last_price - low) / low) * 100`; Short proximity is
  `((high - last_price) / high) * 100`. A proximity qualifies only when it is
  non-negative and no greater than the configured threshold.
- Exact mode compares range percentage to a target using a configurable
  percentage-point tolerance. Interval mode uses inclusive minimum and maximum
  bounds, defaulting to 20% and 25%. Proximity defaults to 3%.
- Evaluation happens on each fresh Last Price update. If both allowed directions
  qualify in one evaluation, neither may enter and the decision reason is
  Conflicting Long and Short Signal.
- A signal state machine uses Eligible, Retry Delayed, Pending / Unknown, and
  Used. The saved snapshot includes contract, direction, analysis mode,
  timeframe, range identifier, range, high, low, proximity, and trigger-zone
  boundaries.
- A Long Signal Trigger Zone is the saved interval from `low` through the
  proximity-adjusted upper edge. A Short zone is the proximity-adjusted lower
  edge through `high`. These saved values remain authoritative for reset even
  when later market ranges move.
- A Used Long completes its Directional Reset only when Last Price reaches at
  least the original upper edge increased by reset distance. A Used Short resets
  only when Last Price reaches at most the original lower edge decreased by reset
  distance. Reset distance defaults to 1%.
- Completion of Directional Reset does not itself enter. Position and pending
  state must be clear, cooldown must have ended, price must later enter a valid
  current zone, and every current entry condition must pass.

### Account modes and Live authorization

- Paper Trading uses a persistent local Paper Account with a default Paper
  Starting Balance of 1,000 USDT or an explicitly selected amount. It may use
  only Gate.io public market, contract-rule, fee-rate, and funding-rate data.
  It never queries, displays, or mutates real balances, positions, orders, or
  credentials.
- Resetting or changing Paper Starting Balance requires confirmation and is
  allowed only with no Paper position or pending Paper entry. The reset and its
  reason are persisted and logged.
- Testnet and Live use distinct Gate.io endpoints, credentials/configuration,
  persisted account state, reconciliation, and risk counters.
- Mode changes are prohibited while the selected or target account has a
  position, pending entry, protective order, Emergency Stop, unresolved
  reconciliation/protection error, or Unmanaged Exchange State. No cross-mode
  state is auto-cancelled to permit a switch.
- Live activation always requires a current safety evaluation, Live Locked
  unlock intent, the exact `LIVE` confirmation, and absence of real blocking
  conditions. A restart, intentional service stop, or Emergency Stop restores
  Live Locked without disabling reconciliation or existing protection.
- Paper and Testnet verification may be persisted as separate advisory Live
  Readiness Records containing timestamp, engine build identifier, and
  Safety-Critical Profile Fingerprint. A build or safety-critical profile
  change makes the record stale.
- Missing or stale readiness records cause a prominent Arabic RTL real-money
  warning but do not block Live activation. This accepted decision supersedes
  the earlier requirement wording that treated current Paper/Testnet
  verification as a hard gate. Actual safety conditions and typed confirmation
  remain hard gates.

### Entry gate, sizing, and daily risk

- One central entry policy evaluates both automatic and manual requests. Manual
  requests bypass automatic-trading-enabled, range, proximity, automatic
  direction signal, and cooldown conditions only. They still require current
  market/history readiness, central locks, account-mode rules, one-trade state,
  balance, Safety Reserve, daily risk, exchange rules, reconciliation, and
  protection readiness.
- Before every exchange-backed entry, the engine verifies One-way mode, Cross
  margin, leverage of 1x, 5x, or 10x, real positions, pending entries, and
  conflicting orders. It may request Cross margin or leverage only when no
  conflict exists and must read back confirmation before continuing.
- Safety Reserve defaults to 10% with minimums of 0% for Paper, 5% for Testnet,
  and 10% for Live. Allocation choices are 25%, 50%, 75%, and 100%.
- Let Available Futures Balance be `A`, reserve fraction be `r`, allocation
  fraction be `P`, leverage be `L`, and conservative entry and exit fee rates be
  `f_entry` and `f_exit`. The Safety Reserve is `R = A * r`; Allocation Budget is
  `B = (A - R) * P`; maximum Allocated Margin is
  `M = B / (1 + L * (f_entry + f_exit))`.
- Both conservative fee inputs are current Taker rates, falling back to 0.10%
  per side. After quantity is rounded down to Gate.io's step, actual margin,
  notional, and fees are recomputed and must satisfy
  `actual margin + entry fee + exit fee + R <= A`. Quantities below the exchange
  minimum or failing final sufficiency are rejected, never rounded up.
- Maker and Taker rates are stored separately and refreshed periodically. The
  precise refresh interval remains configurable. Fee source, age, and fallback
  use are observable.
- Daily risk days start at 00:00 Asia/Riyadh. The baseline is total futures
  equity at that instant, including wallet balance and unrealized P&L. Later
  unrealized movement does not change the baseline or realized daily loss.
- Confirmed deposits increase and confirmed withdrawals decrease the baseline.
  Ambiguous transfers set Daily Risk Baseline Requires Review and block entries.
- A missing baseline after midnight is created from a fresh equity snapshot as
  a Late Daily Baseline. New Live and automatic entries remain blocked until it
  is durably stored and clearly reported.
- Realized daily net loss includes realized P&L, trading fees, and funding fees
  or credits. Default limits are 5% adjusted-baseline loss, three fully closed
  losing trades, and five automatic entries receiving any fill. Live loss
  percentage is mandatory, defaults to 5%, and is restricted to 1% through 5%.
- Reaching loss or losing-trade limits blocks manual and automatic entries.
  Reaching the automatic-fill limit blocks automatic entry only. Protective
  close and cancellation remain available.

### Order execution and idempotency

- Market and Limit entries are supported. Automatic entry defaults to Market;
  automatic Limit price derives from Last Price and configured offset, default
  0%, and expires after 60 seconds by default.
- Manual Limit Entry accepts an absolute price from the operator. It is validated
  exactly against Gate.io tick, range, side, and minimum rules and is never
  silently repriced. A Long at or above best Ask or Short at or below best Bid is
  classified as a Marketable Limit Order and budgeted as Taker execution.
- Immediately before Market submission, the engine captures a Last Price and
  order-book snapshot each less than one second old, consumes Ask liquidity for
  Long or Bid liquidity for Short, and computes volume-weighted expected price.
  Insufficient liquidity or deviation above 0.30% rejects without resizing,
  conversion, submission, or immediate retry.
- A pre-submission liquidity block leaves the signal Eligible and rate-limits
  reevaluation to once per five seconds. A definitive exchange rejection becomes
  Retry Delayed for at least 30 seconds and may retry only after the cause clears.
  An uncertain submission becomes Pending / Unknown and blocks retry and new
  entry until reconciliation proves the outcome.
- Every entry, TP, SL, cancellation, and close receives a persistent
  client-generated identity. Intent, payload fingerprint, account, state, and
  identity are committed before external submission. Timeout or missing response
  triggers lookup and reconciliation by identity, never blind resubmission.
- A pending entry consumes the account's one active trade state. Unfilled Limit
  expiry cancels the order and marks the signal Used. Any partial real fill marks
  it Used, cancels the remainder, and protects actual quantity at actual average
  fill.
- Paper Market Long fills at Last Price plus configured adverse slippage; Paper
  Market Short fills at Last Price minus it; default slippage is 0.10%. Paper
  Limit Long fills fully when Last Price is at or below Limit; Paper Limit Short
  fills fully when Last Price is at or above Limit; otherwise it remains pending
  until expiry.
- Paper Market entry and Stop Loss exit use Taker fees. Passive Paper Limit entry
  and TP use Maker fees; a Marketable Limit Order uses Taker fees. Paper does not
  simulate Gate.io's full liquidation or forced-liquidation process.

### Position protection and closure

- TP is enabled by default at expected net return equal to 30% of Allocated
  Margin. SL is enabled by default at expected net loss equal to 10%. Both use
  actual average fill, actual quantity, leverage, entry fees, estimated exit
  fees, and Gate.io contract/P&L rules.
- TP is a reduce-only Limit order. SL is a Mark Price-triggered reduce-only
  stop-market order. Protection payloads are capped to the reconciled remaining
  quantity and may never open or increase reverse exposure.
- A position is not considered protected until exchange confirmation exists.
  Rejection, absence, or unexpected cancellation produces TP Protection Error or
  Stop Loss Protection Error, blocks new entries, and initiates reconciliation
  and restoration unless explicitly disabled for that position.
- Partial TP fill reconciles remaining size and resizes both TP and SL as needed.
  A partially effective SL reconciles and repeatedly issues identity-protected,
  reduce-only Market closes for actual remainder until zero or an unrecoverable
  exchange error.
- Global protection settings affect only future entries. Open-position update or
  disable is a separate confirmed command. Live disable commands require exact
  `DISABLE TP` or `DISABLE SL`; opening Live with neither protection requires
  exact `UNPROTECTED POSITION`.
- Manual Close Position takes the central lock, reconciles actual size, cancels
  managed TP/SL, reconciles again, closes actual remainder reduce-only, handles
  partial fill with further reconciled closes, and completes only after zero
  position and no old managed protection are verified.
- A TP/SL full closure takes the lock, reconciles zero, cancels opposite managed
  protection, verifies old protection absence, records cause and realized result,
  then starts cooldown. Partial reduction never starts cooldown.
- Emergency Close Position durably activates Emergency Stop before invoking the
  Manual Close Position workflow. Failure or disconnection records a blocked or
  failed result. No close is queued for later; retry requires a fresh explicit
  command and fresh reconciliation. Emergency Stop remains active after success.

### Reconciliation, ownership, and recovery

- Gate.io is authoritative for Testnet and Live positions, orders, fills, and
  reported liquidation price. PostgreSQL is authoritative for RangeBot intent,
  identity, locks, configuration, confirmations, and audit history.
- Startup, reconnect, uncertain requests, protection changes, external account
  events, and closure workflows invoke reconciliation before any new entry.
  Unresolved mismatch blocks entry.
- An exchange position, entry, TP, or SL without matching persisted RangeBot
  identity is Unmanaged Exchange State. RangeBot displays its exchange details
  and continues read-only reconciliation but never adopts, cancels, resizes, or
  closes it, including during emergency workflows.
- Unmanaged Exchange State blocks entries, mode changes, and normal/emergency
  close or cancel mutations. Emergency Stop can still be activated. The operator
  resolves state on Gate.io and then requests read-only Refresh Reconciliation.
- A complete external closure of a managed position is recorded as External
  Gate.io Closure and triggers managed cleanup. An external partial reduction
  reconciles remaining size and resizes remaining protection.
- Market data is stale 10 seconds after the last valid live update. Reconnect
  readiness requires subscription confirmation, a fresh REST snapshot, at least
  two newer WebSocket price updates within 10 seconds, and account reconciliation.
- Stale or incomplete data blocks manual and automatic entries. Managed Close
  Position and Cancel Orders remain available when their required account/order
  reconciliation can be performed; they do not depend on a fresh signal price.
- Paper and Testnet automatic trading intent may resume after ordinary restart
  only when previously enabled and active contract, reconciliation, market data,
  history, protection, and daily-risk checks pass. Live never auto-unlocks.

### Profiles, security, observability, and deployment

- Profiles store future-facing validated configuration only. They never contain
  credentials, active positions/orders, history, cooldowns, signals, runtime
  locks, daily counters, or reconciliation state. Applying a profile requires a
  diff and confirmation, affects future activity only, and cannot unlock Live.
- A Safety-Critical Profile Fingerprint includes entry, sizing, risk, execution,
  protection, cooldown, daily-limit, analysis, and market-data-safety settings;
  purely visual preferences are excluded.
- Credentials are loaded from a local `.env`, excluded from source control and
  executable builds, protected with basic Windows file permissions, never shown
  in full, and redacted with request signatures, authentication headers,
  database passwords, and environment contents from every log path.
- Gate.io keys must disable withdrawals, use only required trading permissions,
  and use VPS IP allowlisting where supported.
- Structlog emits structured rotating local logs for lifecycle, connections,
  reconciliation, decisions, signal transitions, persistent identities, order
  lifecycle, slippage, protection, manual/emergency action, closure, P&L, fees,
  funding, risk baselines/counters, cooldown, profile changes, and redaction-safe
  failures. Every user-facing event has a stable code and Arabic explanation.
- The PySide6 UI uses centralized typography and direction handling, persistent
  high-risk banners, a dashboard state summary, condition details, activity log,
  confirmations, and Arabic Help Center. Final font, visual theme, icons, optional
  sounds, and final Help Center wording remain non-blocking presentation choices.
- Production packages separate engine, control UI, config, logs, and service
  assets. WinSW starts with Windows, restarts crashes, supports clean intentional
  stop, and does not close a position merely because the service stops.
- Before advisory Live Readiness is marked Verified, operations documentation
  covers and manually validates PostgreSQL backup and restore with standard
  tools. This verification-status requirement is not a Live activation gate.
  Restore requires engine restart, database validation, exchange reconciliation,
  protection validation, and continued entry blocking until successful.

## Testing Decisions

- Tests assert externally visible domain and application behavior: accepted or
  rejected commands, reason codes, state transitions, persisted identities,
  adapter calls, emitted events, and reconciled outcomes. They do not assert
  private helper structure, SQLAlchemy internals, Qt widget implementation, or
  incidental call ordering except where ordering is itself a safety guarantee.
- The primary test seam is the engine's application-service/localhost API
  contract. Tests drive real command handlers and persistence against controlled
  clocks and fake ExchangeAdapter/market streams, then assert returned snapshots,
  durable state, Arabic-capable reason events, and external requests. This is the
  highest seam that covers strategy through execution without a real exchange or
  UI process.
- Direct domain tests are reserved for dense financial invariants and state
  machines where exhaustive examples or property generation add value: range and
  proximity formulas, exact/interval boundaries, Directional Reset, allocation
  and round-trip fee budgeting, quantity rounding, TP/SL prices, daily baseline,
  and realized-loss accounting.
- Adapter contract tests use recorded/constructed Gate.io API v4 REST and
  WebSocket payloads to verify mapping, Decimal preservation, authentication
  redaction, reconnect sequencing, client identity lookup, partial fills,
  configuration confirmation, contract rules, fee fallback, and Unmanaged
  Exchange State detection. Routine automated tests never depend on Gate.io.
- Persistence integration tests use PostgreSQL and migrations to prove
  restart-critical state survives transaction boundaries and process recreation:
  request intents, Pending / Unknown, Used Signals and saved zones, cooldown,
  Emergency Stop, Live Locked, automatic intent, positions/protection, daily
  baselines/counters, profiles, and Live Readiness Records.
- UI tests exercise the engine boundary with a fake localhost service and verify
  Arabic RTL layout behavior, mixed-direction values, reconnect/snapshot refresh,
  condition explanations, risk banners, disabled controls, typed confirmations,
  stale preview rejection, and that no exchange submission path exists in the UI.
- Process/deployment tests verify that the engine survives UI exit and Remote
  Desktop disconnection, WinSW restarts a crash, intentional service stop is
  clean and does not close a position, Live relocks on restart, and Paper/Testnet
  resume only under the specified conditions.
- Hypothesis properties cover Decimal-only financial calculations, monotonic
  safety reserve and fee behavior, never-exceed-balance sizing, valid step
  rounding, non-reversing reduce-only quantities, proximity boundaries, stable
  Directional Reset, and daily-risk invariants.
- Fault-injection scenarios cover timeouts before and after exchange acceptance,
  missing responses, duplicate commands, REST/WebSocket disagreement, stale and
  out-of-order market data, history gaps, disconnect during submission or close,
  partial entry/TP/SL fills, protection rejection/cancellation, external closure
  or reduction, restart at every persisted state, and database write failure.
- Paper execution tests verify isolated balance/state, configurable starting
  balance, reset restrictions, adverse Market slippage, full-or-none Limit fills,
  expiry, Maker/Taker classification including Marketable Limit Orders, funding
  accounting, fee reserves, protection, cooldown, and daily limits.
- Explicit acceptance coverage maps TEST-001 through TEST-027 to automated or
  manual evidence. Gate.io Testnet checks are separately marked and run only on
  demand after Paper tests. Marking advisory Live Readiness as Verified requires
  manual backup/restore, service lifecycle, RTL visual review, and controlled
  Testnet reconciliation evidence; absence of that evidence does not block the
  typed `LIVE` activation flow when all current real safety checks pass.
- Security-focused tests verify localhost-only bindings, rejection/redaction of
  secrets in logs and errors, `.env` exclusion from builds, withdrawal-disabled
  key documentation, typed Live/protection confirmations, and absence of UI
  exchange credentials or direct order calls.
- There is no existing implementation-test prior art in the repository. The PRD
  acceptance criteria and accepted ADR scenarios are the normative test catalog
  until executable tests exist.

## Out of Scope

- Automatic contract discovery, ranking, recommendation, watchlist mutation, or
  backtesting.
- Automatic trading of more than one contract, multiple simultaneous positions,
  Hedge mode, multiple position legs, or exchanges other than Gate.io.
- Public APIs or dashboards, browser or mobile applications, multi-user access,
  and remote UI access outside Remote Desktop.
- Profitability promises, strategy optimization, trading recommendations, and
  complete Gate.io liquidation or forced-liquidation simulation in Paper.
- Automated backups, automated updates/uninstall, Windows Event Log integration,
  Sentry or external telemetry.
- DPAPI, Windows Credential Manager, a dedicated service account, advanced NTFS
  architecture, and a separate localhost API token.
- Automatically changing Hedge mode, closing positions, or cancelling unrelated
  or Unmanaged Exchange State to force a configuration or mode change.
- Final selection of Arabic font, visual theme, icon set, alert sounds, exact
  fee-refresh interval, or final Arabic Help Center copy.
- Implementation code and implementation tickets; this artifact defines the
  final implementation contract only.

## Further Notes

- The product requirements remain the authoritative catalog of requirement IDs
  and acceptance IDs. This specification translates them and the confirmed
  domain decisions into an implementation-ready contract without weakening any
  safety rule.
- Accepted ADR-0007 supersedes ADR-0006 and the earlier hard-gate wording for
  Paper/Testnet verification. Readiness is advisory; current safety checks,
  Live Locked handling, and exact `LIVE` confirmation are mandatory.
- Accepted ADR-0001 through ADR-0005 define Paper Account isolation, fee-aware
  Allocation Budget sizing, fresh-action Emergency Close Position, read-only
  handling of Unmanaged Exchange State, and stable Directional Reset semantics.
- No blocking product decision remains. Non-blocking presentation and timing
  choices must be made without changing the safety or acceptance behavior in
  this specification.
- The specification is ready to be decomposed into tracer-bullet implementation
  tickets. Paper Trading must be implemented and verified before Testnet work is
  treated as complete. Testnet evidence is recommended before operator use of
  Live, but its absence must never block typed `LIVE` activation when all current
  real safety checks pass.
