# ADR 0008: Retain the Python engine and centralize local persistence

- Status: Accepted
- Date: 2026-07-16

## Context

RangeBot already has a working Python/FastAPI engine, Gate.io adapter boundary,
Alembic migration history, risk controls, reconciliation behavior, and Paper
Trading implementation. The existing PySide control UI stores several visual
and order-form preferences through `QSettings`, while the engine's default
SQLite path and credential file are relative to the repository or packaged
application directory.

The product direction calls for a React and TypeScript localhost control panel,
but the visible frontend must remain independent from trading execution. A full
technology rewrite would place stable trading behavior, migrations, and safety
controls at unnecessary risk.

## Decision

1. Keep the Python/FastAPI engine as the authoritative local process for trading,
   risk, reconciliation, calculated values, and persistence.
2. Move mutable local state to a current-user application root. On Windows this
   is `%LOCALAPPDATA%\RangeBot`; tests and non-Windows development may use the
   explicit `RANGEBOT_HOME` override.
3. Use SQLite as the installed application's local database for Paper, Testnet,
   and Live modes unless an explicit database URL is supplied.
4. Back up an existing SQLite database before every migration and retain the ten
   newest pre-migration backups.
5. Introduce backend-owned application settings before replacing the visible UI.
   The current PySide UI may be migrated incrementally, and the future React UI
   will consume the same localhost API instead of becoming another source of
   truth.
6. Keep credentials out of the generic settings store. Windows-protected
   credential storage is a separate security slice and must replace the legacy
   plaintext `.env` product path before release.

## Consequences

- Existing trading and risk code can be preserved while the control interface is
  modernized independently.
- Settings shared by future frontends can survive frontend and engine restarts.
- Installed mutable data no longer needs write access to the installation
  directory.
- SQLite migration failures have a recoverable pre-migration copy.
- The transition remains incomplete until PySide critical settings use the
  backend API and credential storage is protected by Windows facilities.

## Rejected alternatives

### Rewrite the engine with the frontend

Rejected because it would duplicate or replace proven trading, safety, and
migration behavior without a meaningful product benefit.

### Continue using frontend-only settings

Rejected because closing or replacing the frontend must not lose operational
configuration or create competing sources of truth.

### Require PostgreSQL for Testnet and Live

Rejected for the locally installed single-user product because it adds an
end-user dependency and conflicts with the no-developer-tools installation
requirement. An explicit alternate SQLAlchemy URL remains available for
controlled deployments.
