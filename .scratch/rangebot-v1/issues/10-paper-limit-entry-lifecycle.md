# 10 — Paper Limit Entry lifecycle

**What to build:** Safe Paper manual and automatic Limit-entry behavior, including absolute/derived prices, full-or-none fills, expiry cancellation, Used Signal consumption, and all required close/risk guards.

**Blocked by:** 06 — Paper manual Market Entry; 08 — Paper close and cancellation controls; 09 — Paper daily risk and cooldown.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [x] Manual Limit Entry validates an absolute operator-entered price without silent repricing; automatic Limit Entry uses configured side-aware offset and expiry.
- [x] Paper Long Limit fills only at or below Limit and Paper Short Limit only at or above Limit, fully or not at all.
- [x] Expiry cancels the pending entry, marks the signal Used, observes daily-risk and one-trade guards, and leaves cleanup controls available.

## Tests

- [x] Simulation and integration tests cover fill boundaries, expiry, cancellation, and Maker/Taker classification.
- [x] Integration tests prove pending Limit state and risk guards.
- [x] Tests verify cancellation/expiry cleanup and Used Signal persistence.
