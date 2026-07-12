# 08 — Paper close and cancellation controls

**What to build:** Safe Paper-mode Manual Close Position and pending-entry cancellation controls that reconcile local simulated state, remove old protection, close only the remaining quantity, and verify cleanup.

**Blocked by:** 07 — Paper TP/SL protection.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [x] Manual Close Position takes the central trading lock, cancels active simulated TP/SL, closes actual remaining quantity, and verifies old protection is gone.
- [x] Pending Paper entries can be cancelled without cancelling unrelated state.
- [x] Protective close and cancellation stay available when the market feed is stale or incomplete.

## Tests

- [x] State-machine and integration tests cover close, cancellation, cleanup, and no-reverse-position ordering.
- [x] Integration tests cover stale-data availability and partial remaining quantity.
- [x] Negative tests prove oversized close requests are rejected.
