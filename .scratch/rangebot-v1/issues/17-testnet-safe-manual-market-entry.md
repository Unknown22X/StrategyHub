# 17 — Testnet safe Manual Market Entry

**What to build:** A single safe Testnet Manual Market Entry flow that persists request identity before submission and enforces fresh Last Price, order-book liquidity, and the 0.30% expected-deviation guard before any order can reach Gate.io.

**Blocked by:** 16 — Testnet market/account readiness gate.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Final confirmation submits a Market entry only after Last Price and order-book snapshot are each less than one second old.
- [ ] Long uses Ask liquidity and Short uses Bid liquidity; insufficient liquidity or expected deviation above 0.30% rejects without resizing, conversion, or submission.
- [ ] Intent and persistent client identity are committed before submission; timeout/missing response produces Pending / Unknown and no blind duplicate retry.

## Tests

- [ ] Adapter tests cover order-book volume-weighting, age checks, and Long/Short sides.
- [ ] Fault-injection tests cover timeout before/after exchange acceptance and prove identity-based reconciliation prevents duplicates.
- [ ] Integration tests verify final confirmation, rejection reasons, retry-delay behavior, and no order request on guard failure.
