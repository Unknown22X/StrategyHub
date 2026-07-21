# Strategy, coin setup, opportunity, approval, and deployment workflow

Updated: 2026-07-19

This document describes the implemented RangeBot product workflow introduced by
migration `0029_strategy_workflow`. It replaces the old product assumption that a
saved strategy, one coin configuration, and one running bot are the same object.
The existing `StrategyInstance` runtime remains the execution adapter so its run,
decision, ownership, and trade history are preserved.

## 1. Domain model

### Strategy implementation

A registered Python implementation and its capability metadata. This is an internal
engine concept. It owns the configuration schema, supported timeframes,
scanner/backtest support, implementation version, and evaluator factory.

### Strategy Template

An immutable built-in product definition projected from one registered
implementation. Its stable ID is `builtin:<type_id>`. A Template exposes its English
strategy name, implementation version, capabilities, supported timeframes and
directions, and configuration schema. It cannot be edited, archived, or deleted by
the user.

### Strategy Preset

A user-owned editable set of defaults layered over a compatible Template. Presets
contain name and description, default timeframe and direction, strategy
configuration, execution/DCA/risk defaults, status, and immutable revisions.

The records historically named `strategy_template` are preserved in place and
exposed as Presets. Their IDs and revision rows are not rewritten, so existing coin
setups, Backtests, deployments, and audit history keep their original references.
The legacy `/v1/strategy-templates` API remains a compatibility alias; new clients
use `/v1/strategy-presets`.

Updating a Preset creates a new revision. Existing coin setups and Strategy
Instances remain pinned to the revision they were created from and never change
silently.

### Strategy Instance

A saved runnable configuration created from exactly one immutable Template and,
optionally, one Preset revision. The Instance stores `template_id`,
`template_version`, `preset_id`, and `preset_revision` alongside its effective
configuration. Existing Instance IDs, runs, decisions, Trades, ownership, and
deployments remain unchanged by migration `0033_strategy_template_preset_lineage`.

### Strategy Coin Setup

A configured use of one user Preset revision, backed by its compatible immutable
Strategy Template, on one Gate.io USDT perpetual symbol. A setup stores:

- exchange, market type, symbol, and quote currency;
- current price, observation timestamp, and `fresh`/`delayed`/`unavailable` state;
- pinned template revision;
- timeframe and direction;
- inherited configuration plus coin-specific overrides;
- inherited setup defaults plus a coin-specific override;
- backtest, approval, and deployment references;
- immutable setup revisions.

Saving a setup creates a new revision. The old backtest and approval remain in the
audit history but are not valid evidence for the new revision.

### Opportunity

A first-class persisted scanner result. It stores the source scan, strategy type
and version, symbol, exchange, market, quote currency, current price and timestamp,
scanner score, signal, qualifying factors, warnings, expiry, and status.

Statuses are:

- `new`;
- `reviewed`;
- `approved`;
- `rejected`;
- `ignored`;
- `expired`;
- `converted`.

Conversion creates one Strategy Coin Setup under a compatible Strategy Template
and records the conversion link. Rejected and ignored opportunities remain as
research records.

### Backtest Run

A deterministic historical simulation linked to both `setup_id` and
`setup_revision`. A result is valid approval evidence only while the setup remains
on that exact revision. Historical account P&L and backtest P&L remain separate.

### Setup Approval

An explicit Paper, Testnet, or Live approval bound to one setup revision. Normal
approval requires a `promising` assessment for that revision. The backend also
supports an explicit non-promising override with a confirmation contract for
operator-controlled exceptional use; the normal React flow does not expose an
accidental bypass.

Editing or rebasing a setup marks current approvals `stale`.

### Bot Deployment

An immutable snapshot created from one approved setup revision. It records:

- setup and template IDs and revisions;
- runtime `StrategyInstance` ID;
- Paper/Testnet/Live environment;
- strategy type and implementation version;
- complete effective configuration and setup defaults;
- approved backtest reference;
- lifecycle state.

Deployment states are `not_started`, `starting`, `running`, `monitoring`, `paused`,
`stopped`, and `error`. Later template or setup edits cannot mutate the snapshot.

## 2. User workflow

1. Create a reusable Strategy Template from the schema-driven Arabic form.
2. Add one or more Gate.io USDT perpetual coins manually, or convert a current
   scanner Opportunity.
3. Review the coin setup, current price freshness, inherited values, overrides,
   execution behavior, DCA support, and risk defaults.
