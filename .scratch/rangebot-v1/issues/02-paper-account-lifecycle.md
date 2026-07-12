# 02 — Paper Account lifecycle

**What to build:** An isolated persistent Paper Account that the operator can select, inspect, initialize with the default or chosen Paper Starting Balance, and reset only through an explicit confirmed safe flow.

**Blocked by:** 01 — Engine/UI heartbeat.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Paper Account balance, positions, orders, protection, cooldown, and risk state are local and distinct from Testnet and Live state.
- [ ] Default Paper Starting Balance is 1,000 USDT; an operator-selected amount is persisted with its change reason.
- [ ] Reset or starting-balance change is rejected while a Paper position or pending Paper entry exists and is otherwise confirmed and logged.

## Tests

- [ ] Integration tests prove Paper queries never require or expose real Gate.io credentials or account balances.
- [ ] State-transition tests cover initialization, safe reset, and each reset rejection.
- [ ] Restart test proves Paper Account state and audit activity persist.
