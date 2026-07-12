# 08 — Paper close and cancellation controls

**What to build:** Safe Paper-mode Manual Close Position and pending-entry cancellation controls that reconcile local simulated state, remove old protection, close only the remaining quantity, and verify cleanup.

**Blocked by:** 07 — Paper TP/SL protection.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Manual Close Position takes the central trading lock, cancels active simulated TP/SL, closes actual remaining quantity, and verifies old protection is gone.
- [ ] Pending Paper entries can be cancelled without cancelling unrelated state.
- [ ] Protective close and cancellation stay available when the market feed is stale or incomplete.

## Tests

- [ ] State-machine tests verify lock, cancellation, close, cleanup, and no-reverse-position ordering.
- [ ] Integration tests cover stale-data availability and partial remaining quantity.
- [ ] Negative tests prove unrelated account state is untouched.
