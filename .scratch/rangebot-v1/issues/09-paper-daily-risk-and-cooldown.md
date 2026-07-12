# 09 — Paper daily risk and cooldown

**What to build:** Paper Trading daily-risk accounting and cooldown behavior that blocks unsafe new entries while retaining protective controls.

**Blocked by:** 06 — Paper manual Market Entry; 08 — Paper close and cancellation controls.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Daily baseline and counters use the Asia/Riyadh day boundary and include realized P&L, fees, and funding in realized net loss.
- [ ] Loss, losing-trade, and automatic-fill limits block the required entry types while close/cancel remain available.
- [ ] Cooldown begins only after zero position and old protection cleanup, persists across restart, and does not start after partial reduction.

## Tests

- [ ] Time-controlled tests cover midnight reset, Late Daily Baseline, and persisted restart behavior.
- [ ] Integration tests cover all limit thresholds and allowed protective actions.
- [ ] Property tests cover monotonic risk-counter and cooldown invariants.