4. Run a historical backtest for the current setup revision.
5. Review the assessment and metrics.
6. Explicitly approve the current revision for Paper, Testnet, or Live.
7. Create an immutable Bot Deployment.
8. Start trading or monitoring from the Trading page.
9. Pause or stop the deployment through the deployment lifecycle.
10. Any setup edit requires a new backtest and approval before a new deployment.

## 3. Primary navigation

The Arabic RTL frontend now has distinct primary destinations:

- `الرئيسية`: account and engine overview plus workflow attention counts;
- `الاستراتيجيات`: templates, revisions, coin setups, create/edit/archive/delete;
- `الفرص`: current-market scanning and opportunity review/conversion;
- `الاختبار التاريخي`: setup-bound backtests and stored research results;
- `التداول`: immutable bot deployments and lifecycle controls;
- `الأداء`: execution-account equity and P&L only.

Risk, Gate.io connection, backup/log operations, manual trading, and dashboard
customization remain secondary drawers. Trade History remains a distinct immutable
execution ledger.

## 4. Execution settings

Each template/setup has an explicit execution plan:

- entry order type, optional Limit price or formula, TIF, expiry, cancellation,
  and partial-fill behavior;
- take-profit execution;
- stop-loss execution;
- strategy-exit execution;
- manual-exit execution.

Safe defaults use Market execution. The current UI only enables Limit controls
where the underlying strategy and protection path support them safely. A Limit
exit without Market fallback produces a visible warning because it may not fill
and may leave exposure open.

DCA is represented in the domain for consistent inheritance and future extension.
The current UI enables multi-entry DCA only for the fixed-price-ladder strategy,
which already has a real execution implementation; other strategies show it as
unsupported instead of pretending it is active.

## 5. Persistence and compatibility migration

Migration `0029_strategy_workflow` adds:

- `strategy_template`;
- `strategy_template_version`;
- `strategy_coin_setup`;
- `strategy_coin_setup_version`;
- `strategy_setup_approval`;
- `strategy_opportunity`;
- `bot_deployment`;
- `setup_id` and `setup_revision` on `backtest_run`.

Every existing `StrategyInstance` is backfilled into one template and one coin
setup. Its original instance ID remains linked as the compatibility runtime. A
previously running or monitoring instance receives a migration approval and
matching deployment snapshot so restart behavior and history are not discarded.
Stopped instances require the new workflow before a future start.

Hard deletion is limited to unused drafts. Used templates and setups are archived
so versions, backtests, approvals, deployments, decisions, and trade ownership
remain auditable.

## 6. API surface

Main localhost endpoints:

- `GET/POST /v1/strategy-templates`;
- `GET/PUT/DELETE /v1/strategy-templates/{template_id}`;
- template versions and archive endpoints;
- `GET/POST /v1/strategy-setups`;
- `GET/PUT/DELETE /v1/strategy-setups/{setup_id}`;
- setup versions, price refresh, reset defaults, rebase, archive, backtest,
  approval, and deployment endpoints;
- `GET/PUT /v1/opportunities/{opportunity_id}` and conversion;
- `GET /v1/opportunities`;
- `GET /v1/bot-deployments` and deployment transition endpoints;
- `GET /v1/workflow/summary`.

Successful scanner runs are ingested into the Opportunity store. Direct starts of
workflow-backed runtime instances are routed through the deployment record and
approval check. Legacy runtime APIs remain available for compatibility and
history, but cannot bypass the new start gate for newly created workflow bots.

## 7. Safety invariants

- A deployment cannot be created without approval for the same setup revision and
  environment.
- A normal approval cannot be created without a promising current-revision
  backtest.
- Editing or rebasing invalidates evidence and approvals.
- A running or paused deployment must be stopped before its setup can be edited or
  archived.
- A template or setup with history is archived, not hard-deleted.
- Current price state is explicit; unavailable data is never replaced by a fake
  value.
- Deployment snapshots are immutable.
- Gate.io reconciliation, Emergency Stop, account risk, one-way position rules,
  market freshness, ownership, and central Order Manager checks still gate every
  actual order.
- Backtest research never contributes to Paper/Testnet/Live account P&L.

## 8. Verification completed

On 2026-07-19:

- workflow repository and API tests: 5 passed;
- all Python unit tests: 142 passed;
- all Python process tests: 18 passed;
- all Python UI/source tests: 14 passed;
- every integration test file executed in batches: 147 passed, 5 skipped;
- frontend TypeScript check: passed;
- frontend Vitest: 25 passed;
- frontend production Vite build: passed.

The one-shot Python/integration command exceeded the connector transport limit,
so the same complete set was executed in deterministic groups. Native packaged
Windows service/installer execution, real Gate.io Testnet acceptance, and browser
screenshot review remain external acceptance items and are not claimed here.
