# 03 — Paper watchlist and public market feed

**What to build:** A Paper-mode dashboard where the operator searches eligible Gate.io USDT perpetual contracts, manages a manual watchlist, selects an Active Auto-Trading Coin, and sees current public market data.

**Blocked by:** 02 — Paper Account lifecycle.

**Status:** completed — covered by automated API/UI tests; final operator UAT is tracked in ticket 28.

## Acceptance criteria

- [x] Eligible contracts are searchable and may be manually added or removed up to a maximum watchlist size of 20.
- [x] Exactly one watched contract can be the Active Auto-Trading Coin; changing it stops automatic trading intent.
- [x] Watchlist priority affects display order only, and non-active contracts are visibly monitoring-only.

## Tests

- [x] Adapter-contract tests map eligible public contract and Last Price data without leaking exchange payloads into domain state.
- [x] Integration tests cover watchlist limit, active-contract exclusivity, and automatic-stop-on-change behavior.
- [x] UI tests verify Arabic contract status and mixed Arabic/Latin symbol rendering.
