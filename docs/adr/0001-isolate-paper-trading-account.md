---
status: accepted
---

# Isolate Paper Trading in a local Paper Account

Paper Trading uses a persistent local Paper Account, starting at 1,000 USDT by
default or a user-selected amount, while consuming only Gate.io public market,
contract-rule, fee-rate, and funding-rate data where available. It must never
query, alter, or display the user's real Gate.io futures balance, positions,
orders, or credentials; all simulated money, trading, protection, cooldown, and
risk state belongs exclusively to the Paper Account. Its starting balance may
be changed, or the account reset with explicit confirmation and logging, only
when no Paper position or pending Paper entry order exists.
