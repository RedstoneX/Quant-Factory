# Monte Carlo Stress Testing

Milestone 13 stress-tests a completed realized-return series. It does not
optimize parameters, create an edge, forecast returns, or approve a strategy.

The canonical input is an explicitly identified sequence of period, trade, or
fold-endpoint returns with strategy, experiment, provenance, and execution
assumptions. Fold endpoints are never labeled daily returns. Empty, short,
non-finite, or returns at or below -100% produce `insufficient_evidence` or
`invalid_input`; values are never repaired.

Supported seeded methods are IID bootstrap with replacement (destroys serial
dependence), permutation without replacement (same return set, reordered path),
and fixed moving-block bootstrap (local dependence partly preserved, blocks
sampled from valid starts and the final block truncated to source length).
Randomness uses a local NumPy `Generator`; global random state is untouched.
Permutation preserves the exact compounded terminal return (within floating
point tolerance); it measures sequencing and drawdown risk, not terminal-return
uncertainty.

Each path reports terminal compounded return, compounded-equity maximum
drawdown, volatility, and Sharpe when variance permits. Summaries include mean,
median, standard deviation, minimum, maximum, and configured percentiles.
Provisional defaults fail when probability of loss exceeds 25%, probability of
a 35% drawdown exceeds 10%, or the 5th-percentile terminal return is below
-10%. Status is `passed`, `failed`, `insufficient_evidence`, or `invalid_input`.

Adverse execution scenarios apply two-sided incremental fees and slippage plus
an execution-price penalty only to realized trade returns. Period or fold
returns without turnover metadata produce a typed scenario-level
`insufficient_evidence` result. Applied stress can never improve results.

Reports use schema version 1 and strict JSON: non-finite values are rejected,
required keys are validated, and read-back is supported. Undefined Sharpe is
omitted and explained; annualization requires an explicit positive finite
factor. Full paths are omitted unless `persist_paths` is enabled.

Run:

```bash
.venv/bin/python backtesting/run_rsi_monte_carlo.py
```

The current legacy RSI walk-forward artifact has zero successful folds. It can
establish only that no evidence exists, not full identity provenance, so the
honest result is `insufficient_evidence`; no returns are consumed or fabricated.
Artifacts with successful folds must establish schema, identity, execution
mode, finite metrics, and test boundaries. Reports are Git-ignored JSON.

VectorBT Pro 2026.4.7 installed API inspection confirmed portfolio returns,
returns accessors, resampling, drawdown, and statistics facilities. They remain
the upstream portfolio analytics source. Monte Carlo resampling uses a small
NumPy implementation because the required bootstrap/permutation/block semantics
and local RNG are clearer and directly testable. Private MCP hybrid search was
unavailable due to the recorded CUDA kernel incompatibility.

Monte Carlo explores path and sampling uncertainty conditional on observed
returns. It cannot repair overfitting, biased data, model error, execution model
error, or an insufficient strategy history.
