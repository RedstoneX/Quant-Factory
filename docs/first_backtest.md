# First backtest: SPY RSI mean reversion

This milestone proves the Quant Factory path from market data to a reproducible
ranked result. It uses `vectorbtpro.YFData.pull` to download SPY daily OHLCV
from Yahoo Finance. The request begins `2016-01-01`; the actual first market row
in the verified run was `2016-01-04`.

The end date is dynamic. `pandas_market_calendars` supplies the NYSE schedule,
including weekends, exchange holidays, and scheduled early closes. A session is
eligible only after its scheduled close in `America/New_York`, and the final
usable date is the latest eligible session for which Yahoo returned complete
OHLCV. Incomplete current-session bars and future rows are removed. If Yahoo
lags the exchange calendar, the previous complete provider row is retained and
the lag is reported rather than filled.

Prices are adjusted by explicitly passing `auto_adjust=True` through VectorBT
Pro to `yfinance.history`; `actions=False` limits the cached columns to adjusted
Open, High, Low, Close, and Volume. No synthetic or forward-filled rows are
used.

The reusable [`market_data`](../market_data/) package now owns Yahoo access,
NYSE completed-session calculation, validation, cache compatibility, and audit
metadata. The RSI runner defines its `MarketDataConfig`, calls
`load_market_data(config)`, and consumes `result.data` and `result.audit`; it no
longer contains provider or cache implementation details.

## Verified dataset

The corrective live run on 2026-07-02 produced:

- Provider: Yahoo Finance
- Provider implementation: `vectorbtpro.YFData.pull`
- Interval: one day
- Requested start: 2016-01-01
- Actual range: 2016-01-04 through 2026-07-02
- Rows: 2,639
- Duplicate timestamps: 0
- Missing Open/High/Low/Close/Volume values: 0/0/0/0/0
- Unexpected NYSE session gaps: 0
- Provider warnings: none
- Cache action: replaced the incompatible legacy 2018–2025 cache

The final date is an observed result, not a hardcoded project setting. Later
runs recompute the latest completed NYSE session and may extend the dataset.

## Cache policy

The dataset and its human-readable audit sidecar are stored at:

```text
data/cache/spy_2016_dynamic_adjusted.csv
data/cache/spy_2016_dynamic_adjusted.metadata.json
```

Before reuse, the loader validates the cache schema, symbol, provider,
implementation, interval, requested start, adjustment setting, required
columns, duplicates, missing values, expected NYSE sessions, and coverage
through the latest completed session. A compatible current cache is reused. A
stale or incompatible cache is downloaded again and atomically replaced; no
unrelated cache is deleted. The old 2018–2025 filename is never treated as the
active dataset. Both `data/cache/` and generated result CSV files are ignored by
Git.

## Strategy and grid

The strategy is long-only. It enters when RSI crosses below the entry threshold
and exits when RSI crosses above the exit threshold. The complete grid contains
27 combinations:

- RSI windows: 7, 14, and 21
- Entry thresholds: 20, 25, and 30
- Exit thresholds: 50, 55, and 60

Every exit threshold is greater than its paired entry threshold. Each portfolio
starts with $10,000 and applies 0.05% fees plus 0.02% slippage per transaction.

The stable strategy ID is `rsi_mean_reversion`. The public registry entry
implements the common `spec`, `validate_parameters(parameters)`, and
`generate_signals(data, parameters)` interface. Its typed specification records
strategy identity and family, required adjusted daily Close data, parameter
definitions, and the execution assumptions below. The original convenience
functions remain available and use the same implementation.

The current default calculates RSI crossings from a completed daily close,
shifts the signal to the next available session, and executes at that session's
adjusted open with slippage applied by VectorBT Pro. The original same-bar-close
model remains available only for explicit comparison. Portfolios are long-only,
use 1× leverage (no borrowing), and set `accumulate=False`, so entry signals
observed while already long do not add to the position.

## Results

The original same-bar-close verified top five combinations were:

| Window | Entry | Exit | Return | Annualized | Sharpe | Max drawdown | Trades | Win rate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7 | 25 | 60 | 99.45% | 10.02% | 0.701 | -30.49% | 35 | 91.43% |
| 7 | 30 | 60 | 96.87% | 9.82% | 0.658 | -30.49% | 49 | 85.71% |
| 7 | 30 | 50 | 64.98% | 7.17% | 0.555 | -31.12% | 56 | 83.93% |
| 7 | 25 | 55 | 54.86% | 6.24% | 0.495 | -30.49% | 35 | 85.71% |
| 7 | 25 | 50 | 54.42% | 6.19% | 0.519 | -30.80% | 36 | 80.56% |

Results are ranked by total return, then Sharpe ratio. The complete table also
contains annualized return, maximum drawdown, trade count, win rate, and dataset
provenance fields.

## Run it

From the repository root, the exact command is:

```bash
$QF_REPO_ROOT/.venv/bin/python backtesting/run_rsi_demo.py
```

The command prints the dataset-quality report and top 10 combinations, then
writes the full ranking to `results/rsi_spy_demo.csv`.

This is an in-sample research demonstration, not investment advice. Yahoo data
can be revised upstream. Same-bar close execution, in-sample ranking, absence
of taxes, and absence of explicit liquidity constraints limit real-world use.
