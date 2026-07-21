# Adding a RangeBot strategy type

RangeBot discovers strategy types from Python modules in
`src/rangebot/strategies/`. The frontend does not contain a hard-coded list of
strategy names. It requests `/v1/strategy-types` and renders the returned
metadata, candidate metrics, and JSON configuration schema.

## 1. Add a strategy module

Create a module such as:

```text
src/rangebot/strategies/adaptive_trend.py
```

The module must expose one public constant named `STRATEGY_TYPE` containing a
validated `StrategyTypeMetadata` instance or a dictionary accepted by that
model.

```python
from rangebot.domain.strategy import StrategyTypeMetadata

STRATEGY_TYPE = StrategyTypeMetadata(
    type_id="adaptive_trend",
    display_name_ar="اتباع الاتجاه المتكيف",
    display_name_en="Adaptive Trend Following",
    description_ar="...",
    description_en="...",
    version="1",
    supports_long=True,
    supports_short=True,
    supports_monitoring=True,
    supported_timeframes=(5, 15, 30, 60, 240, 1440),
    required_market_data_feeds=(
        "candlesticks",
        "last_price",
        "mark_price",
        "best_bid_ask",
        "volume",
    ),
    implementation_status="working",
    supports_scanning=True,
    supports_backtesting=True,
    minimum_backtest_candles=300,
    configuration_schema=TrendConfig.model_json_schema(),
    candidate_metrics=(...),
    summary_metrics=(...),
    live_analysis_fields=(...),
    recommended_widgets=(...),
    chart_overlays=(...),
    status_badges=(...),
    important_warnings_ar=(...),
)
```

Private modules whose filename starts with `_` are ignored. Duplicate
`type_id` values fail startup instead of silently replacing another strategy.

## 2. Keep metadata frontend-neutral

The metadata must describe data rather than import or name React/PySide
components. Use stable keys for:

- configuration fields;
- supported timeframes and required normalized market-data feeds;
- Long/Short/Monitoring capabilities and implementation status;
- Discovery Lab capability and minimum historical sample;
- candidate metrics shown by the scanner;
- summary metrics and live-analysis values;
- recommended generic widgets;
- chart overlay and status badge identifiers;
- important Arabic warnings.

The frontend may format these values, but the engine and strategy remain the
source of truth.

## 3. Implement the deterministic evaluator

Expose `EVALUATOR_FACTORY`. The evaluator implements the common
`StrategyEvaluator` contract, accepts `StrategyEvaluationContext`, and returns
`StrategyEvaluationResult`. The same evaluator is shared by Live, Testnet,
Paper, Monitoring, scanning, and deterministic backtesting.

The evaluator must:

- use only normalized values and timestamps passed in the context;
- avoid system-clock and network calls;
- use completed candles for signals that require closed-candle behavior;
- return an unsized `StrategyTradeRequest` rather than submitting an order;
- give stable reason codes and an Arabic explanation for every decision.

```python
EVALUATOR_FACTORY = AdaptiveTrendEvaluator
```

A strategy must never call Gate.io directly or place critical logic only in the
browser. Registration metadata and evaluators never authorize exchange
activity. Live requests still pass through the Strategy Manager, Market Data
Manager, Order Manager, risk limits, Emergency Stop, reconciliation, and
position protection.

## 4. Add optional Discovery Lab support

When the strategy can scan the market, set `supports_scanning=True`, define
`candidate_metrics`, and expose `SCANNER_FACTORY`.

```python
class AdaptiveTrendScanner:
    type_id = "adaptive_trend"

    def scan_candidate(
        self,
        context: StrategyEvaluationContext,
        configuration: dict[str, object],
        *,
        minimum_backtest_candles: int,
    ) -> StrategyScanCandidate:
        ...

SCANNER_FACTORY = AdaptiveTrendScanner
```

The scanner owns the suitability score and explanation. React must never
hard-code what makes a good Range, Trend, or Breakout contract. Each candidate
must expose:

- an explainable score from 0 to 100;
- the preferred direction, if any;
- current eligibility and decision reason codes;
- metrics declared by `candidate_metrics`;
- completed-candle count and backtest readiness;
- stale, missing-feed, liquidity, and historical-data warnings.

The scanner is research-only. It has no Order Manager, account credentials, or
exchange submission interface. Gate public contracts and completed historical
candles are loaded by the central historical-market provider.

## 5. Backtesting behavior

When `supports_backtesting=True`, the shared `BacktestEngine` replays the same
registered evaluator over completed Gate.io historical candles. It:

- executes a new signal at the next candle open to avoid look-ahead bias;
- resolves a same-candle target/stop ambiguity conservatively in favor of the
  stop;
- supports Long and Short positions;
- applies configured fees and adverse slippage;
- includes historical funding where Gate data is available;
- records trades, equity points, drawdown, costs, and the strategy version;
- gives an explainable `promising`, `mixed`, `weak`, or `insufficient_data`
  assessment.

Do not create a separate strategy implementation for backtesting. Configuration
and evaluator behavior must remain identical to the registered strategy type.
Set `minimum_backtest_candles` to a meaningful warm-up and sample requirement.

The Discovery Lab can create a saved strategy from a stored result, but the new
instance is always `stopped`. It never starts Monitoring or Live trading
automatically.

## 6. Add tests

At minimum add tests proving:

1. the module is discovered without changing registry code;
2. metadata and JSON schema pass validation;
3. the public API entry appears through `/v1/strategy-types`;
4. decision logic is deterministic and uses closed candles where required;
5. stale data, risk limits, Emergency Stop, and reconciliation block entries;
6. scanner ranking is deterministic and candidate metrics match metadata keys;
7. backtests enter on the next candle and include fees, slippage, and funding;
8. a stored result survives restart and creates only a stopped strategy;
9. the research path cannot call the Order Manager or Gate order endpoints;
10. no test uses real Live credentials.

Run:

```text
uv run pytest -q
```

Record the exact result in `docs/IMPLEMENTATION_CHECKLIST.md` before marking the
strategy or Discovery Lab support verified.
