# RangeBot v1 Approved Milestone Plan

**Status:** approved

## Completed foundation

- **01 — Engine/UI heartbeat:** complete in commit `a214ce1`.

## Approved delivery sequence

1. **Paper Trading foundation:** tickets 02 through 14, in their existing
   numerical order. Complete and verify each ticket before beginning the next.
2. **Gate.io Testnet safety path:** tickets 15 through 21, in their existing
   numerical order, after Paper Trading verification is complete.
3. **Live deployment and controls:** tickets 22 through 27, in their existing
   numerical order, after Testnet evidence is complete.
4. **Version-one acceptance evidence:** ticket 28, after all preceding tickets
   are complete.

This approved plan does not authorize implementation of ticket 02 yet.

## Deferred production requirement

**PROD-001 — Explicit PostgreSQL runtime configuration**

SQLite is permitted only for ticket 01's local demo/test persistence path.
Before production runtime is supported, RangeBot must require explicit local
PostgreSQL configuration and must not silently use SQLite or fall back to it.
This requirement is deferred planning work and does not expand ticket 01 into
PostgreSQL provisioning.
