# 01 — Engine/UI heartbeat

**What to build:** A demoable local control loop in which the asynchronous engine persists a minimal runtime state, serves it only on localhost, and an Arabic RTL UI connects, displays engine health, and reconnects after a temporary outage.

**Blocked by:** None — can start immediately.

**Status:** approved

## Acceptance criteria

- [x] Engine and UI run as separate processes; closing the UI leaves the engine running.
- [x] The UI displays engine connection and lifecycle state and reconnects after the engine becomes available again.
- [x] Runtime state is persisted through the database migration path and the service/API are localhost-only.

## Tests

- [x] Integration test drives health/state queries through the localhost contract and verifies persisted state.
- [x] Process test verifies UI exit does not stop the engine and reconnect restores a fresh state snapshot.
- [x] UI test verifies Arabic RTL direction and mixed-direction status values render without changing engine state.

## Comments

- Approved on 2026-07-12. SQLite is permitted only for ticket 01's local
  demo/test persistence path. A future production requirement must require
  explicit PostgreSQL configuration and must never silently fall back to SQLite.
