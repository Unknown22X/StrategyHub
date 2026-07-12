# 05 — Paper entry preview and Allocation Budget

**What to build:** A Paper entry-preview flow that calculates safe Decimal sizing, fees, Safety Reserve, Allocated Margin, rounded quantity, and estimated liquidation information before an operator can confirm an entry.

**Blocked by:** 04 — Paper range analysis and decision details.

**Status:** completed — covered by automated Decimal sizing tests; final operator UAT is tracked in ticket 28.

## Acceptance criteria

- [ ] Preview supports 25%, 50%, 75%, and 100% allocation and applies Paper Safety Reserve and conservative round-trip fee budgeting.
- [ ] Quantity is rounded down to contract rules; final margin, fees, reserve, and balance sufficiency are recomputed after rounding.
- [ ] The UI displays a labelled Paper liquidation estimate, expected entry values, fees, TP/SL preview, and all blocking reasons before confirmation.

## Tests

- [ ] Hypothesis tests prove sizing never exceeds Available Futures Balance after fees and Safety Reserve.
- [ ] Unit tests cover fee fallback, minimum quantity rejection, leverage options, and deterministic Decimal rounding.
- [ ] Contract tests reject submission when a preview's safety-critical state becomes stale.
