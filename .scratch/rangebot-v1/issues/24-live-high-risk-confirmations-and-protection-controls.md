# 24 — Live high-risk confirmations and protection controls

**What to build:** Live-only high-risk confirmation flows for unprotected positions and changes to current-position TP/SL, with persistent Arabic warnings and no implicit modification of open risk.

**Blocked by:** 23 — Live activation and advisory readiness warning.

**Status:** completed — typed confirmations and persistent protection state are covered automatically.

## Acceptance criteria

- [x] Opening a Live position with both TP and SL disabled requires exact `UNPROTECTED POSITION` confirmation.
- [x] Disabling TP or SL on an open Live position requires exact `DISABLE TP` or `DISABLE SL` confirmation respectively.
- [x] Global TP/SL changes affect future trades only; current-position changes require separate confirmed commands and persistent warnings.

## Tests

- [x] Command tests reject incorrect, missing, or stale typed confirmations.
- [x] Integration tests verify protection updates, persistent high-risk banners, and `NO AUTOMATIC EXIT PROTECTION`.
- [x] Tests prove an unconfirmed UI action cannot change a live protection order.
