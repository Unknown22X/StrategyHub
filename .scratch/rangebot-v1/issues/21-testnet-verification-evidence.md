# 21 — Testnet verification evidence

**What to build:** Advisory Testnet verification evidence that combines with Paper verification in the Live Readiness display without becoming a deployment or Live-activation gate.

**Blocked by:** 14 — Paper verification record; 20 — Testnet automatic trading, external changes, and recovery.

**Status:** completed — separate persistent advisory evidence and UI state are covered automatically.

## Acceptance criteria

- [x] Testnet verification can be recorded with timestamp, engine build identifier, and Safety-Critical Profile Fingerprint.
- [x] Live Readiness clearly distinguishes current, stale, missing Paper, and missing Testnet evidence in Arabic RTL.
- [x] Missing or stale Paper/Testnet evidence never blocks Live deployment or valid typed `LIVE` activation when current real safety checks pass.

## Tests

- [x] Persistence tests cover separate Paper/Testnet records and fingerprint/build invalidation.
- [x] UI tests cover advisory warning states and mixed verification combinations.
- [x] Activation-policy tests prove readiness evidence is never an activation blocker.
