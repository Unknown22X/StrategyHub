# RangeBot final end-to-end checklist

This checklist is intentionally the only stage that uses external systems. Complete
Paper first, then Testnet, and leave Live locked. Never use a key with withdrawal
permission.

## 1. Build and install

- Run `uv sync`, `uv run ruff check .`, and `uv run pytest -q`.
- Build `deploy/engine.spec` and `deploy/ui.spec` with PyInstaller; verify two
  independent `onedir` outputs and confirm `.env` is absent from both.
- Create `C:\RangeBot\engine`, `ui`, `config`, `logs`, `service`, and `backup`.
- Install PostgreSQL bound to `127.0.0.1`; create the RangeBot database/user.
- Put `.env` only under `config`, restrict its Windows ACL, and keep it outside Git.
- Install WinSW with `deploy\install-service.ps1`; confirm automatic start and crash
  restart. Close the UI and disconnect RDP; confirm the engine service remains alive.

## 2. Arabic desktop UI

- Confirm all seven Arabic RTL pages, keyboard order, dialogs, tables, cards, and
  mixed `BTC_USDT`, prices, percentages, and timestamps render correctly.
- Confirm no normal workflow displays raw JSON and the chosen Arabic font can be
  applied through the centralized font setting.
- Confirm the dashboard always shows connection, mode, Live Locked, balance,
  active contract, position, liquidation price, TP/SL, cooldown, daily risk, and
  Emergency Stop state.
- Confirm blocked actions show an Arabic reason and emergency controls remain visible.

## 3. Paper acceptance

- Initialize/reset the Paper Account, manage the watchlist, inspect range decisions,
  and validate Long/Short manual Market and Limit workflows.
- Exercise TP, SL, partial close, full close, cancellation, daily risk, cooldown,
  Used Signal reset, Emergency Stop/RESUME, profiles, audit log, and Help Center.
- Restart the engine and UI; confirm state recovery and record advisory Paper evidence.

## 4. Gate.io Testnet acceptance

- Add Testnet-only credentials with withdrawals disabled and IP allowlisting; start
  the engine with signed read-only exchange access.
- Reconcile balance, One-way mode, Cross margin, 1x/5x/10x leverage, positions,
  entries, TP, and SL. Resolve Unmanaged Exchange State only on Gate.io, then refresh.
- Verify stale data at 10 seconds and reconnect stages: subscription confirmation,
  REST snapshot, two newer WebSocket updates, and account reconciliation.
- With explicit operator control, validate persistent identity, timeout reconciliation,
  0.30% market deviation guard, Market/Limit fills, expiry, partial fills, protection
  restoration, external reductions/closure, safe close, restart, and automatic recovery.
- Record advisory Testnet evidence tied to the current build/profile.

## 5. Backup and restore

- Stop the service intentionally and run `deploy\backup-postgresql.ps1`.
- Restore to a controlled database with `deploy\restore-postgresql.ps1` and the exact
  confirmation `RESTORE RANGEBOT`.
- Restart with `--restored-state`; confirm Live is locked and all entries remain
  blocked until database validation, exchange reconciliation, and TP/SL validation pass.

## 6. Locked Live readiness — no real order required

- Start Live with PostgreSQL and read-only reconciliation. Confirm every restart,
  service stop, and Emergency Stop returns to Live Locked.
- Confirm unmatched positions/orders/protection are read-only and block mutations.
- Confirm incorrect `LIVE`, `DISABLE TP`, `DISABLE SL`, and `UNPROTECTED POSITION`
  text is rejected; advisory Paper/Testnet evidence never substitutes for current
  safety checks.
- Confirm Emergency Stop cancels only managed pending entries and preserves protection;
  Emergency Close requires fresh reconciliation and never queues a later close.
- Do not activate Live or submit a Live order during acceptance. Activation/execution
  remains a separate future operator decision.
