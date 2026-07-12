# 07 — Paper TP/SL protection

**What to build:** Automatic Paper TP and SL protection for a filled position, including fee-aware target calculation, persistent protection state, and visible warnings/errors.

**Blocked by:** 06 — Paper manual Market Entry.

**Status:** completed

## Approved Paper fee model

Paper persists an isolated local fee schedule. Maker and Taker rates default to
0.10%, are validated as non-negative Decimal rates, and are never obtained from
or applied to a real Gate.io account. TP uses Maker; Market entry and SL use
Taker. Future Paper Limit fills use Maker unless marketable.

## Acceptance criteria

- [x] Default TP and SL use actual Paper fill, quantity, leverage, entry fee, estimated closing fee, and configured 30%/10% Allocated Margin targets.
- [x] TP and SL are capped to remaining position quantity and cannot create reverse exposure.
- [x] Missing, rejected, or disabled protection has a persistent high-risk warning and blocks new entries where required.

## Tests

- [x] Unit tests cover Long/Short target calculations, fee treatment, and non-reversing quantities.
- [x] Integration tests verify protected position state, protection-error entry blocking, and Arabic warnings.
- [x] Simulation tests cover TP/SL trigger fees and position state changes.
