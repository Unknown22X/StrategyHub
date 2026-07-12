---
status: accepted
---

# Budget round-trip fees before sizing

For available USDT futures balance `A`, reserve percentage `r`, allocation
percentage `P`, leverage `L`, and conservative entry and exit fee rates
`f_entry` and `f_exit`, RangeBot sets `R = A × r`,
`B = (A - R) × P`, and maximum allocated margin
`M = B / (1 + L × (f_entry + f_exit))`. Both fee rates are the Taker rate;
after quantity is rounded down to Gate.io's valid step, the engine recomputes
actual margin, notional value, and fees and requires
`actual margin + entry fee + exit fee + R <= A`, rejecting quantities below
the exchange minimum or failing the final sufficiency check.
