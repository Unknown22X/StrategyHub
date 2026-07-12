# 23 — Live activation and advisory readiness warning

**What to build:** A Live activation flow that requires current real safety checks and exact `LIVE` confirmation while showing Paper/Testnet readiness only as an advisory Arabic warning.

**Blocked by:** 22 — Live deployment in locked state and read-only reconciliation.

**Status:** completed — exact confirmation and advisory policy are covered; real activation was not performed.

## Acceptance criteria

- [x] Live activation requires Live Locked unlock intent, exact typed `LIVE`, no conflicting position/order, no Emergency Stop, no reconciliation/protection error, fresh data/history, active contract, and acceptable risk state.
- [x] Missing or stale Paper/Testnet verification displays a prominent warning but does not block activation when all real safety checks pass.
- [x] Live remains locked after restart, intentional service stop, or Emergency Stop and does not auto-unlock.

## Tests

- [x] Integration tests cover each real activation block and exact-confirmation validation.
- [x] Policy tests prove every Paper/Testnet readiness combination permits activation when real checks pass.
- [x] Restart and Emergency Stop tests verify Live Locked behavior.
