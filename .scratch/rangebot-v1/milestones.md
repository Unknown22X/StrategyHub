# RangeBot v1 Milestone Plan

## File and execution controls

- Create only `.scratch/rangebot-v1/milestones.md`; do not edit ticket files or application code when maintaining this plan.
- Write the file using UTF-8 without a BOM and verify it decodes as UTF-8 before completion. Preserve typographic characters such as `—` and `–` exactly; do not use corrupted mojibake text.
- Before ticket 02 begins, verify ticket 01 has its own tested commit. The current checkout shows `a214ce1 Add engine UI heartbeat` at `HEAD`; if that commit is absent when execution starts, create the dedicated ticket-01 commit first.

## 1. Paper Foundation

- **Goal:** Establish an isolated Paper account, public market visibility, explainable range evaluation, and safe entry previews.
- **Tickets:**
  - [x] 01 — Engine/UI heartbeat
  - [ ] 02 — Paper Account lifecycle
  - [ ] 03 — Paper watchlist and public market feed
  - [ ] 04 — Paper range analysis and decision details
  - [ ] 05 — Paper entry preview and Allocation Budget
- **Required predecessor:** None; ticket 01’s dedicated tested commit is required before ticket 02.
- **Manual review before approval:** Verify Paper isolation from real credentials/accounts, Arabic RTL rendering, restart persistence, market/history readiness blocks, decision explanations, and Decimal sizing after fees, reserve, and rounding.
- **Safety risks / dependencies:** Gate.io public data availability and integrity, stale/incomplete candles, contract-rule rounding, persistence failures, and accidental credential exposure.
- **Completion criteria:** Tickets 01–05 have separate tested commits; tickets 02–05 acceptance tests pass; a Paper-only demo safely completes account setup, watchlist selection, analysis, and an allowed or blocked entry preview.

### Expected manual test after Milestone 1

- Launch the engine locally and confirm `/health` reports `lifecycle: running`.
- Open `/docs`, initialize or inspect the Paper account, and confirm no real exchange credentials are requested or used.
- Search eligible public contracts, add one Paper watchlist contract, set it active, and confirm the watchlist shows active versus monitoring-only state and public last price when data is available.
- Submit range-analysis examples for ready, warming-up, and history-gap cases; expect Arabic decision details and blocked-entry explanations when history or range rules fail.
- Submit an entry preview; expect Decimal-safe margin, quantity, reserve, fees, TP/SL, liquidation estimate, and stale-preview validation without placing any order.

## 2. Complete Paper Trading

- **Goal:** Complete the simulated-trading workflow with protection, risk controls, automation, recovery, operator tools, and verification evidence.
- **Tickets:**
  - [ ] 06 — Paper manual Market Entry
  - [ ] 07 — Paper TP/SL protection
  - [ ] 08 — Paper close and cancellation controls
  - [ ] 09 — Paper daily risk and cooldown
  - [ ] 10 — Paper Limit Entry lifecycle
  - [ ] 11 — Paper automatic Market Entry and Used Signals
  - [ ] 12 — Paper Emergency Stop and restart recovery
  - [ ] 13 — Paper profiles, audit log, and Help Center
  - [ ] 14 — Paper verification record
- **Required predecessor:** Milestone 1 — Paper Foundation.
- **Manual review before approval:** Exercise Long/Short entry, TP/SL, close/cancel, risk and cooldown blocks, limit expiry, automatic-signal reset, Emergency Stop/Resume, restart recovery, profiles, redacted Arabic logs, and Paper-verification staleness.
- **Safety risks / dependencies:** Incorrect fill/fee/partial-quantity simulation, duplicate automatic entries, unavailable protective actions during stale data, stale emergency actions, and secret leakage in logs or UI.
- **Completion criteria:** Tickets 06–14 have separate tested commits and passing acceptance tests; the complete Paper workflow survives restart and enforces entry, risk, protection, and emergency safeguards; Paper evidence remains advisory only.

### Expected manual test after Milestone 2

- Start with a Paper-only account and a watched active contract; create Long and Short simulated market entries.
- Confirm TP/SL protection is created in Paper state, can be inspected, and remains available even when new entries are blocked.
- Close positions and cancel pending entries; expect balances, fees, realized results, and audit entries to update without exchange activity.
- Trigger daily-risk and cooldown blocks; expect clear Arabic explanations and no duplicate automatic entries.
- Create, partially fill, expire, and recover Paper limit entries across restart.
- Use Emergency Stop and Resume; expect automation to stop immediately and restart recovery to reconcile Paper state.
- Generate the Paper verification record; expect it to be advisory only and clearly marked stale when inputs change.

## 3. Gate.io Testnet

- **Goal:** Prove exchange-integrated execution safeguards on Gate.io Testnet before any Live deployment work.
- **Tickets:**
  - [ ] 15 — Testnet secure onboarding and read-only reconciliation
  - [ ] 16 — Testnet market/account readiness gate
  - [ ] 17 — Testnet safe Manual Market Entry
  - [ ] 18 — Testnet protection and managed closure
  - [ ] 19 — Testnet Limit Entry and partial-fill recovery
  - [ ] 20 — Testnet automatic trading, external changes, and recovery
  - [ ] 21 — Testnet verification evidence
- **Required predecessor:** Milestone 2 — Complete Paper Trading.
- **Manual review before approval:** Verify credential redaction, resolve unmanaged Testnet state externally, demonstrate readiness/reconnect gates, inspect Market/Limit and partial-fill behavior, protection restoration, external changes, restart reconciliation, and advisory evidence.
- **Safety risks / dependencies:** Testnet credentials and API/WebSocket availability, exchange configuration compatibility, data freshness, identity-based reconciliation, and uncertain or partial exchange outcomes.
- **Completion criteria:** Tickets 15–21 have separate tested commits and passing acceptance tests; marked Testnet validation demonstrates reconciliation, guarded execution, protection, and recovery; readiness evidence is not a Live-activation gate.

