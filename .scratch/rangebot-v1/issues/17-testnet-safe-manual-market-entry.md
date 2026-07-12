# 17 — Testnet safe Manual Market Entry

**What to build:** A single safe Testnet Manual Market Entry flow that persists request identity before submission and enforces fresh Last Price, order-book liquidity, and the 0.30% expected-deviation guard before any order can reach Gate.io.

**Blocked by:** 16 — Testnet market/account readiness gate.

**Status:** completed — persistent identity and market execution safeguards are covered locally.

## Acceptance criteria

- [x] Final confirmation submits a Market entry only after Last Price and order-book snapshot are each less than one second old.
- [x] Long uses Ask liquidity and Short uses Bid liquidity; insufficient liquidity or expected deviation above 0.30% rejects without resizing, conversion, or submission.
- [x] Intent and persistent client identity are committed before submission; timeout/missing response produces Pending / Unknown and no blind duplicate retry.

## Tests

- [x] Adapter tests cover order-book volume-weighting, age checks, and Long/Short sides.
- [x] Fault-injection tests cover timeout before/after exchange acceptance and prove identity-based reconciliation prevents duplicates.
- [x] Integration tests verify final confirmation, rejection reasons, retry-delay behavior, and no order request on guard failure.
