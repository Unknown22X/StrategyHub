# RangeBot product workflow audit

Updated: 2026-07-19

This document records the product and domain state before the strategy-template,
coin-setup, opportunity, approval, and deployment workflow is changed. It is the
baseline for the requested product restructuring and is intentionally separate
from the full backtesting-engine implementation.

## 1. Current user workflow

The current React application has two main entry paths, but they end in the same
coin-bound `StrategyInstance` model.

### Create-first path

1. Open the strategy creation drawer from the dashboard or sidebar.
2. Choose a registered strategy type.
3. Enter a name, environment, symbol, timeframe, direction, margin, leverage,
   and strategy configuration in one form.
4. Save a stopped `StrategyInstance`.
5. Open its detail page.
6. Start trading or monitoring directly from that page.

A reusable strategy cannot currently be saved without choosing a coin. Using the
same rules on another coin requires duplicating or recreating the complete
instance.

### Discovery-first path

1. Open Discovery Lab.
2. Choose a strategy type and scanner/backtest configuration.
3. Run a current Gate.io market scan.
4. Select a ranked candidate.
5. Run a historical backtest from the same page.
6. Create a stopped `StrategyInstance` from the stored backtest.
7. Open the created instance and start trading or monitoring directly.

Discovery and backtesting are implemented and persisted, but a scanner candidate
is not a first-class opportunity with a review lifecycle. The combined page also
makes current-market discovery and historical evaluation look like one action.

## 2. Current route and sidebar structure

The React control panel does not currently use URL routes. `App.tsx` switches
between four in-memory views:

| View key | Visible destination | Entry points |
| --- | --- | --- |
| `dashboard` | Operations dashboard | `لوحة العمليات`, `الأداء`, `السجل والنشاط`, back buttons |
| `strategy` | One saved strategy instance | Saved-strategy sidebar rows and dashboard links |
| `discovery` | Combined scanner and backtest lab | `مختبر اكتشاف الفرص` and strategy detail action |
| `trades` | Immutable trade history | `سجل الصفقات` |

Risk management, Gate.io connection, backup/log operations, manual trading, and
dashboard customization open as drawers over the current view.

## 3. Duplicate or indistinguishable navigation

The following three sidebar items do not represent three distinct pages:

- `لوحة العمليات` opens the dashboard.
- `الأداء` also opens the dashboard.
- `السجل والنشاط` also opens the dashboard.

The dashboard contains P&L summaries, performance charts, positions, orders,
strategy information, alerts, and activity. This provides useful data, but the
sidebar labels imply separate destinations that do not exist.

`سجل الصفقات` is distinct. `مختبر اكتشاف الفرص` is also distinct, but it combines
opportunity discovery and historical backtesting in one long page.

## 4. How strategies are stored

A registered `StrategyTypeMetadata` describes a Python strategy implementation,
its JSON schema, supported timeframes, scanner/backtest capability, metrics, and
warnings.

A persisted `StrategyInstance` currently stores all of the following together:

- strategy type;
- user-facing name;
- Paper/Testnet/Live environment;
- one symbol;
- timeframe and direction;
- requested margin and leverage;
- the complete strategy configuration;
- running/monitoring lifecycle state.

The engine also stores immutable configuration revisions, runs, decisions, and
trade ownership. These histories are useful and must be preserved.

The current `StrategyInstance` is therefore closer to a configured coin bot than
to a reusable strategy template.

## 5. How coins are associated with strategies

The coin is stored directly in `strategy_instance.symbol`. There is no separate
relationship table and no parent strategy template. One instance can reference
one symbol only.

Changing the symbol edits the same instance and increments its revision. Adding
a second coin with the same strategy requires another independent instance,
which duplicates configuration and loses an explicit parent relationship.

## 6. How opportunities are discovered

Discovery Lab uses the registered strategy scanner and Gate.io public historical
market-data provider. A scan persists:

- scan request and strategy version;
- scan timestamp;
- ranked candidate symbols;
- score, signal, eligibility, explanation, reasons, warnings, metrics, data
  quality, completed candle count, and backtest readiness;
- per-symbol scan failures.

