# 22 — Live deployment in locked state and read-only reconciliation

**What to build:** Deployable Live-mode engine/UI packages and WinSW service behavior that always starts Live Locked, performs read-only Live reconciliation, and detects/displays Unmanaged Exchange State before any Live activation is possible.

**Blocked by:** 20 — Testnet automatic trading, external changes, and recovery.

**Status:** implemented with mocks — packages, durable Live Locked state, and adapter read-only contract are covered; Live read-only validation remains external.

## Acceptance criteria

- [ ] Separate engine and UI deployment packages, local config/log directories, and WinSW service configuration support startup, crash restart, clean stop, and Remote Desktop disconnection.
- [ ] A Live process/service/Windows/VPS restart restores Live Locked while keeping reconciliation and existing-position protection active.
- [ ] Read-only Live reconciliation detects positions/orders/protection and Unmanaged Exchange State; unmatched exchange state is displayed and cannot be mutated.

## Tests

- [ ] Packaging/service tests verify process separation, crash restart, clean stop, and engine survival after UI exit.
- [ ] Restart tests prove Live Locked persistence and read-only reconciliation before activation.
- [ ] Integration tests cover Unmanaged Exchange State display and mutation blocks.
