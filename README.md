# StrategyHub

> A local-first trading strategy operations application built to help my dad understand, test, and safely operate crypto futures Strategies without needing to learn every internal exchange or bot term first.

StrategyHub is the public project name. The stable internal engine, Python package, Windows service, executable, installer filename, and local data folder retain the **RangeBot** name to avoid risky release-time renames.

## Why I built it

My dad wanted a clearer way to work with trading Strategies: choose a coin, understand what a Strategy will do, test it safely, see its real state and performance, and avoid accidentally mixing Paper, Testnet, and Live funds.

The original project already had a local Python engine, React dashboard, strategy registry, Paper trading, Gate.io integration boundaries, Backtesting, and risk controls. During OpenAI Build Week, I used GPT-5.6 and Codex to audit the complete lifecycle and turn the existing application into a safer, more understandable Strategy operations product.

The Build Week focus was not profit prediction. It was trustworthy state, safer execution, clearer lifecycle rules, and a reliable Paper demo.

## What StrategyHub does

- Runs as a localhost-only Windows application with a background engine service.
- Separates **Paper**, **Testnet**, and **Live** using authoritative runtime state.
- Supports manual futures Order Preview and submission through one central validation path.
- Simulates Paper Orders, Positions, PnL, fees, Take Profit, Stop Loss, and Emergency Stop.
- Separates immutable built-in **Strategy Templates**, reusable user **Presets**, and user-created **Strategy Instances**.
- Allows direct Paper Strategy start without requiring a Backtest.
- Stores immutable Strategy Run configuration snapshots for execution and recovery.
- Shows attributed performance, Position, Orders, health, live price state, and recent activity.
- Supports Pin, duplicate, Archive, Restore, and safe deletion rules.
- Provides scanner Opportunities with Review, Shortlist, Ignore/Undo, Coin Setup creation, and compatible Strategy Instance creation.
- Includes a searchable Gate.io USDT perpetual contract picker with manual fallback and visible price freshness.
- Includes deterministic Backtesting with a conservative beginner preset, cancellation, bounded polling, retries, and structured failure diagnostics.
- Provides configurable daily Risk Management limits and durable Emergency Stop.

## Screenshots

Add final screenshots before submission:

1. `docs/screenshots/01-paper-dashboard.png` — StrategyHub dashboard with the PAPER badge.
2. `docs/screenshots/02-paper-order-preview.png` — BTC_USDT Market Long Preview with Quantity, Margin, fees, Take Profit, and Stop Loss.
3. `docs/screenshots/03-paper-position.png` — resulting Paper Position with protection and PnL.
4. `docs/screenshots/04-strategy-instance.png` — Running Strategy Instance operations page.
5. `docs/screenshots/05-opportunities.png` — Opportunity Review and compatible Strategy selection.
6. `docs/screenshots/06-backtest-result.png` — completed Backtest metrics and warnings.
7. `docs/screenshots/07-risk-management.png` — daily limit toggles and Emergency Stop.

Do not include API Credentials, private account data, or fabricated performance.

## Technology stack

### Backend

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy and Alembic-style ordered migrations
- SQLite for local application state
- HTTPX and WebSockets for Gate.io integration
- Pytest, Hypothesis, and Ruff

### Frontend

- React 19
- TypeScript
- Vite
- Vitest and Testing Library

### Windows release

- PyInstaller
- WinSW background service wrapper
- Inno Setup 6
- Windows DPAPI for stored exchange Credentials

## Architecture overview

```text
React dashboard
      │ localhost HTTP
      ▼
FastAPI engine ── Strategy registry / runtime runner
      │           Order Manager / Risk / Reconciliation
      │           Paper account / Backtesting / Opportunities
      ▼
SQLite repositories and immutable audit/history records
      │
      ├── Public Gate.io REST/WebSocket market data
      └── Environment-bound Testnet or Live adapter when explicitly enabled
```

Important boundaries:

