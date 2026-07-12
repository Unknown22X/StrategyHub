---
status: accepted
---

# Require fresh reconciliation and action for Emergency Close Position

Emergency Close Position atomically persists Emergency Stop, blocks entries,
and then performs the Manual Close Position workflow for the selected
mode/account: cancel pending entries, reconcile, cancel TP and SL, reconcile
again, repeatedly issue reduce-only market closes for the actual remainder,
and verify zero position with no old entry or protective orders. Emergency Stop
remains active after success; if disconnected or unable to reconcile, the
engine records and displays the blocked or failed outcome but never queues a
close to execute later without fresh reconciliation and explicit user action.
