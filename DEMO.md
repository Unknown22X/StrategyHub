# StrategyHub — Build Week Demo Script

## Goal

Record a truthful demo in **under three minutes** using **Paper** only. Do not enter or display Gate.io Credentials. Do not switch to Live. Do not imply that Paper or Backtest results guarantee profit.

## Prepare before recording

1. Install or launch the final Windows build.
2. Confirm the authoritative environment badge says **PAPER**.
3. Confirm Emergency Stop is off before the Order step.
4. Confirm public internet access and that `BTC_USDT` shows a fresh or clearly labeled price.
5. Prepare one stopped Paper Strategy Instance named:

   ```text
   BTC Paper Ladder Demo
   ```

   Recommended Template: **Fixed Price Ladder**. Use conservative `1x` Leverage and a small Paper budget.
6. Prepare one completed Backtest result. Do not rely on running a Backtest during the recording unless it has already been tested immediately beforehand.
7. Close the Gate Credential drawer and any page containing private information.
8. Remove or archive confusing temporary Strategies. Do not delete historical records merely to clean the screen.
9. Use 100% browser zoom unless the interface is clipped. Prefer a 16:9 recording area.
10. Rehearse the Paper Order once and close the Position before starting the final recording.

## Primary demo route — approximately 2 minutes 40 seconds

### 0:00–0:18 — Story and safety

**Screen:** StrategyHub dashboard with the PAPER badge visible.

**Say:**

> “I built StrategyHub for my dad. He wanted to understand and test trading Strategies without having to decode every exchange and bot term first. StrategyHub is a local-first operations app that separates Paper, Testnet, and Live, and this entire demo uses Paper mode with no real funds.”

Point briefly to the persistent **PAPER** badge.

### 0:18–0:55 — Paper Order Preview

**Clicks:**

1. Select **Manual Trade**.
2. Confirm the drawer says **PAPER**.
3. Search or select `BTC_USDT`.
4. Choose **Market**.
5. Choose **Long**.
6. Use a small Margin and `1x` Leverage.
7. Select **Preview**.

**Say:**

> “The contract picker uses Gate.io public market data and shows its freshness. Paper does not need private Gate Credentials. Before any Order, the central Order Manager calculates Quantity, Margin, Leverage, fees, Take Profit, Stop Loss, and safety validation.”

Pause on the Preview so Quantity, Margin, fee, Take Profit, and Stop Loss are visible.

### 0:55–1:18 — Submit, Position, protection, and close

**Clicks:**

1. Select **Submit**.
2. Open or scroll to the resulting Paper Position.
3. Point to Entry, Quantity, current PnL, Take Profit, and Stop Loss.
4. Select **Close Position** and confirm.

**Say:**

> “Submitting creates a local Paper Position. StrategyHub shows the Position, updated PnL, and its protection. Closing it records the Trade without contacting a private Live endpoint.”

### 1:18–1:58 — Direct Strategy start and immutable Run

**Clicks:**

1. Open **Strategies**.
2. Open `BTC Paper Ladder Demo`.
3. Show the Strategy command center: symbol, live price state, PnL, Win Rate, Drawdown, health, activity, and any genuinely attributed Position or Orders.
4. Point to the readiness panel and **Never Backtested** warning if present.
5. Select **Start**.
6. Show the green Running status or sidebar shortcut.
7. Select **Stop**.

**Say:**

> “A Strategy Instance can start directly in Paper. Backtesting is optional, so ‘Never Backtested’ is a warning, not a universal blocker. When it starts, StrategyHub stores an immutable Run snapshot, which means later edits cannot silently change a running Strategy.”

Do not claim a Position or Order belongs to this Strategy unless the page actually attributes it.

### 1:58–2:20 — Opportunities

**Clicks:**

1. Open **Opportunities**.
2. Select **Review details** on one saved Opportunity.
3. Show **Shortlist**, **Ignore**, and **Create Strategy Instance for this coin**.
4. Open the Strategy selector and briefly show Fixed Price Ladder or another compatible Template.

**Say:**

> “Opportunities are research leads, not Trades. Review explains why a coin qualified, Shortlist does not start trading, Ignore supports Undo, and I can create a stopped Paper Strategy Instance using another compatible Template.”

### 2:20–2:38 — Backtesting

**Clicks:**

1. Open **Backtesting**.
2. Open the prepared completed result.
3. Show return, Drawdown, Win Rate, fees, warnings, and the stored assumptions.

**Say:**

> “Backtesting has a conservative beginner preset, advanced assumptions stay optional, and runs now have cancellation, bounded polling, retry handling, and structured failure stages. The result is research—not a profit promise.”

Do not wait for a new long Backtest during the recording.

### 2:38–2:55 — Risk Management and environment separation

**Clicks:**

1. Open **Risk Management**.
2. Point to the three explicit Enable/Disable toggles.
3. Point to Emergency Stop.
4. Briefly open the environment selector without switching away from Paper.

**Say:**

> “Daily risk policies can be explicitly enabled or disabled without fake huge values, while fundamental safety checks remain mandatory. Emergency Stop persists across restart. Paper, Testnet, and Live use separate authoritative runtime states and Credential profiles.”

### 2:55–3:00 — GPT-5.6 and Codex

**Screen:** Return to the dashboard or Strategy page.

**Say:**

> “GPT-5.6 helped me reason through the trading UX and safety model, and Codex inspected, implemented, migrated, tested, and packaged the repository milestone by milestone.”

Stop recording.

## Recovery if a step fails

### Contract price is unavailable

- Keep the screen visible long enough to show the honest stale/unavailable state.
- Say: “Public market data is unavailable right now, so StrategyHub refuses to present it as fresh.”
- Use a manually entered `BTC_USDT` symbol only if Preview validation works.

### Paper Preview says Quantity is zero

- Increase the Paper Margin slightly or keep `1x` Leverage.
- Do not change to Live or bypass validation.
- Explain that contract rounding produced zero and the app returned a structured blocker instead of crashing.

### Position does not appear immediately

- Select the page refresh action once.
- Do not repeatedly submit the same Order.
- If it remains unavailable, use the backup route and show an existing recorded Paper Trade.

### Strategy does not start

- Read the exact readiness reason.
- Confirm the Strategy environment is Paper and Emergency Stop is off.
- Do not remove a genuine blocker merely to finish the recording.
- Use an already verified stopped Paper Strategy Instance.

### Opportunities list is empty

- Use a previously saved Opportunity.
- Do not run a long scanner during the recording.
- If no saved item exists, skip this section and mention that the scanner requires current public market access.

### Backtest is not ready

- Open a prepared completed result.
- Do not wait through network retries in the final video.
- If no result exists, show the beginner preset and explain the reliability controls without claiming a completed run.

## Backup demo route — approximately 90 seconds

Use this route when market access or Backtesting is unstable:

1. **Dashboard:** explain the project for your dad and point to PAPER.
2. **Existing Paper Trade:** open Trade History and show a previously completed local Paper Trade with no private data.
3. **Strategy Instance:** show readiness, immutable Run snapshot information, Start, Running status, and Stop.
4. **Opportunities:** open a saved Review and show Shortlist/Ignore/compatible Strategy selection.
5. **Risk Management:** show explicit toggles and Emergency Stop.
6. **Finish:** explain GPT-5.6, Codex, and that no real funds were used.

## Recording checklist

- Video duration is below three minutes.
- PAPER is visible before any Order action.
- No API key, secret, Credential status detail, private balance, or personal path is exposed.
- No fabricated PnL or performance claim is made.
- No Live confirmation is entered.
- No real Gate.io Order is submitted.
- The final frame is clean and readable.
