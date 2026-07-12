# 06 — Paper manual Market Entry

**What to build:** A confirmed Paper Long/Short Market-entry path that creates a single simulated position using configured adverse slippage, fees, persisted activity, and the central entry safeguards that apply to manual actions.

**Blocked by:** 05 — Paper entry preview and Allocation Budget.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Manual Paper Market Entry requires final confirmation and consumes the account's one active trade state.
- [ ] Long and Short fills apply configured adverse slippage and Taker fees, with actual fill and account effects persisted.
- [ ] Manual entry bypasses only automatic-strategy conditions; balance, reserve, one-trade, history, and market-data safety checks remain enforced.

## Tests

- [ ] Integration tests cover confirmed Long/Short fill, slippage, fees, and Arabic activity output.
- [ ] Negative tests cover each manual-entry safety block and duplicate-position rejection.
- [ ] Restart test verifies a filled Paper position remains visible after engine recreation.
