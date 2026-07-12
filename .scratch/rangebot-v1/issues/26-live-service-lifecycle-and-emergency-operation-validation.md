# 26 — Live service lifecycle and emergency-operation validation

**What to build:** Validation of Live runtime recovery, Emergency Stop, and fresh-action Emergency Close Position under service, process, connectivity, and exchange-state failure scenarios.

**Blocked by:** 22 — Live deployment in locked state and read-only reconciliation; 25 — Live managed entry, TP/SL, and closing execution.

**Status:** implemented with mocks — durable lock and managed emergency cancellation paths are covered; WinSW/VPS validation remains external.

## Acceptance criteria

- [ ] Emergency Stop durably blocks all Live entries, cancels only managed pending entries, and preserves existing protection.
- [ ] Emergency Close Position activates Emergency Stop first, requires fresh reconciliation, handles actual remainder reduce-only, and never queues a later close after failure/disconnection.
- [ ] Service/process/VPS restart preserves locks and protection behavior; Live remains locked while reconciliation proceeds.

## Tests

- [ ] Fault-injection tests cover service stop, crash, disconnect, partial close, and unrecoverable exchange errors.
- [ ] Integration tests prove only RangeBot-managed state is mutated during emergency workflows.
- [ ] Restart tests verify Live Locked, Emergency Stop, and protection reconciliation persistence.
