# RangeBot Beginner Testing Guide

Updated: 2026-07-21

This guide is for a user who wants to understand and test RangeBot without risking real funds. It follows the current workflow implemented in the React control panel.

> **Safety rule:** use **Paper** first. Do not test a new strategy with Live funds. Testnet is useful later for exchange connectivity, but Paper is the correct first step for strategy behavior.

## 1. The mental model

RangeBot now separates five things that are easy to confuse:

1. **Strategy Type** — the Python implementation, such as Fixed Price Ladder or Range Breakout.
2. **Strategy Template** — reusable trading rules that are not tied to one coin.
3. **Coin Setup** — one template applied to one contract, such as `BTC_USDT`.
4. **Backtest** — a historical simulation of one exact coin-setup revision.
5. **Bot Deployment** — the frozen approved version that can monitor or trade.

The normal path is:

```text
Strategy Template
      ↓
Coin Setup
      ↓
Historical Backtest
      ↓
Approve for Paper
      ↓
Create Bot Deployment
      ↓
Monitoring
      ↓
Paper Trading
```

A **revision** is a saved version. Changing the strategy or coin setup creates a new revision because an old backtest should not silently approve new settings.

## 2. Before the first test

1. Create a backup from **النسخ الاحتياطية والسجلات**.
2. Confirm the selected environment is **Paper**.
3. Confirm Emergency Stop is available and currently understood.
4. Do not enter or enable Live credentials for this first test.
5. Use a small imaginary Paper budget even though no real funds are used.

## 3. Recommended first strategy: Fixed Price Ladder

Use **سلم الأسعار الثابت / Fixed Price Ladder** first if your goal is:

- place several Long limit entries at exact prices;
- combine filled entries into one position;
- calculate the weighted-average entry price;
- move one reduce-only take-profit order based on that average.

This strategy is Long-only, isolated-margin, one-way futures trading. It is not Spot ownership.

### Safe example configuration

The values below are only a learning example. Replace the symbol and prices with valid values for the contract being tested.

| Setting | Beginner value |
| --- | --- |
| Environment | Paper |
| Direction | Long only |
| Margin mode | Isolated |
| Leverage | 1x |
| Total budget | 30 USDT |
| Budget basis | Margin budget |
| Allocation | Equal |
| Entry levels | 3 |
| Placement | All at once |
| Post-only | Off for the first test |
| Allow immediate fill | Off |
| Take-profit mode | Percentage from weighted average |
| Take-profit value | 5% |
| Fee handling | Net after estimated fees, when available |
| Stop-loss | 3% below the lowest entry for a controlled test |
| Cycle policy | One shot |
| Repeat | Off |

Example levels for a contract trading near `0.08852` could be:

```text
Level 1: 0.085
Level 2: 0.084
Level 3: 0.083
```

These values are **not** sensible for a market trading near `0.8852`; they would be about 90% lower. Always check the decimal place before saving.

With equal allocation and a 30 USDT margin budget, each level receives approximately 10 USDT of margin before contract rounding and fees.

## 4. Create the strategy and coin setup

1. Open **الاستراتيجيات**.
2. Select **إنشاء استراتيجية**.
3. Choose **سلم الأسعار الثابت**.
4. Give it a clear name, such as `Three-Level Paper Ladder`.
5. Enter the ladder rules and safe defaults.
6. Save the strategy template.
7. In its card, add one Gate.io USDT perpetual symbol, such as `BTC_USDT`.
8. Open the new coin setup.
9. Confirm the displayed exchange, market, symbol, price timestamp, leverage, budget, entries, take-profit, and stop-loss.
10. Save only when the values match the intended test.

## 5. Run the first historical backtest

Open **الاختبار التاريخي** and use these beginner defaults:

| Backtest setting | Recommended first value |
| --- | --- |
| Opportunity source | Manual symbols |
| Symbols | One symbol only |
| Period | Last 90 days |
| Warm-up candles | 200 |
| Starting balance | 1,000 USDT |
| Position sizing | Fixed quote/margin |
| Margin per trade | Same as the setup budget |
| Maximum simultaneous positions | 1 |
| Maker fee | 0.0002 |
| Taker fee | 0.0005 |
| Slippage | 5 basis points |
| Bid/ask spread | 2 basis points |
| Intrabar ambiguity | Conservative: stop-loss first |
| Fallback take-profit | 5% |
| Fallback stop-loss | 3% |

Why use the conservative ambiguity policy? A historical candle may touch both the take-profit and stop-loss, but ordinary candle data does not reveal which happened first. Assuming the stop-loss happened first prevents an unrealistically favorable result.

### Before pressing Run

Read the review step and verify:

- the correct setup and setup revision are selected;
- the symbol and date range are correct;
- fees, spread, and slippage are not zero;
- maximum positions is 1 for the first test;
- the test clearly says it will not send Paper or Gate.io orders.

## 6. How to judge the result

Do not judge a strategy using only net return.

Check these fields together:

- **Number of trades:** fewer than five trades is usually too little evidence.
- **Maximum drawdown:** how far equity fell from a previous peak.
- **Net return:** after fees and simulated execution costs.
- **Profit factor:** gross profit divided by gross loss.
- **Win rate:** useful, but a high win rate can still hide large losses.
- **Expectancy per trade:** the average expected result of one trade.
- **Fees and slippage:** confirm they did not consume most of the profit.
- **Ambiguous trades:** inspect them; too many means the timeframe may be too coarse.
- **Equity curve:** look for steady behavior rather than one lucky trade.

### Common result meanings

- **No trades:** the strategy did not receive its entry conditions during the selected period, the ladder prices were never reached, or the data/rules were incomplete.
- **Promising:** suitable for further Paper testing, not proof that it will make money.
- **Mixed:** some useful behavior, but important weaknesses or insufficient consistency.
- **Weak:** do not approve it merely to continue the workflow.
- **Insufficient data:** use a longer period or reconsider the symbol/timeframe.

## 7. Approve and deploy safely

The current UI can explicitly approve a setup without a current backtest. A beginner should **not use that shortcut**.

After a reasonable backtest:

1. Return to the coin setup review.
2. Confirm the backtest belongs to the current setup revision.
3. Approve **Paper** only.
4. Create the bot deployment.
5. Open **التداول**.
6. Start **Monitoring** first.
7. Confirm the bot produces explanations and does not submit orders while monitoring.
8. Stop monitoring.
9. Start **Paper Trading** only after the monitoring behavior looks correct.

## 8. Paper-trading test checklist

### Test A — Order creation

Expected behavior:

- exactly the configured enabled ladder orders are created;
- each order uses the correct contract, side, price, and calculated quantity;
- total required balance includes fee reserve and safety reserve;
- no duplicate orders appear after refresh.

### Test B — One level fills

Expected behavior:

- the pending order becomes a fill;
- one Long position is shown;
- average entry equals the first fill price;
- take-profit is calculated from the actual fill, not merely the configured price;
- remaining entry orders stay pending if the strategy allows them.

### Test C — Multiple levels fill

Expected behavior:

- all fills belong to the same Long position;
- quantity is the sum of filled quantities;
- average entry is quantity-weighted;
- the old take-profit is safely replaced with one reduce-only take-profit based on the new average;
- the take-profit quantity does not exceed the open position.

Weighted average formula:

```text
Average entry =
(sum of fill price × fill quantity)
÷
(sum of fill quantity)
```

### Test D — Take-profit closes the position

Expected behavior:

- the reduce-only exit closes only the owned position quantity;
- realized P&L, fees, and trade history are recorded;
- the position becomes closed;
- one-shot mode does not silently create a new ladder.

### Test E — Emergency Stop

While entry orders are pending:

1. Activate Emergency Stop.
2. Confirm new entries are blocked.
3. Confirm pending entry orders are cancelled according to the safety policy.
4. Confirm existing position reconciliation and protection continue.
5. Restart RangeBot and confirm Emergency Stop remains active.
6. Resume only after reviewing the state.

### Test F — Restart recovery

With pending orders or an open Paper position:

1. Close the browser.
2. Reopen RangeBot.
3. Confirm the engine restores the same strategy, deployment, pending orders, fills, position, and protection.
4. Confirm no duplicate order is submitted during recovery.

### Test G — Invalid configuration

Try saving deliberately invalid values one at a time:

- duplicate ladder prices;
- Long ladder prices ordered lowest to highest;
- custom weights not totaling 100%;
- budget smaller than required fees/reserve;
- stop-loss mode enabled without a value;
- repeat policy selected while repeat is disabled.

Expected behavior: the UI or API must reject the configuration with a clear explanation and submit no order.

## 9. When to try Testnet

Move to Testnet only after all Paper tests above pass.

Testnet is for checking:

- API credentials;
- Gate.io contract rules and quantity rounding;
- real REST/WebSocket behavior;
- exchange acknowledgements, partial fills, cancellations, and reconciliation;
- protective-order behavior against exchange state.

Use the smallest permitted contract size. Testnet performance is not proof of Live profitability.

## 10. Do not use Live yet unless all are true

- Paper behavior is understood and repeatable.
- Restart and Emergency Stop tests pass.
- Testnet reconciliation passes.
- Contract quantity and leverage are understood.
- Maximum loss is explicitly limited.
- API key has no withdrawal permission.
- The exact deployed setup revision was reviewed.
- You can explain every open order, position, stop, target, and risk limit shown by the app.

## 11. Current usability issues to remember during testing

The current code still contains both the newer template/setup/deployment workflow and parts of the older instance-based workflow. This can make similarly named screens feel inconsistent.

Also, advanced backtest settings are visible immediately. For the first test, keep the recommended values above instead of optimizing many variables at once. Change one setting per test and write down why it changed.

## 12. Record evidence

For every meaningful test, save:

- strategy and setup revision numbers;
- symbol and environment;
- configuration values;
- date range and fees/slippage assumptions;
- backtest result ID;
- screenshots before and after fills;
- expected behavior;
- actual behavior;
- whether the test passed;
- any error message exactly as displayed.

A failure with clear evidence is useful. Do not repeatedly click Start or resubmit an order when the state is unclear; stop and inspect the activity log first.