### Expected manual test after Milestone 3

- Configure Testnet credentials only when available; if credentials or API access are missing, stop and ask for direction instead of forcing a fake integration.
- Confirm secrets are redacted in logs, UI, screenshots, errors, and audit entries.
- Run read-only reconciliation against Testnet; expect unmanaged or unknown state to block execution until resolved externally.
- Demonstrate readiness and reconnect gates by simulating stale market data or unavailable account data.
- Place Testnet-only market and limit entries, then inspect managed TP/SL, partial-fill recovery, external-state changes, and restart reconciliation.
- Produce Testnet verification evidence; expect it to support review but not automatically unlock Live activation.

## 4. Live Deployment and Execution

- **Goal:** Deliver a safely locked Live deployment, guarded activation, high-risk confirmations, and managed execution capability.
- **Tickets:**
  - [ ] 22 — Live deployment in locked state and read-only reconciliation
  - [ ] 23 — Live activation and advisory readiness warning
  - [ ] 24 — Live high-risk confirmations and protection controls
  - [ ] 25 — Live managed entry, TP/SL, and closing execution
- **Required predecessor:** Milestone 3 — Gate.io Testnet.
- **Manual review before approval:** Confirm engine/UI packages and WinSW lifecycle, locked restart behavior, read-only reconciliation, unmanaged-state blocks, exact `LIVE` confirmation, and high-risk confirmations. Validate execution readiness through Testnet or read-only/locked Live checks only; do not require or place a real Live order unless explicitly authorized.
- **Safety risks / dependencies:** Windows/VPS and WinSW behavior, Live credentials/access, explicit PostgreSQL runtime configuration, real-account reconciliation, liquidity/slippage controls, typed confirmations, and protection failures.
- **Completion criteria:** Tickets 22–25 have separate tested commits and passing acceptance tests; deployment and service behavior work as specified; Live remains locked until current real safety checks and confirmations pass; no real Live order is required for milestone approval.

### Expected manual test after Milestone 4

- Install or launch the packaged engine/UI and confirm the WinSW service lifecycle works across start, stop, restart, and machine reboot where applicable.
- Confirm Live mode starts locked, remains locked after restart, and blocks execution until explicit activation checks pass.
- Run read-only Live reconciliation only; expect unmanaged real-account state to block activation and execution.
- Type the exact `LIVE` confirmation and inspect high-risk confirmation prompts, but do not place a real Live order unless the user explicitly authorizes it.
- Validate execution readiness with Testnet or read-only/locked Live checks; expect the milestone to be approvable without a real Live order.

## 5. Final Operations and Acceptance

- **Goal:** Validate Live emergency operations and recovery procedures, then consolidate version-one acceptance evidence.
- **Tickets:**
  - [ ] 26 — Live service lifecycle and emergency-operation validation
  - [ ] 27 — Live backup/restore operating procedure
  - [ ] 28 — Version-one acceptance and deployment evidence
- **Required predecessor:** Milestone 4 — Live Deployment and Execution.
- **Manual review before final acceptance:** Validate Emergency Stop and fresh-action Emergency Close failure handling; perform and review PostgreSQL backup/restore; inspect post-restore reconciliation and entry blocking; review the acceptance matrix, RTL presentation, Testnet evidence, Live operational checks, and remaining non-blocking choices.
- **Safety risks / dependencies:** Service, process, VPS, connectivity, exchange, and PostgreSQL failures; protection state after restore; unmanaged exchange-state mutation; incomplete acceptance evidence.
- **Completion criteria:** Tickets 26–28 have separate tested commits and passing acceptance tests; emergency-operation and backup/restore evidence is recorded; TEST-001 through TEST-027 map to automated or documented manual evidence; handoff distinguishes advisory readiness evidence from Live-activation safety gates.

### Expected manual test after Milestone 5

- Validate Emergency Stop and fresh-action Emergency Close behavior in the safest available environment; use Testnet or locked/read-only Live unless the user explicitly authorizes real Live action.
- Simulate service/process/connectivity failures and confirm recovery behavior is documented and operator-visible.
- Perform a PostgreSQL backup and restore procedure; expect restored state to reconcile before allowing new entries.
- Inspect the final acceptance matrix and confirm each TEST-001 through TEST-027 item maps to automated evidence or documented manual evidence.
- Review remaining risks and non-blocking choices; expect advisory readiness evidence to stay separate from Live-activation safety gates.

## Execution policy

- Implement tickets sequentially within an approved milestone.
- Make a separate tested commit for each ticket.
- Run the ticket’s acceptance tests before starting the next ticket.
- Prefer targeted tests for the ticket and changed files first. Do not rerun broad tests that already passed unless the change touches shared infrastructure, a previous failure needs confirmation, or the user explicitly asks for a full rerun.
- Run a broader suite at milestone end only when it gives new confidence proportional to the changed surface area.
- Stop immediately for failed tests, ambiguity, scope expansion, missing external access, missing API credentials/access, unavailable external systems, or a safety concern.
- If something cannot work because a required API, credential, service, or external permission is missing, stop and ask the user instead of forcing a workaround that would misrepresent the feature.
- Do not start a new milestone until the user explicitly approves the previous one.
- At each milestone end, provide a consolidated summary with commits, changed files, tests run, how to launch/demo it, expected manual checks, and remaining risks.
