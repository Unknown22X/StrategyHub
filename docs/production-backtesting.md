# Production historical backtesting

Updated: 2026-07-19

RangeBot now uses one deterministic `BacktestEngine` for manual-symbol and
historical-scanner runs. Both modes reuse the registered strategy evaluator,
normalized closed candles, strategy scanner, setup revision, execution defaults,
portfolio constraints, and Gate contract rules. Simulated events are persisted
under backtest-only tables and never enter Paper, Testnet, or Live order state.

## Flow and event order

The shared flow is:

`Opportunity source → Strategy evaluator → Portfolio manager → Order/fill simulator → Position manager → Performance analyzer`

For every chronological candle the engine:

1. fills eligible orders created after an earlier candle close;
2. processes gaps and intrabar limit/stop/target interactions;
3. updates cash, positions, fees, DCA average entry, and realized P&L;
4. closes the candle and exposes only candles closed by that timestamp;
5. evaluates scanner qualification separately from the strategy entry trigger;
6. ranks simultaneous candidates by score and then symbol;
7. applies position, symbol-exposure, cooldown, and available-balance limits;
8. submits new orders that can first execute on later market data;
9. records decisions, candidates, orders, fills, equity, and drawdown.

Higher-timeframe contexts contain only candles fully closed by the decision
timestamp. Warm-up candles initialize strategy calculations but cannot generate
reported-period trades.

## Execution model

- Market entries fill at the next eligible candle open with adverse slippage
  plus half the configured bid/ask spread. The same adverse half-spread applies
  to market exits.
- Limit entries begin checking only after submission and may expire.
- Candle-volume partial fills are intentionally out of phase-one scope; accepted
  orders fill completely after rounding and contract validation.
- Entry and exit fees are recorded separately using Maker/Taker assumptions.
- Stops that gap execute from the available open with adverse slippage.
- Stop/target collisions record an ambiguity flag. Conservative is the default;
  optimistic is explicit. Lower-timeframe resolution falls back conservatively
  when no lower-timeframe series is supplied.
- DCA fills share one position, recalculate weighted-average entry, and may
  recalculate a percentage target. Unfilled levels remain pending until fill,
  expiration, cancellation, or position closure.
- Time exits are decided after a candle closes and execute no earlier than the
  following candle open.

## Persistence and APIs

Migration `0030_production_backtesting` adds an immutable portfolio-run record
and candidate, decision, order, and fill logs. Separate SHA-256 hashes identify
the immutable configuration and the exact candle/additional-timeframe/contract
rule inputs. The engine code version is captured automatically when the caller
does not supply one. Post-test observations are editable without changing the
request or result.

Main endpoints:

- `POST /v1/backtests/portfolio/readiness`
- `POST /v1/backtests/portfolio`
- `GET /v1/backtests/portfolio`
- `GET /v1/backtests/portfolio/{backtest_id}`
- `PUT /v1/backtests/portfolio/{backtest_id}/notes`

Runs are queued and executed as server background work. Persisted stages are
queued, loading data, running, calculating results, completed, and failed. The
React UI polls the run record and shows the current Arabic stage. Simulation
execution is serialized so research runs cannot fan out without a bound. If the
engine restarts mid-run, the nonterminal record becomes an explicit failed run
instead of remaining stuck or appearing successful; its immutable request can
be inspected and submitted as a new run.

## Phase-one limitations

- Gate does not currently provide a complete local listing/delisting history,
  so scanner replay declares `current_survivor` universe quality and warns about
  survivor bias.
- Candle simulation cannot infer the true intrabar path. Ambiguity is explicit.
- Tick execution, complex partial fills, optimization, Monte Carlo, walk-forward
  testing, and parameter search are intentionally deferred.
- Historical funding remains zero when the provider cannot supply a reproducible
  funding series and the result shows that warning.
