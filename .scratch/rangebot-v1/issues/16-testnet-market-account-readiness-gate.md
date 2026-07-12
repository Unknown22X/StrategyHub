# 16 — Testnet market/account readiness gate

**What to build:** A Testnet readiness gate that validates market freshness, history, contract rules, One-way mode, Cross margin, leverage, existing orders/positions, and reconnect state before any entry can be attempted.

**Blocked by:** 15 — Testnet secure onboarding and read-only reconciliation.

**Status:** completed — readiness and reconnect behavior are covered locally; real WebSocket validation remains external.

## Acceptance criteria

- [x] Testnet entries are blocked until One-way mode, Cross margin, selected leverage, account state, contract rules, and reconciliation are confirmed.
- [x] The engine never automatically switches Hedge mode and never cancels unrelated or Unmanaged Exchange State to force configuration.
- [x] Market data becomes stale after 10 seconds; reconnect requires subscription confirmation, REST snapshot, two newer updates within 10 seconds, and reconciliation.

## Tests

- [x] Adapter and integration tests cover confirmed configuration, rejection paths, and stale/partial market data.
- [x] Reconnect tests verify every required readiness stage before entry becomes available.
- [x] Tests prove protective close/cancel remains available when permissible during data staleness.
