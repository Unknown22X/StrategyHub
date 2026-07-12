---
status: accepted
---

# Keep Paper and Testnet verification advisory for Live activation

RangeBot may store separate Paper Trading Verified and Gate.io Testnet Verified
operator confirmations with timestamp, engine build identifier, and
Safety-Critical Profile Fingerprint, invalidating both when the build or a
safety-critical profile setting changes. Missing or stale verification must
show a prominent Arabic RTL warning that the configuration has not completed
Paper and/or Testnet verification and Live Trading may use real money and
result in losses, but must not block the normal typed `LIVE` confirmation.
Live remains blocked only by actual safety conditions: Live Locked state,
Emergency Stop, no Active Auto-Trading Coin, stale or incomplete market data,
reconciliation or protection errors, Unmanaged Exchange State, an existing
position or conflicting pending order, or daily risk limits.
