# 25 — Live managed entry, TP/SL, and closing execution

**What to build:** Actual RangeBot-managed Live entry, TP/SL, cancellation, and closing execution after activation, requiring fresh reconciliation, current protection rules, and every Testnet-proven execution safeguard.

**Blocked by:** 18 — Testnet protection and managed closure; 19 — Testnet Limit Entry and partial-fill recovery; 20 — Testnet automatic trading, external changes, and recovery; 23 — Live activation and advisory readiness warning; 24 — Live high-risk confirmations and protection controls.

**Status:** implemented — adapter-gated execution safety is covered with mocks; no Live order was or will be sent.

## Acceptance criteria

- [ ] A Live order can submit only after fresh reconciliation, current readiness, persistent request identity, liquidity/slippage guard where applicable, and applicable typed confirmations.
- [ ] Live Market/Limit entry, partial fill, TP/SL placement/restoration, cancellation, Manual Close Position, and protection-triggered cleanup use the same proven safeguards as Testnet.
- [ ] Gate.io-reported liquidation price becomes the displayed source of truth after position open, and no managed operation mutates Unmanaged Exchange State.

## Tests

- [ ] Mocked Live-adapter end-to-end tests cover entry through confirmed TP/SL and closure, including timeout/partial-fill faults.
- [ ] Safety tests verify no submission before fresh reconciliation or required confirmation.
- [ ] Controlled manual Live-readiness test plan documents a non-production verification of the complete workflow.
