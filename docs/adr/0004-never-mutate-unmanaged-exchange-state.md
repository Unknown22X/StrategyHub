---
status: accepted
---

# Never mutate Unmanaged Exchange State

Any Testnet or Live position, entry order, TP order, or SL order without a
matching persisted RangeBot identity is Unmanaged Exchange State. RangeBot
displays its exchange details and continues read-only reconciliation, but
blocks entries, mode changes, and every normal or emergency close/cancel action
from altering it; Emergency Stop still blocks new RangeBot entries. The user
must resolve that state directly on Gate.io and request Refresh Reconciliation
before normal operation can resume.
