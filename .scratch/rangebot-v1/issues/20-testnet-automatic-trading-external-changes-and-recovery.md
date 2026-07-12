# 20 — Testnet automatic trading, external changes, and recovery

**What to build:** Testnet automatic trading that reuses Paper-proven Used Signal behavior and guards, reconciles external exchange changes, and resumes safely after restart without mutating Unmanaged Exchange State.

**Blocked by:** 11 — Paper automatic Market Entry and Used Signals; 17 — Testnet safe Manual Market Entry; 18 — Testnet protection and managed closure; 19 — Testnet Limit Entry and partial-fill recovery.

**Status:** completed — automatic intent, Used Signals, restart, and external-change recovery are covered with mocks.

## Acceptance criteria

- [x] Automatic Testnet entry uses the Active Auto-Trading Coin, current readiness/risk guards, and the persisted Used Signal/Directional Reset semantics proven in Paper.
- [x] Full external closure is recorded and cleaned up; external partial reduction reconciles remaining position and resizes managed protection.
- [x] Testnet automatic intent resumes after ordinary restart only when prior intent and all reconciliation, history, market-data, protection, risk, and active-contract checks pass.

## Tests

- [x] End-to-end tests exercise automatic Market/Limit paths from fresh signal through protection and cleanup.
- [x] Reconciliation tests cover external full closure, partial reduction, restart, and Unmanaged Exchange State mutation blocks.
- [x] Scenario tests prove Used Signals cannot duplicate entries before Directional Reset and cooldown completion.
