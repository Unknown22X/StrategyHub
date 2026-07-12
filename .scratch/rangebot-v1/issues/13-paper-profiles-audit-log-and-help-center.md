# 13 — Paper profiles, audit log, and Help Center

**What to build:** Operator-facing Paper configuration profiles, redaction-safe Arabic activity/audit explanations, high-risk banners, and the Arabic Help Center.

**Blocked by:** 12 — Paper Emergency Stop and restart recovery.

**Status:** completed — manual/UAT pending final project verification.

## Acceptance criteria

- [x] Profiles can be saved, duplicated, renamed, edited, applied with a confirmed change summary, and deleted; they exclude credentials and runtime trading state.
- [x] Applying a profile affects only future activity and never enables Live Trading or clears runtime locks.
- [x] Activity records and Help Center present Arabic explanations for trading decisions, protection, risk, modes, cooldown, Emergency Stop, and rejection reasons without exposing secrets.

## Tests

- [x] Integration tests prove profile isolation and rejected application of credentials/runtime state.
- [x] Log tests prove credentials, signatures, headers, database passwords, and environment contents are redacted.
- [x] UI tests verify RTL activity, banners, and Help Center navigation/content coverage.
