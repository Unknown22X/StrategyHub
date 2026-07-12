# 28 — Version-one acceptance and deployment evidence

**What to build:** Consolidated evidence that the complete RangeBot version-one contract is satisfied across Paper, Testnet, and deployed Live operations, with advisory verification clearly separate from Live activation safety.

**Blocked by:** 21 — Testnet verification evidence; 27 — Live backup/restore operating procedure.

**Status:** completed — automated evidence, packages, UI review, operations guide, and final checklist are recorded.

## Acceptance criteria

- [x] TEST-001 through TEST-027 each have automated or documented manual evidence, including service lifecycle, reconciliation, stale data, idempotency, protection, cooldown, daily risk, and confirmations.
- [x] Paper and Testnet results are recorded as advisory Live Readiness evidence; missing/stale evidence is not represented as a Live activation blocker.
- [x] Deployment handoff includes RTL visual review, Testnet evidence, Live operational checks, backup/restore evidence, and known non-blocking presentation choices.

## Tests

- [x] Acceptance matrix maps every requirement and accepted ADR scenario to a test or manual validation artifact.
- [x] Release review reruns the full automated suite and separately marked Testnet checks.
- [x] Manual review verifies the typed `LIVE` flow remains available when real safety checks pass regardless of advisory evidence state.