The scan is real and errors are shown during execution. Stored scan and backtest
history is available, although history-loading failures are currently hidden.

A candidate does not currently have an independent status such as reviewed,
approved, rejected, ignored, expired, or converted. It also lacks a stable
conversion link to a coin setup. The candidate UI does not consistently show a
first-class current price with its timestamp, exchange, and market.

## 7. How paper or live trading is started

The selected environment is stored on the strategy instance. A stopped or paused
instance can transition directly to `running` from its detail page. A monitorable
strategy can also transition directly to `monitoring`.

The engine still applies account, reconciliation, market-data, Emergency Stop,
risk, ownership, and order-manager safeguards before an actual entry. However,
the product workflow does not currently require:

1. a completed coin setup;
2. a linked backtest of the current revision;
3. a reviewed verdict;
4. explicit Paper or Live approval;
5. an immutable deployment snapshot.

Changing an instance creates a configuration revision, but there is no approval
record that becomes stale when the setup changes.

## 8. Incomplete, duplicated, misleading, or nonfunctional areas

- Strategy type, reusable strategy, one-coin configuration, and running bot are
  represented by overlapping concepts.
- A strategy cannot own multiple coin setups without duplicating the full
  instance.
- Discovery candidates have no review or conversion lifecycle.
- Current discovery and historical backtesting share one page and workflow.
- `الأداء` and `السجل والنشاط` are misleading duplicate dashboard links.
- Trading can be started without a backtest/approval product gate.
- There is no immutable deployment record or approved setup snapshot.
- Entry execution supports Market and Limit, but explicit take-profit,
  stop-loss, and manual/strategy exit execution types are not first-class
  strategy/setup fields.
- There is protected deletion for active or historically owned instances, but no
  normal archive lifecycle.
- Candidate and setup price presentation is incomplete; timestamp and stale or
  unavailable state are not consistently prominent.
- Backtest results are stored by strategy type, symbol, and request, rather than
  by an immutable coin-setup version.
- The current dashboard already has useful environment-specific P&L and does not
  mix backtest P&L into Paper/Live account totals. That behavior should remain.

## 9. Proposed information architecture

Use one clear destination per primary task:

- `الرئيسية`: account P&L, balances, active bots, open positions, recent
  activity, and setups requiring attention.
- `الاستراتيجيات`: reusable strategy templates, template versions, associated
  coin setups, create strategy, and archive views.
- `الفرص`: current-market scanner, qualifying reasons, review status, and
  conversion into a coin setup.
- `الاختبار التاريخي`: start a backtest, stored runs, comparisons, and results.
- `التداول`: bot deployments, positions, pending orders, fills, and activity log.
- `الأداء`: realized/unrealized P&L, equity, fees, and strategy/coin/bot history.

Risk, connection, backup, logs, manual trading, and display settings may remain
secondary drawers where that keeps the interface simpler.

During migration, old in-app destinations should resolve to the nearest new view.
If URL routing is introduced later, old URLs should remain temporary redirects,
not permanent duplicate pages.

## 10. Proposed domain relationships

### Strategy Type

The registered Python implementation and capability metadata. This remains the
extension point for built-in and Codex-added strategy behavior.

### Strategy Template

A reusable user-owned rule set with `draft`, `active`, or `archived` status. It
references a Strategy Type and has immutable template versions. A custom strategy
must use the same template/version contracts and may label unsupported fields as
read-only rather than pretending they are visually editable.

### Strategy Coin Setup

A configured application of one Strategy Template Version to one exchange,
market, and symbol. It owns coin-specific overrides, execution types, market-price
snapshot metadata, backtest state, approval state, trading state, and immutable
setup versions. One template may own many setups.

### Opportunity

A persisted scanner candidate with source scan, symbol, exchange, market, price,
price timestamp, strategy compatibility, score, qualifying factors, expiry, and
review status. Conversion creates or links exactly one Strategy Coin Setup.
Rejected opportunities remain research records and never become setups.

### Backtest Run

A deterministic simulation linked to an immutable Strategy Coin Setup Version
snapshot. Editing the setup creates a new version and makes the older result
historical rather than valid approval evidence for the new version.

