# 12 — Paper Emergency Stop and restart recovery

**What to build:** Persistent Paper Emergency Stop, explicit Resume, Emergency Close Position, and restart recovery that safely handles open positions and pending Limit entries without queuing stale emergency actions.

**Blocked by:** 08 — Paper close and cancellation controls; 10 — Paper Limit Entry lifecycle; 11 — Paper automatic Market Entry and Used Signals.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [ ] Emergency Stop persistently blocks manual and automatic entries and cancels managed pending Paper entries.
- [ ] Emergency Close Position activates Emergency Stop before performing the safe close path and never queues a disconnected or failed close for later execution.
- [ ] `RESUME` is required to clear Emergency Stop; automatic trading remains disabled until explicitly restarted after recovery.

## Tests

- [ ] Restart tests prove Emergency Stop, pending Limit handling, cooldown, and recovery state persist.
- [ ] Fault-injection tests cover failed/disconnected Emergency Close Position and require a fresh explicit retry.
- [ ] Integration tests cover typed Resume, entry blocks, and post-resume automatic-trading state.
