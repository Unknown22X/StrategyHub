# RangeBot v1 Milestone Plan

## File and execution controls

- Create only `.scratch/rangebot-v1/milestones.md`; do not edit ticket files or application code.
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

## Execution policy

- Implement tickets sequentially within an approved milestone.
- Make a separate tested commit for each ticket.
- Run the ticket’s acceptance tests before starting the next ticket.
- Stop immediately for failed tests, ambiguity, scope expansion, missing external access, or a safety concern.
- Do not start a new milestone until the user explicitly approves the previous one.
- At each milestone end, provide a consolidated summary with commits, changed files, tests run, how to launch/demo it, and remaining risks.