### Bot Deployment

An immutable snapshot of an explicitly approved setup version and strategy
version. It records Paper/Testnet/Live mode and `not_started`, `starting`,
`running`, `paused`, `stopped`, or `error` state. Later edits to the template or
setup cannot silently mutate a running deployment.

## 11. Low-risk migration approach

Do not replace the working engine or delete current history in one migration.
Use staged compatibility:

1. Add template, template-version, coin-setup, setup-version, opportunity,
   approval, and deployment tables alongside existing tables.
2. Backfill each existing `StrategyInstance` into one template and one coin setup
   while preserving the original instance ID as a compatibility/deployment
   reference.
3. Route new creation through templates and setups while existing APIs continue
   to read compatibility projections.
4. Link backtests to setup versions and invalidate approval when a new setup
   version is saved.
5. Add explicit approval and immutable deployment creation before changing the
   engine start endpoint.
6. Migrate the UI page by page, then remove obsolete duplicate paths only after
   tests prove history and runtime restoration remain intact.

## 12. Numeral and localization policy

The interface remains Arabic and RTL, but all displayed digits must use Latin
English numerals (`0-9`). Number, compact-number, duration, and date/time
formatters must use the `latn` numbering system. Source text must not contain
Arabic-Indic (`٠-٩`) or Eastern Arabic/Persian (`۰-۹`) digit literals.
Financial values and symbols remain isolated in LTR sections where appropriate.

## 13. Planned implementation slices

1. Establish the documented baseline and Latin-digit formatting contract.
2. Clean up primary navigation into distinct dashboard, strategies,
   opportunities, backtesting, trading, and performance destinations.
3. Add Strategy Template and Strategy Coin Setup persistence with compatibility
   backfill and APIs.
4. Build strategy-template creation and the manual/opportunity Add Coin flow.
5. Add explicit entry/exit execution settings, setup versioning, archive, and
   safe delete.
6. Promote scanner candidates into first-class opportunities and separate
   current scanning from historical backtesting.
7. Link backtests to setup snapshots, add approval invalidation, and create the
   setup review page.
8. Add immutable deployment snapshots and enforce explicit Paper/Live approval
   before start.
9. Complete acceptance tests, responsive/RTL verification, production build, and
   regression review.

## 14. Implementation result

The planned code restructuring was completed on 2026-07-19 without replacing the
existing execution engine or discarding `StrategyInstance` history.

Implemented outcomes:

- primary navigation now has distinct Home, Strategies, Opportunities,
  Backtesting, Trading, and Performance destinations;
- Strategy Templates and immutable template revisions are persisted independently
  from coins and environments;
- each template can own multiple Strategy Coin Setups pinned to immutable template
  revisions, with inherited configuration, coin overrides, explicit execution
  defaults, DCA capability, risk defaults, current price, timestamp, and freshness;
- scanner candidates are persisted as Opportunities with review, approval,
  rejection, ignore, expiry, and conversion lifecycle;
- Backtesting is separate from current-market Opportunities and every setup-bound
  run records both setup ID and setup revision;
- setup edits and rebases create a new revision and invalidate prior approval
  evidence;
- Paper, Testnet, and Live approval is explicit and revision-bound;
- Bot Deployments preserve immutable approved snapshots and route start,
  monitoring, pause, and stop through the existing runtime adapter;
- used records archive instead of being hard-deleted, while unused drafts retain a
  safe delete path;
- migration `0029_strategy_workflow` backfills existing saved instances and
  preserves runtime IDs, decisions, runs, ownership, and trade history;
- Arabic RTL formatting keeps Latin digits and displays unavailable or delayed
  price state explicitly rather than fabricating fallback data.

The full implemented contract, API surface, migration behavior, safety invariants,
and verification evidence are documented in `docs/strategy-workflow.md`.

Code verification completed with 321 passing Python tests and 5 intentional skips,
25 passing frontend tests, a clean TypeScript check, and a successful production
Vite build. Native Windows packaging/service execution, browser screenshot review,
and real Gate.io Testnet acceptance remain external checklist items rather than
unimplemented product code.
