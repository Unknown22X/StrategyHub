# StrategyHub Build Week Changes

## Scope boundary

StrategyHub is the public submission name. The repository and stable internal runtime continue to use RangeBot identifiers.

The checkpoint before the approved Build Week implementation is:

```text
e7b362661fc0e1c2b827c8eaef54912d48e360e3
Checkpoint current RangeBot implementation
```

That checkpoint already contained a local Python/FastAPI engine, React control panel, dynamically registered Strategies, Paper trading foundations, Gate.io integration boundaries, central Order and risk services, Backtesting foundations, persistence, tests, and Windows packaging foundations.

The commits below are the focused Build Week implementation after that checkpoint.

## P0.1 — Authoritative trading environment lifecycle

**Commit:** `0253bc0dd2a1c753c1c4cac4e0b5a80809ad50cc`

**Changed:**

- Made active engine and exchange-adapter environment authoritative.
- Separated requested/stored environment from actual activated runtime mode.
- Rebuilt environment-specific public and private providers together.
- Invalidated stale reconciliation, account, risk, and market state during transitions.
- Preserved the adapter-mode mismatch hard blocker.
- Documented Paper public-market policy.

**Verification:** focused runtime, provider, environment, credential-isolation, exchange-safety, frontend, typecheck, build, and Ruff suites.

**Limitation:** real Windows service transition and real Gate.io Testnet acceptance remained manual external checks.

## P0.2 — Safe zero-Quantity Preview

**Commit:** `edd63576fc16f7b471be53d3c647672908dfaa8c`

**Changed:**

- Prevented `Protection calculation requires positive base quantity.` from escaping for normal invalid input.
- Validated rounded Quantity before protection calculations.
- Returned structured `can_submit=false` Preview issues for zero and below-minimum Quantity.
- Added raw/rounded/minimum Quantity and approximate minimum Margin context.
- Ensured invalid submission never reaches an exchange adapter.

**Verification:** Order Manager unit tests and manual Order API integration tests, including Margin, balance-percentage, direct Quantity, valid protection, and rejected submission paths.

## P0.3 — Reconciliation coordinator and accurate readiness

**Commit:** `2aac84f84f25f514560523f0675c9c5b76ab5bb7`

**Changed:**

- Removed full blocking Gate reconciliation from the normal Preview critical path.
- Added stored authoritative snapshot freshness, background refresh, timeout, and single-flight coordination.
- Preserved exact risk and reconciliation reason codes.
- Distinguished real policy limits from initialization and synchronization failures.
- Added structured reconciliation checks, timestamps, sanitized errors, and Preview diagnostics.

**Verification:** reconciliation coordinator, account-risk, manual Preview, timeout, exception, freshness, deduplication, and frontend readiness tests.

**Limitation:** real Gate latency was not measured with production Credentials.

## P0.4 — Riyadh daily baseline and Risk Management controls

**Commit:** `878ee508e6f4d34bbd49fe599133bb23b2f21bec`

**Changed:**

- Added immutable environment-specific daily equity baselines for the Riyadh trading day.
- Made baseline initialization idempotent after an authoritative account snapshot.
- Prevented baseline reset after losses or restart.
- Added explicit persisted enabled/disabled state for daily equity-loss, losing-Trades, and automatic-entry limits.
- Added Live real-funds confirmation before disabling important optional policy limits.
- Kept unrelated safety controls mandatory.

**Migration:** additive account-risk policy and daily-baseline migration preserving existing data.

**Verification:** account-risk policy, daily baseline, migration, environment isolation, Preview reason-code, frontend toggle, typecheck, build, and Ruff tests.

## P0.5 — Paper and Testnet lifecycle verification

**Commit:** `3f00a308bd4475ba4bb7ed8640cef8180e55295a`

**Changed:**

- Added automated verification for environment selection, Credential profile isolation, reconciliation, Preview, submission routing, Position/protection lifecycle, and closing.
- Added exact manual Windows and Gate.io Testnet acceptance instructions for checks unavailable in the automated environment.

**Verification:** mock/automated Paper and Testnet suites.

**Limitation:** no real Gate.io Testnet Credentials were available; real Testnet UI/order visibility remains a manual acceptance step.

## P1.1 — Strategy Template, Preset, and Instance model

**Commit:** `b02ff26bcd805449b68e20c70529621c1e2ddee7`

**Changed:**

- Exposed registered built-in Strategies as immutable Strategy Templates.
- Preserved existing editable persisted template records as user Presets.
- Allowed Strategy Instances to reference a built-in Template and optional Preset.
- Preserved existing IDs, Backtests, Trades, deployments, ownership, and history.

**Migration:** `0033_strategy_template_preset_lineage`.

**Verification:** model, migration, API, compatibility, and frontend source tests.

## P1.2 — Optional Backtesting and immutable Strategy Run snapshots

**Commit:** `c76ae3c653c6f11f2abd352426dc3fbf1f89c2f6`

**Changed:**

