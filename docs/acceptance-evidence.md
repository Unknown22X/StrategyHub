# RangeBot v1 acceptance evidence

Automated release gate executed on 2026-07-13:

- `uv run ruff check .` — passed.
- `uv run pytest -q` — 86 passed.
- `uv run pyinstaller --clean --noconfirm deploy/engine.spec` — passed.
- `uv run pyinstaller --clean --noconfirm deploy/ui.spec` — passed.
- Both packaged executables returned exit code 0 for `--help`.
- Offscreen Arabic RTL layout review completed at 1200×820; see
  `docs/ui-visual-verification.md`.

No credential was loaded by the test suite, no external network transport was used,
and no Testnet or Live order was submitted. “Implemented” below means code and local
mock acceptance are complete; real Gate.io, VPS, WinSW, PostgreSQL, RDP, and Arabic
font validation remain explicit final external checks.

| Criterion | Automated or documented evidence |
| --- | --- |
| TEST-001 | `tests/process/test_engine_ui_lifecycle.py`; WinSW asset test |
| TEST-002 | Mock adapter/API restart, reconnect, and automatic-intent tests |
| TEST-003 | Live relock integration test and service configuration |
| TEST-004 | Paper and exchange position/pending-entry gate tests |
| TEST-005 | Range-analysis gap/insufficient-history tests |
| TEST-006 | Current Gate Candle boundary tests |
| TEST-007 | 10-second readiness and one-second market guard tests |
| TEST-008 | Paper and mock Used Signal/Directional Reset tests |
| TEST-009 | Persistent request identity and unknown-outcome retry test |
| TEST-010 | Ask/Bid VWAP, liquidity, and 0.30% deviation tests |
| TEST-011 | Paper adverse-slippage tests |
| TEST-012 | Paper Limit full-fill/no-fill tests |
| TEST-013 | Mock partial-fill protection resize tests |
| TEST-014 | Reduce-only TP/SL and no-reversal tests |
| TEST-015 | Mock repeated manual-close plan and cleanup tests |
| TEST-016 | Protection-triggered repeated close/opposite cleanup tests |
| TEST-017 | External full-close/partial-reduction reconciliation tests |
| TEST-018 | Paper cooldown restart plus mock state serialization tests |
| TEST-019 | Paper and exchange Emergency Stop restart tests |
| TEST-020 | Paper daily-risk reset/restart tests |
| TEST-021 | Daily-baseline readiness gate and restore invalidation test |
| TEST-022 | Profile isolation and secret-rejection tests |
| TEST-023 | Exact `LIVE` and relock policy tests |
| TEST-024 | Mode and cross-mode activity block tests |
| TEST-025 | Protective close/cancel availability during stale data tests |
| TEST-026 | Exact `DISABLE TP` / `DISABLE SL` tests and persistent mock state |
| TEST-027 | Exact `UNPROTECTED POSITION` tests |

## Milestone evidence

- Tickets 01–14: Paper engine, public market, strategy, execution, risk, profiles,
  audit/help, restart behavior, and advisory verification.
- Tickets 15–21: separate Testnet configuration, signed read-only adapter boundary,
  unmanaged-state policy, staged reconnect, guarded Market/Limit execution, persistent
  identities, TP/SL, safe close, external-change recovery, automatic recovery, and
  Testnet advisory evidence—all covered locally with mocks.
- Arabic desktop milestone: final seven-page Qt interface, RTL/mixed-direction text,
  cards/tables/forms/dialogs, mode-aware operations, risk/emergency controls, Help and
  audit surfaces, typed Live confirmations, and centralized font configuration.
- Tickets 22–27: Live Locked lifecycle, advisory activation policy, protection
  confirmations, shared managed execution safeguards, emergency workflows, PyInstaller
  packages, WinSW assets, and restore gating.
- Ticket 28: this matrix, `docs/final-checklist.md`, visual evidence, operations guide,
  package builds, and full automated release gate.

## External validation deliberately not claimed

- Real Gate.io Testnet REST/WebSocket authentication and exchange behavior.
- Any Live activation or Testnet/Live order submission.
- WinSW installation/restart and RDP disconnect on the target VPS.
- PostgreSQL backup/restore against the target database.
- Final Arabic glyph rendering with the operator-selected font on the VPS.