- The UI displays the authoritative active engine environment.
- Saving an environment preference does not pretend the adapter switched.
- Paper never needs private Gate.io Credentials.
- Testnet and Live Credentials, account snapshots, reconciliation, and risk baselines are isolated.
- Live submission remains fail-closed when safety readiness is incomplete.
- Existing Strategy Runs evaluate from their stored snapshot, not mutable current settings.

## Windows installation

Download or build:

```text
release\RangeBot-Setup.exe
```

Run the installer as administrator. The installed launcher appears as RangeBot for compatibility, while the dashboard identifies the public project as StrategyHub.

Default mutable data location:

```text
%LOCALAPPDATA%\RangeBot\
```

The application and API are available only on:

```text
http://127.0.0.1:8765/app/
```

See [USER_GUIDE.md](USER_GUIDE.md) and [BUILD.md](BUILD.md).

## Development setup

### Requirements

- Windows 10 or 11, 64-bit
- Python 3.12+
- `uv`
- Node.js 22 LTS; the final Build Week verification uses Node `v22.22.0`
- npm

### Install dependencies

From the repository root:

```bat
uv sync --group dev
cd frontend
npm ci
cd ..
```

### Run the backend in safe Paper mode

```bat
uv run python -m rangebot.engine.main --mode paper --enable-public-websocket
```

This starts the engine on `127.0.0.1:8765`. It does not enable private exchange access or exchange Order submission.

### Run the frontend development server

In a second terminal:

```bat
cd frontend
npm run dev
```

Open:

```text
http://127.0.0.1:5173/app/
```

Vite proxies `/v1` and `/health` to the local engine.

### Run the compiled frontend through FastAPI

```bat
cd frontend
npm run build
cd ..
uv run python -m rangebot.engine.main --mode paper --enable-public-websocket
```

Then open `http://127.0.0.1:8765/app/`.

## Paper demo

Use the exact recording route in [DEMO.md](DEMO.md).

Recommended preparation:

- authoritative environment: Paper;
- symbol: `BTC_USDT`;
- conservative Leverage: `1x`;
- one existing stopped Paper Strategy Instance with a clear name;
- one completed short Backtest already saved;
- no exchange Credentials visible;
- Emergency Stop off before the Order demo, then shown at the end.

Paper uses real public market information when available, but all private account state, Orders, Positions, and PnL are local simulation. No real funds are used.

## Paper, Testnet, and Live

| Environment | Purpose | Private Credentials | Real funds |
| --- | --- | --- | --- |
| Paper | Local simulation and demonstrations | No | No |
| Testnet | Gate.io Futures Testnet verification | Testnet profile only | No |
| Live | Real Gate.io trading | Live profile only | **Yes** |

The Credential-profile selector edits Credentials. It does not silently switch the active engine environment.

## Gate.io integration

StrategyHub can use Gate.io public futures REST and WebSocket data for:

- USDT perpetual contract discovery;
- contract rules;
- current prices and freshness;
- completed historical candles;
- funding data used by Backtesting.

Testnet and Live private integration remains environment-bound and requires explicit readiness. Public Paper market data follows the documented policy of using public Live market data without Live Credentials or private account state.

## Safety and Risk Management

- Authoritative environment/adapter mismatch remains a hard blocker.
- Invalid or zero Quantity returns a structured invalid Preview; it is never silently increased.
- Order Preview shows the main cause and next action rather than exposing internal exceptions.
- Reconciliation and risk reason codes distinguish missing data from actual reached limits.
- Daily equity-loss, losing-Trades, and automatic-entry limits have explicit persisted enable/disable states.
- Disabling an optional limit never disables Credentials, environment, balance, freshness, Quantity, unmanaged-state, or protection checks.
- Live requires explicit real-funds confirmation.
- Emergency Stop persists through restart.

## How GPT-5.6 was used

GPT-5.6 helped:

- explain trading concepts and lifecycle terminology in beginner-friendly language;
- audit the UX and safety requirements;
- separate genuine risk blockers from temporary readiness and software errors;
- design the Strategy Template, Preset, Instance, and immutable Run model;
- plan the environment lifecycle, reconciliation, risk baseline, and Backtesting changes;
- review test results and keep the release claims honest;
- prepare the demo, README, limitations, and submission materials.

