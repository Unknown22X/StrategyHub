# 04 — Paper range analysis and decision details

**What to build:** Explainable Paper-mode range evaluation for Rolling Window and Current Gate Candle analysis, including history readiness and all passed/failed Long and Short conditions.

**Blocked by:** 03 — Paper watchlist and public market feed.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Rolling Window uses the specified one-minute candle counts including the forming candle; Current Gate Candle follows Gate.io interval boundaries.
- [ ] Exact and interval range modes, proximity, direction settings, and conflicting Long/Short rejection produce structured decision reasons and Arabic explanations.
- [ ] Missing, invalid, insufficient, or non-contiguous history shows Warming Up / History Gap and blocks entries while protective controls remain available.

## Tests

- [ ] Unit and property tests cover Decimal range/proximity boundaries, candle selection, and conflicting signals.
- [ ] Adapter tests cover candle ordering, gaps, and timestamp-boundary behavior.
- [ ] API/UI tests verify the complete condition-details view and Arabic decision text.
