# 07 — Paper TP/SL protection

**What to build:** Automatic Paper TP and SL protection for a filled position, including fee-aware target calculation, persistent protection state, and visible warnings/errors.

**Blocked by:** 06 — Paper manual Market Entry.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Default TP and SL use actual Paper fill, quantity, leverage, entry fee, estimated closing fee, and configured 30%/10% Allocated Margin targets.
- [ ] TP and SL are capped to remaining position quantity and cannot create reverse exposure.
- [ ] Missing, rejected, or disabled protection has a persistent high-risk warning and blocks new entries where required.

## Tests

- [ ] Unit tests cover Long/Short target calculations, fee treatment, and non-reversing quantities.
- [ ] Integration tests verify protected position state, protection-error entry blocking, and Arabic warnings.
- [ ] Simulation tests cover TP/SL trigger fees and position state changes.
