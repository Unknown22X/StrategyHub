---
status: accepted
---

# Use stable directional signal resets

At entry, accepted Limit expiry, or any partial fill, RangeBot saves the
original Long zone `[low, low × (1 + proximity)]` or Short zone
`[high × (1 - proximity), high]`. A Used Long resets only when Last Price is
at least the original upper edge times `(1 + reset distance)`; a Used Short
resets only when it is at most the original lower edge times
`(1 - reset distance)`. Moving further through the entry boundary does not
reset a signal, and the saved zone remains authoritative even if later rolling
window or Gate candle values change; after reset, a current zone and every
current entry condition must pass before a new signal is generated.
