# RangeBot v1 Milestone Plan

## Execution controls

- Implement tickets sequentially within an approved milestone.
- Run focused acceptance tests after each ticket. Run the full suite and Ruff at commit boundaries and at milestone end.
- Group closely related completed work into a small number of focused commits; do not create a commit for every ticket.
- Stop for failed checks, ambiguity, scope expansion, missing external access, or a safety concern.
- Do not begin a new milestone without explicit approval of its predecessor.
- At each milestone end, provide commits, changed files, tests, launch/demo instructions, manual checks, and remaining risks.

## 1. Paper Foundation

- **Goal:** Establish an isolated Paper account, public market visibility, explainable range evaluation, and safe entry previews.
- **Tickets:** 01 — Engine/UI heartbeat; 02 — Paper Account lifecycle; 03 — Paper watchlist and public market feed; 04 — Paper range analysis and decision details; 05 — Paper entry preview and Allocation Budget.
- **Required predecessor:** None. Ticket 01 has its own tested commit before ticket 02.
- **Manual review:** Paper isolation, restart persistence, market/history blocks, Arabic decision details, and Decimal sizing after reserve, fees, and rounding.
- **Safety risks / dependencies:** Public market availability, stale candles, contract rules, persistence, and credential exposure.
- **Completion criteria:** Tickets 01–05 are tested and committed; Paper setup, watchlist, analysis, and an allowed or blocked preview work without exchange credentials.

## 2. Complete Paper Trading

- **Goal:** Complete the backend Paper workflow for execution, protection, risk, automation, recovery, operator records, and advisory verification.
- **Tickets:** 06 — Paper manual Market Entry; 07 — Paper TP/SL protection; 08 — Paper close and cancellation controls; 09 — Paper daily risk and cooldown; 10 — Paper Limit Entry lifecycle; 11 — Paper automatic Market Entry and Used Signals; 12 — Paper Emergency Stop and restart recovery; 13 — Paper profiles, audit log, and Help Center; 14 — Paper verification record.
- **Required predecessor:** Milestone 1 — Paper Foundation.
- **Manual review:** Long/Short market and Limit workflows, TP/SL, close/cancel, risk/cooldown, automatic signals, Emergency Stop/Resume, profiles, Arabic audit/help content, and verification staleness.
- **Safety risks / dependencies:** Simulation/accounting errors, duplicate automation, stale-data protective actions, emergency recovery, and secret leakage.
- **Completion criteria:** Paper backend acceptance tests pass and the workflows persist safely across restart. Paper verification remains advisory only.
- **Temporary UI status:** The current Qt interface is an internal Paper-testing/debug surface. It is not the final product UI, is not polished, and is not release-ready. Swagger is also not a product UI.

## 3. Gate.io Testnet

- **Goal:** Prove exchange-integrated safeguards on Gate.io Testnet before any Live deployment work.
- **Tickets:** 15 — Testnet secure onboarding and read-only reconciliation; 16 — Testnet market/account readiness gate; 17 — Testnet safe Manual Market Entry; 18 — Testnet protection and managed closure; 19 — Testnet Limit Entry and partial-fill recovery; 20 — Testnet automatic trading, external changes, and recovery; 21 — Testnet verification evidence.
- **Required predecessor:** Milestone 2 — Complete Paper Trading.
- **Manual review:** Credential redaction, unmanaged-state resolution, readiness/reconnect gates, managed orders/protection, partial fills, external changes, restart reconciliation, and advisory evidence.
- **Safety risks / dependencies:** Testnet credentials, API/WebSocket availability, exchange configuration, freshness, reconciliation identity, and partial outcomes.
- **Completion criteria:** Tickets 15–21 are tested and committed; marked Testnet validation demonstrates guarded execution, protection, recovery, and advisory verification.

## 4. Arabic Desktop Control Interface

- **Goal:** Replace the temporary JSON-oriented Paper debug interface with the final usable Arabic RTL desktop control interface before Live Trading work begins.
- **Included scope:** Final Arabic RTL dashboard and navigation; readable mixed Arabic/English values; account, watchlist, active contract, range decision details, previews, manual/automatic entry controls, positions/protection, risk/cooldown, emergency operations, profiles, activity/audit log, Help Center, and verification status. Add focused UI tests and operator demos.
- **Required predecessor:** Milestone 3 — Gate.io Testnet.
- **Manual review:** Usability of real operator workflows without Swagger or raw JSON, RTL layout, clear state/error banners, confirmation flows, readable numbers/symbols, and accessibility of protection/emergency controls.
- **Safety risks / dependencies:** UI may obscure or misstate safety state, mixed-direction rendering defects, unsafe confirmation UX, and accidental dependence on a running desktop client for engine safety.
- **Completion criteria:** The temporary debug UI is replaced for operator use; each required workflow is usable in the desktop app; Arabic RTL and mixed values are manually verified; no UI action bypasses engine-side safeguards.
- **Non-goal:** This milestone does not add Live execution privilege or relax any Testnet/Live safety gate.

## 5. Live Deployment and Execution

- **Goal:** Deliver a safely locked Live deployment, guarded activation, high-risk confirmations, and managed execution capability.
- **Tickets:** 22 — Live deployment in locked state and read-only reconciliation; 23 — Live activation and advisory readiness warning; 24 — Live high-risk confirmations and protection controls; 25 — Live managed entry, TP/SL, and closing execution.
- **Required predecessor:** Milestone 4 — Arabic Desktop Control Interface.
- **Manual review:** Engine/UI packages and WinSW lifecycle, locked restart behavior, read-only reconciliation, unmanaged-state blocks, exact `LIVE` confirmation, and high-risk confirmations. Use Testnet or read-only/locked Live validation only; no real Live order is required.
- **Safety risks / dependencies:** Windows/VPS/WinSW behavior, Live access, PostgreSQL runtime configuration, real-account reconciliation, liquidity/slippage, confirmations, and protection failures.
- **Completion criteria:** Tickets 22–25 are tested and committed; Live remains locked until current safety checks and confirmations pass; no real Live order is required for approval.

## 6. Final Operations and Acceptance

- **Goal:** Validate Live emergency/recovery procedures and consolidate version-one acceptance evidence.
- **Tickets:** 26 — Live service lifecycle and emergency-operation validation; 27 — Live backup/restore operating procedure; 28 — Version-one acceptance and deployment evidence.
- **Required predecessor:** Milestone 5 — Live Deployment and Execution.
- **Manual review:** Emergency Stop and fresh-action Emergency Close failure handling, PostgreSQL backup/restore, post-restore reconciliation, final RTL presentation, Testnet evidence, Live operational checks, and remaining non-blocking choices.
- **Safety risks / dependencies:** Service/VPS/connectivity/exchange/PostgreSQL failures, restore protection state, unmanaged exchange changes, and incomplete evidence.
- **Completion criteria:** Tickets 26–28 are tested and committed; emergency and backup/restore evidence is recorded; TEST-001 through TEST-027 map to automated or documented manual evidence; advisory verification remains distinct from Live activation gates.
