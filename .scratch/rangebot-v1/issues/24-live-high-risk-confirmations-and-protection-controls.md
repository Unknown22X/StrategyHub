# 24 — Live high-risk confirmations and protection controls

**What to build:** Live-only high-risk confirmation flows for unprotected positions and changes to current-position TP/SL, with persistent Arabic warnings and no implicit modification of open risk.

**Blocked by:** 23 — Live activation and advisory readiness warning.

**Status:** implemented — typed high-risk confirmation guards are covered automatically.

## Acceptance criteria

- [ ] Opening a Live position with both TP and SL disabled requires exact `UNPROTECTED POSITION` confirmation.
- [ ] Disabling TP or SL on an open Live position requires exact `DISABLE TP` or `DISABLE SL` confirmation respectively.
- [ ] Global TP/SL changes affect future trades only; current-position changes require separate confirmed commands and persistent warnings.

## Tests

- [ ] Command tests reject incorrect, missing, or stale typed confirmations.
- [ ] Integration tests verify protection updates, persistent high-risk banners, and `NO AUTOMATIC EXIT PROTECTION`.
- [ ] Tests prove an unconfirmed UI action cannot change a live protection order.
