# 18 — Testnet protection and managed closure

**What to build:** Confirmed Testnet TP/SL protection and safe managed closure for a RangeBot-owned filled position, including restoration, partial-exit handling, and cleanup before cooldown.

**Blocked by:** 17 — Testnet safe Manual Market Entry.

**Status:** completed — managed protection, partial exits, repeated close, and cleanup are covered with mocks.

## Acceptance criteria

- [x] TP is reduce-only Limit and SL is Mark Price-triggered reduce-only stop-market using actual exchange fill/quantity and fee-aware targets.
- [x] Protection rejection or unexpected cancellation blocks entries and restores managed protection after reconciliation unless explicitly disabled.
- [x] Manual Close Position and protection-triggered closure reconcile actual quantity, cancel managed opposite protection, handle partial fills, and verify zero/cleanup before cooldown.

## Tests

- [x] Integration tests cover TP/SL placement, confirmation, restoration, and protection-error entry blocks.
- [x] Fault-injection tests cover partial TP, partial SL, and repeated reduce-only closing to zero.
- [x] Tests prove no protection or close operation can reverse a Testnet position.
