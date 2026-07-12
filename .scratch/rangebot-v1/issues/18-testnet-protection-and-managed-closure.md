# 18 — Testnet protection and managed closure

**What to build:** Confirmed Testnet TP/SL protection and safe managed closure for a RangeBot-owned filled position, including restoration, partial-exit handling, and cleanup before cooldown.

**Blocked by:** 17 — Testnet safe Manual Market Entry.

**Status:** in progress — mock controls exist, but complete managed protection and close lifecycle remains incomplete.

## Acceptance criteria

- [ ] TP is reduce-only Limit and SL is Mark Price-triggered reduce-only stop-market using actual exchange fill/quantity and fee-aware targets.
- [ ] Protection rejection or unexpected cancellation blocks entries and restores managed protection after reconciliation unless explicitly disabled.
- [ ] Manual Close Position and protection-triggered closure reconcile actual quantity, cancel managed opposite protection, handle partial fills, and verify zero/cleanup before cooldown.

## Tests

- [ ] Integration tests cover TP/SL placement, confirmation, restoration, and protection-error entry blocks.
- [ ] Fault-injection tests cover partial TP, partial SL, and repeated reduce-only closing to zero.
- [ ] Tests prove no protection or close operation can reverse a Testnet position.
