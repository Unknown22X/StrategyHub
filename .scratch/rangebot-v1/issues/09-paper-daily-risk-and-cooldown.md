# 09 — Paper daily risk and cooldown

**What to build:** Paper Trading daily-risk accounting and cooldown behavior that blocks unsafe new entries while retaining protective controls.

**Blocked by:** 06 — Paper manual Market Entry; 08 — Paper close and cancellation controls.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [x] Daily baseline and counters use the Asia/Riyadh day boundary and include realized P&L, fees, and funding in realized net loss.
- [x] Loss, losing-trade, and automatic-fill limits block the required entry types while close/cancel remain available.
- [x] Cooldown begins only after zero position and old protection cleanup, persists across restart, and does not start after partial reduction.

## Tests

- [x] Persisted restart and cooldown tests cover the required state transitions.
- [x] Integration tests cover risk blocks and allowed cancellation.
- [x] Focused state-transition tests cover non-negative counters and partial/full close cooldown behavior.
