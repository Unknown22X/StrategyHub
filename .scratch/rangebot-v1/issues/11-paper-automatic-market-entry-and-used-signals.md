# 11 — Paper automatic Market Entry and Used Signals

**What to build:** Automatic Paper Market trading for the Active Auto-Trading Coin with complete signal-state persistence, Directional Reset, daily-risk/cooldown gates, and safe close/cancellation availability.

**Blocked by:** 05 — Paper entry preview and Allocation Budget; 07 — Paper TP/SL protection; 08 — Paper close and cancellation controls; 09 — Paper daily risk and cooldown.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [x] Automatic trading evaluates only the Active Auto-Trading Coin and requires current entry guards.
- [x] Entry and Limit expiry save a Used Signal with its original trigger zone.
- [x] A Used Signal requires cooldown, validated Directional Reset, and current checks before reuse.

## Tests

- [ ] State-machine tests cover Eligible, Retry Delayed, Pending / Unknown, Used, and stable Directional Reset semantics.
- [ ] Integration tests prove daily-risk/cooldown blocks prevent automatic entry and active-contract change stops automation.
- [ ] Scenario tests cover immediate valid startup entry, conflicting signals, and no duplicate entry before full reset.