GPT-5.6 did not provide trading signals or promise returns.

## How Codex was used

Codex, through the local repository workspace, accelerated implementation by:

- inspecting frontend, backend, migrations, tests, service configuration, and packaging;
- applying focused code changes milestone by milestone;
- creating safe database migrations;
- adding unit, integration, process, frontend, and migration tests;
- running Windows Node `v22.22.0` frontend verification;
- reviewing diffs and creating focused commits;
- preserving the existing repository and trading-safety boundaries.

The final implementation remains reviewable in the commit history and [BUILD_WEEK_CHANGES.md](BUILD_WEEK_CHANGES.md).

## Important technical decisions

- Keep the local engine and API bound to `127.0.0.1`.
- Use Paper as the safe fresh-install default.
- Treat runtime engine mode as authoritative.
- Rebuild environment-specific adapters and invalidate stale state during transitions.
- Keep adapter-mode mismatch validation.
- Perform reconciliation outside the normal Preview critical path.
- Store immutable environment-specific Riyadh daily baselines.
- Store immutable Strategy Run snapshots.
- Archive used Strategies rather than deleting history.
- Show unavailable ownership or market data honestly instead of guessing.
- Keep the stable internal RangeBot identifiers during submission finalization.

## Testing

### Focused release checks

```bat
uv run pytest tests/unit/test_order_manager.py tests/integration/test_manual_order_api.py tests/integration/test_paper_central_order_api.py tests/integration/test_paper_operations_api.py -q
uv run pytest tests/integration/test_strategy_start_readiness.py tests/integration/test_strategy_runtime_context.py tests/integration/test_strategy_instance_lifecycle.py -q
uv run pytest tests/integration/test_environment_runtime_api.py tests/integration/test_exchange_safety_api.py -q
```

### Full Python suite

```bat
uv run pytest -q
```

### Frontend

```bat
cd frontend
npm test
npm run typecheck
npm run build
```

### Ruff

```bat
uv run ruff check .
uv run ruff format --check .
```

### Windows installer

```bat
build_release.bat
```

The build fails closed if any required dependency, test, compiled artifact, or installer output is missing.

## Build Week changes versus pre-existing work

### Before Build Week

The repository already contained the RangeBot local engine, React control panel, strategy registry, Paper account, exchange integration boundaries, central Order Manager, risk architecture, Backtesting foundations, persistence, and Windows packaging foundations.

### Completed during Build Week

Build Week work made the active environment authoritative, fixed zero-Quantity Preview crashes, moved reconciliation off normal Preview, implemented accurate risk readiness and daily baselines, added environment-separated trading verification, separated Template/Preset/Instance concepts, added direct Paper starts and immutable Run snapshots, completed Strategy lifecycle and operations pages, redesigned Opportunities, added the contract picker and live price state, and hardened Backtesting reliability and beginner UX.

See the exact commit-by-commit record in [BUILD_WEEK_CHANGES.md](BUILD_WEEK_CHANGES.md).

## Known limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md). The most important ones are:

- no real Gate.io Testnet acceptance was performed in this automated environment;
- no Live Credentials, Live Orders, real transactions, or real funds were used;
- public market data requires internet access and may be stale or unavailable;
- the public project name is StrategyHub while stable Windows/internal identifiers remain RangeBot;
- some advanced screens still mix Arabic explanations with approved English trading terms;
- results from Backtesting or Paper are not evidence of future profitability.

## Roadmap

After the submission freeze:

- complete manual Gate.io Testnet acceptance on Windows;
- expand component and browser-level end-to-end tests;
- refine remaining localization and terminology consistency;
- continue accessibility and responsive-layout review;
- add richer performance charts only when backed by authoritative attribution;
- evaluate additional Strategies without weakening the safety lifecycle.

## Safety disclaimer

Crypto futures and Leverage are high risk. StrategyHub is educational and operational software, not financial advice. Paper and Backtest results can differ materially from real execution. Validate with Paper, then Testnet, before considering Live.

**Build Week safety statement:** no Live Credentials, Live Orders, real Gate.io transactions, or real funds were used during Build Week implementation or automated verification.
