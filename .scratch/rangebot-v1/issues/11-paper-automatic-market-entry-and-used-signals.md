# 11 — Paper automatic Market Entry and Used Signals

**What to build:** Automatic Paper Market trading for the Active Auto-Trading Coin with complete signal-state persistence, Directional Reset, daily-risk/cooldown gates, and safe close/cancellation availability.

**Blocked by:** 05 — Paper entry preview and Allocation Budget; 07 — Paper TP/SL protection; 08 — Paper close and cancellation controls; 09 — Paper daily risk and cooldown.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Automatic trading evaluates only the Active Auto-Trading Coin on fresh Last Price updates and requires all current entry guards.
- [ ] Entry, Limit expiry, and partial-fill paths save a Used Signal with its original Signal Trigger Zone.
- [ ] A Used Signal re-enters only after applicable cooldown, Directional Reset, later valid current zone, and full current checks; automatic limits and normal close paths remain available.

## Tests

- [ ] State-machine tests cover Eligible, Retry Delayed, Pending / Unknown, Used, and stable Directional Reset semantics.
- [ ] Integration tests prove daily-risk/cooldown blocks prevent automatic entry and active-contract change stops automation.
- [ ] Scenario tests cover immediate valid startup entry, conflicting signals, and no duplicate entry before full reset.
