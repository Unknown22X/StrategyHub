---
status: superseded by ADR-0007
---

# Gate Live activation on current Paper and Testnet verification

Live Trading requires a PostgreSQL Live Readiness Record with separate Paper
Trading Verified and Gate.io Testnet Verified operator confirmations. Each
confirmation records its timestamp, trading-engine build identifier, immutable
Safety-Critical Profile Fingerprint, and confirmation that documented checks
succeeded; a build change or safety-critical-profile change invalidates both
records. With both current records present, Live activation still requires the
typed `LIVE` confirmation and every normal account, market-data, protection,
and risk check.
