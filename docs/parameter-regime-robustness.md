# Parameter and Regime Robustness

Milestone 14 evaluates evidence around a parameter set selected and locked by a
prior out-of-sample workflow. Robustness cannot choose a replacement lock,
optimize parameters, promote a strategy, or make it production-ready.

## Locked-source validation

The reusable loader accepts schema-versioned OOS or walk-forward artifacts only
after validating artifact identity, experiment and strategy identity/version,
source dates, data provenance, execution assumptions, successful selection and
test status, finite required metrics, and a normalized parameter lock created
before robustness evaluation. In-sample winners and failed selections are
rejected. Missing or rejected candidate artifacts produce an evidence-based
`insufficient_evidence` result when no valid lock remains.

The current legacy RSI artifacts do not satisfy this contract: the OOS artifact
predates the strict schema and the walk-forward run has no successful fold or
lock. The RSI command therefore reports insufficient evidence after inspecting
both files; it does not substitute the best in-sample row.

## Bounded parameter neighborhoods

Each varied parameter uses exactly one declared method:

- `explicit_values`: a bounded list of strategy-compatible values;
- `integer_offsets`: integer steps added to a locked integer value;
- `percentage_offsets`: finite relative offsets applied to a continuous float.

Every method must explicitly include the locked value. Strategy metadata checks
types, allowed values, and bounds; the registered strategy validates complete
cross-parameter combinations. Nothing is clamped or coerced. Deterministic
candidate records preserve parameter name, locked value, method, source value,
raw value, normalized value, acceptance/rejection, rejection reason, and
normalization-created duplicates. Construction never reads performance data.

## Neighbor evaluation and degradation

Accepted points run as one experiment batch through the existing hygiene,
execution, portfolio, metric, and screening infrastructure. Every point uses
the identical audited data slice, boundaries, initial cash, fees, slippage,
timing, sizing, direction, leverage, and metric definitions. Rejected points
are never simulated. The locked point is always evaluated and remains locked.

Two degradation measures are recorded:

- absolute: `locked_total_return - candidate_total_return`, in decimal return
  units; `0.25` means 25 percentage points;
- relative: the absolute difference divided by `abs(locked_total_return)`.

Relative degradation is unavailable, with a warning, when locked return is
effectively zero. Policy can apply absolute, relative, or both limits. Negative
degradation means a neighbor outperformed, but cannot replace the lock.

The neighborhood summary records requested/raw/unique/rejected/duplicate/valid
and evaluated counts, pass counts and proportions, degradation compliance,
median/worst return and drawdown, median defined Sharpe, informational locked
rank, locked status, and explicit threshold results. Dimension summaries hold
other parameters at their locked values and describe tested values, pass count,
return and drawdown ranges, and monotonic versus unstable behavior.

Provisional defaults require at least three valid points, 60% passing, 60%
within degradation limits, worst drawdown no greater than 35%, and a passing
locked point. Thresholds remain research policy, not live risk limits.

## Past-only regimes

Trend compares each close with a trailing moving average. Values within the
configured relative tolerance are neutral; values above/below are bullish or
bearish. Volatility is the trailing sample standard deviation of period returns
multiplied by the square root of an explicit annualization factor, compared
with a fixed threshold. Both rolling windows use `center=False`; there is no
future observation or full-sample quantile.

Observations without both indicators are labeled `unknown|unknown`, and warm-up
count plus first usable timestamp are reported. Changing a future price cannot
change an earlier label.

## Attribution and evidence minima

Locked-strategy returns, prices, execution-aligned entries, and labels must have
identical unique increasing indexes and remain inside the locked source dates.
A period return at timestamp `t` is attributed to the regime known at `t-1`.
Execution-aligned trades are counted under their entry-timestamp regime.
Positions are not forcibly closed or re-simulated at regime boundaries.

Each regime records components, dates, observations, trades when available,
compounded return, path drawdown, defined Sharpe, win rate, thresholds, reasons,
and warnings. A regime below the minimum observation or trade count is
`insufficient_evidence`, never a pass or failure inferred from a tiny sample.

## Status and reporting

Combined precedence is deterministic:

1. invalid required input → `invalid_input`;
2. otherwise any required failure → `failed`;
3. otherwise any missing required evidence → `insufficient_evidence`;
4. otherwise → `passed`.

A failure cannot be overwritten by a later insufficient component. Reports use
schema version 1, validate required keys and statuses recursively, reject
non-finite or unsupported values, write with `allow_nan=False`, and support
strict read-back. Generated reports remain ignored by Git.

Run:

```bash
.venv/bin/python backtesting/run_rsi_robustness.py
```

## Limitations

This first version uses broad fixed-rule regimes and observation-level return
attribution. It does not discover regimes, correct multiple testing, reconstruct
trade P&L by regime, or prove causality. Passing only permits later lineage and
promotion research; it cannot replace the locked parameters or approve trading.
