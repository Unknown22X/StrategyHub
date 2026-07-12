# 15 — Testnet secure onboarding and read-only reconciliation

**What to build:** A secure Testnet connection path that loads local credentials safely, displays read-only Gate.io Testnet account state, and identifies Unmanaged Exchange State without mutating it.

**Blocked by:** 13 — Paper profiles, audit log, and Help Center.

**Status:** in progress — sanitized adapter seam is covered; authenticated Gate.io v4 onboarding/reconciliation remains required.

## Acceptance criteria

- [ ] Testnet configuration is distinct from Paper and Live, uses local credentials, and keeps secrets out of UI, logs, and builds.
- [ ] The engine retrieves and displays Testnet positions, orders, balances, and relevant configuration through read-only reconciliation.
- [ ] Any unmatched position, entry, TP, or SL is shown as Unmanaged Exchange State; it blocks mutations but is neither adopted nor changed.

## Tests

- [ ] Adapter-contract tests map Testnet REST/WebSocket snapshots and redact authentication material.
- [ ] Integration tests cover Unmanaged Exchange State detection, mutation blocks, and Refresh Reconciliation after external resolution.
- [ ] Security tests verify Testnet credentials cannot appear in client-visible state or logs.
