# 19 — Testnet Limit Entry and partial-fill recovery

**What to build:** Safe Testnet manual/automatic Limit-entry behavior with persistent identity, expiry, uncertain outcomes, partial fills, cancellation of remainder, and already-proven TP/SL protection and closure.

**Blocked by:** 16 — Testnet market/account readiness gate; 17 — Testnet safe Manual Market Entry; 18 — Testnet protection and managed closure.

**Status:** implemented through shared idempotent Limit lifecycle coverage; real Testnet partial-fill validation is external.

## Acceptance criteria

- [ ] Manual Limit Entry preserves the confirmed absolute valid price; automatic Limit uses the configured side-aware offset and expiry.
- [ ] Unfilled expiry cancels the managed order and consumes the signal; an uncertain result blocks retry until reconciled by persistent identity.
- [ ] A partial fill cancels the remainder and immediately manages the actual quantity and average fill with confirmed TP/SL and safe closure capability.

## Tests

- [ ] Integration tests cover expiry, cancellation, request identity, and retry blocking after missing responses.
- [ ] Exchange-simulation tests cover partial fills, actual-fill protection sizing, and cleanup.
- [ ] Negative tests prove no partial Limit fill can be treated as complete before protection is confirmed.
