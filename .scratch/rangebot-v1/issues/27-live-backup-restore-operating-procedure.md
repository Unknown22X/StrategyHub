# 27 — Live backup/restore operating procedure

**What to build:** A documented and manually validated PostgreSQL backup/restore procedure that restores RangeBot safely and blocks entries until database, exchange, and protection reconciliation complete.

**Blocked by:** 26 — Live service lifecycle and emergency-operation validation.

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Operations documentation describes standard PostgreSQL backup and restore commands and required preconditions without storing secrets.
- [ ] After restore, the engine restarts, validates persisted state, reconciles Gate.io positions/orders, validates protection, and blocks entries until safe.
- [ ] The procedure explicitly distinguishes advisory Live Readiness verification from Live activation requirements.

## Tests

- [ ] Manual validation records backup, restore, restart, reconciliation, protection validation, and release of entry blocking.
- [ ] Automated integration test covers restored-state entry blocking until reconciliation success.
- [ ] Documentation review verifies no credentials or unsafe operational shortcuts are included.
