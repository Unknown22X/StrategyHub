# 06 — Paper manual Market Entry

**What to build:** A confirmed Paper Long/Short Market-entry path that creates a single simulated position using configured adverse slippage, fees, persisted activity, and the central entry safeguards that apply to manual actions.

**Blocked by:** 05 — Paper entry preview and Allocation Budget.

**Status:** completed

## Acceptance criteria

- [x] Manual Paper Market Entry requires final confirmation and consumes the account's one active trade state.
- [x] Long and Short fills apply configured adverse slippage and Taker fees, with actual fill and account effects persisted.
- [x] Manual entry bypasses only automatic-strategy conditions; balance, reserve, one-trade, history, and market-data safety checks remain enforced.

## Tests

- [x] Integration tests cover confirmed Long/Short fill, slippage, fees, and Arabic activity output.
- [x] Negative tests cover each manual-entry safety block and duplicate-position rejection.
- [x] Restart test verifies a filled Paper position remains visible after engine recreation.