- Added immutable persisted Strategy Run configuration snapshots.
- Made runtime evaluation, signals, risk, Margin, Leverage, and Order sizing use the Run snapshot.
- Allowed direct Paper start without a Backtest.
- Required authoritative readiness for Testnet and explicit real-funds confirmation plus complete safety for Live.
- Added structured start readiness and Backtest states: never, current successful, current failed, and stale.
- Made Never Backtested a warning rather than a universal blocker.
- Added restart and recovery from stored snapshots.

**Migration:** `0034_strategy_run_configuration_snapshot` with compatibility backfill.

**Verification recorded during the milestone:** focused behavior and quality 22 passed; atomic snapshot/workflow 21 passed; Strategy regressions 42 passed; Order/risk/reconciliation/runtime 38 passed; exchange/Testnet safety 46 passed with 5 external/manual skips; Windows frontend 40 passed with typecheck and build.

## P1.3 — Strategy lifecycle

**Commit:** `717183f91f2f80d766f7e128bae098ee549f5025`

**Changed:**

- Added Pin/Unpin, Archive, Restore, duplicate, and deletion readiness.
- Allowed permanent deletion only for unused Instances with no protected history.
- Required used Instances to remain archived.
- Added Archived Strategies page and sidebar state shortcuts.

**Migration:** `0035_strategy_instance_lifecycle`.

**Verification recorded during the milestone:** lifecycle/migration/source 7 passed; Strategy regressions 28 passed; Windows frontend 41 passed with typecheck and build; Ruff passed.

## P1.4 — Strategy Instance operations page

**Commit:** `8726da7acff09a9b0ad5c46cc7f0a0989a735221`

**Changed:**

- Prioritized authoritative Realized PnL, Win Rate, realized Drawdown, Trades, fees, price/freshness, Position, Orders, health, Run duration, and recent activity.
- Kept configuration and revision information secondary.
- Refused to guess Strategy ownership when attribution is unavailable.

**Verification recorded during the milestone:** Windows frontend 41 passed with typecheck and build; focused source/quality 3 passed.

**Limitation:** Paper pending-entry ownership is not displayed as Strategy-owned when the current response lacks authoritative ownership fields.

## P1.5 — Opportunities redesign

**Commit:** `c51390d6a9426e15639ee5bd9c8ee6f6310d9e03`

**Changed:**

- Made Review open meaningful details.
- Made Shortlist explicit and non-trading.
- Made Ignore hide the active item with Undo support.
- Kept incompatible scanner Strategies visible and disabled with an explanation.
- Allowed creating a stopped Paper Strategy Instance for the coin using another compatible built-in Strategy, including Fixed Price Ladder.

**Verification recorded during the milestone:** workflow/source tests passed; Windows frontend 41 passed with typecheck and build; Ruff passed.

## P1.6 — Gate contract picker and live price state

**Commit:** `64dc2a418d6da86e15c2b34630142d8412b36c56`

**Changed:**

- Added searchable Gate.io USDT perpetual contract options.
- Kept manual symbol fallback with backend validation.
- Displayed public-market source, environment, timestamp, and fresh/stale state.
- Added the picker to Manual Order, Strategy creation/editing, and Add Coin.
- Kept configured, running, pinned, viewed, and restored Strategy symbols subscribed while removing archived-only targets.

**Verification recorded during the milestone:** backend catalog/subscription tests 6 passed; Windows frontend 42 passed with typecheck and build; Ruff passed.

## P1.7 — Backtesting reliability and beginner wizard

**Commit:** `91ef1e924f16c610d8f33f6ea03aba319b8e4347`

**Changed:**

- Added **Beginner — realistic and conservative** preset.
- Collapsed advanced execution assumptions.
- Made Step 5 explicitly final and removed the misleading disabled Next action.
- Marked hypothesis and Setup Review as optional.
- Added bounded polling, cancellation, retries/backoff, request timeouts, reusable frontend request handling, structured failure code/stage, sanitized diagnostics, and visible history-load failures.
- Added persisted Backtest diagnostics and interrupted-run handling.

**Migration:** `0036_backtest_diagnostics`.

**Verification after submission scope freeze:** portfolio Backtesting, diagnostics migration, historical market retry, and wizard source tests 14 passed.

**Scope decision:** retained because it was already complete and committed, directly improves the required demo, has an additive migration, and reverting it after completion would create more release risk than retaining the passing implementation.

## Submission finalization verification

The focused final audit after the feature freeze produced:

- Paper Order Manager, Manual Preview, Paper submit, Position, protection, close, market entry, and trailing stop: **34 passed**.
- Strategy direct start, immutable Run snapshots, runtime recovery, and lifecycle: **20 passed**.
- Opportunities and contract picker wiring: **5 passed**.
- Risk Management and risk migrations: **9 passed**.
- Environment separation and safety: **48 passed, 5 skipped**.
- Startup, launcher, localhost binding, static frontend, lifecycle, deployment, and release assets: **35 passed**.
- Database migration group through `0036`: **11 passed**.
- P1.7 focused reliability group: **14 passed**.
- Secret scan: **731 text files scanned, zero candidate matches, zero items requiring review**.

The five environment-safety skips are real Gate.io/Windows manual acceptance checks, not hidden passing claims.

## Safety statement

No Live Credentials, Live Orders, real Gate.io transactions, or real funds were used during Build Week implementation or automated verification.
