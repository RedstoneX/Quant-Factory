# SPY daily Donchian trend breakout

## Status and hypothesis

This is the approved next candidate for Milestone 16 candidate discovery and screening.

The hypothesis is that sustained directional moves in SPY may be captured by entering after a completed daily close breaks a prior Donchian channel and exiting after a completed close breaks the opposite side of a shorter exit channel. This is structurally different from both RSI mean reversion and the MES cash-session opening-range breakout.

This is an exploratory screening candidate, not production evidence.

## Instrument and data

- Instrument: SPY.
- Provider: Yahoo Finance through the existing reusable market-data layer.
- Frequency: daily.
- Default start date: 2016-01-01.
- End date: latest completed exchange session available from the provider.
- Adjusted OHLC data: use the same adjusted-price policy already approved for daily SPY research.
- Exchange calendar: existing SPY/NYSE calendar policy.

## Exact signal rules

All channels exclude the current bar to prevent look-ahead.

### Long-only variant

- Entry signal: completed close is strictly above the highest high of the previous `entry_lookback` completed sessions.
- Exit signal: completed close is strictly below the lowest low of the previous `exit_lookback` completed sessions.
- Fill: next available session open through the common `next_bar_open` execution model.
- No accumulation; at most one open long position.

### Short-only variant

- Entry signal: completed close is strictly below the lowest low of the previous `entry_lookback` completed sessions.
- Exit signal: completed close is strictly above the highest high of the previous `exit_lookback` completed sessions.
- Fill: next available session open through the common `next_bar_open` execution model.
- No accumulation; at most one open short position.

Long-only and short-only remain separate registered strategy identities so direction is not silently optimized inside one portfolio.

## Approved parameter plan

Reference configurations are classic bounded Donchian trend-following structures:

- `entry_lookback=20`, `exit_lookback=10`;
- `entry_lookback=55`, `exit_lookback=20`.

Approved coarse screening combinations:

- entry lookback: 20 or 55 sessions;
- exit lookback: 10 or 20 sessions;
- constraint: `exit_lookback < entry_lookback`;
- direction: long-only or short-only as separate structural variants.

The valid deterministic matrix is:

1. 20/10 long-only;
2. 20/10 short-only;
3. 55/10 long-only;
4. 55/10 short-only;
5. 55/20 long-only;
6. 55/20 short-only.

Exactly six variants are approved. No other lookbacks, buffers, ATR filters, stops, targets, volatility filters, moving averages, pyramiding, leverage, or local refinement are approved in this task.

## Execution and costs

Use the existing approved daily equity assumptions:

- completed-bar close signal;
- next-session adjusted open fill;
- $10,000 initial cash;
- all-available-cash sizing;
- 0.05% fee per transaction;
- 0.02% slippage;
- 1x leverage;
- accumulation disabled.

Short financing, borrow availability, hard-to-borrow fees, taxes, and opening-auction uncertainty are not modeled. The short-only variant therefore remains exploratory and must carry an explicit limitation.

## Screening and progression

Run all six variants through the existing hygiene gates and provisional cheap-screening policy.

- Preserve every simulated and rejected row.
- Do not proceed to out-of-sample, walk-forward, robustness, Monte Carlo, or dashboard expansion unless at least one variant passes the baseline cheap screen.
- A pass is only permission for the next validation stage, not evidence of profitability or promotion readiness.
- If no variant passes, record a clear rejection and stop.

## Required implementation boundaries

- Add reusable Donchian signal logic rather than embedding it only in a runner.
- Preserve existing RSI and MES ORB behavior.
- Add deterministic tests for channel shifting, entry and exit timing, long and short symmetry, parameter validation, warm-up behavior, and six-row experiment output.
- Generated results remain Git-ignored.

## Baseline cheap-screen result — 2026-07-09

The approved six variants were implemented and run through the existing hygiene
gates, VectorBT Pro portfolio path, and provisional cheap-screening policy using
Yahoo Finance adjusted daily SPY data from 2016-01-04 through 2026-07-08.

Generated result rows are preserved outside Git at:

```text
results/spy_donchian_baseline.csv
```

| Direction | Entry lookback | Exit lookback | Total return | Annualized return | Sharpe | Max drawdown | Trades | Win rate | Screening |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Long-only | 20 | 10 | 1.538576 | 0.137353 | 1.181894 | -0.091294 | 48 | 0.583333 | Passed |
| Long-only | 55 | 20 | 0.576182 | 0.064878 | 0.636339 | -0.247073 | 26 | 0.653846 | Passed |
| Long-only | 55 | 10 | 0.468497 | 0.054518 | 0.612886 | -0.204777 | 41 | 0.536585 | Passed |
| Short-only | 55 | 20 | -0.147224 | -0.021762 | -0.104277 | -0.222205 | 11 | 0.272727 | Screened out |
| Short-only | 55 | 10 | -0.323041 | -0.052473 | -0.369462 | -0.345494 | 15 | 0.066667 | Screened out |
| Short-only | 20 | 10 | -0.521148 | -0.096727 | -0.653338 | -0.526002 | 34 | 0.117647 | Screened out |

Survivor set pending explicit user approval before any deeper validation:

- 20/10 long-only;
- 55/20 long-only;
- 55/10 long-only.

The short-only variants are rejected by the baseline cheap screen. The passing
long-only rows are not production evidence and do not authorize out-of-sample,
walk-forward, robustness, Monte Carlo, dashboard, paper, or live work until the
user explicitly approves the next stage.

## Chronological out-of-sample result — 2026-07-09

The three approved long-only baseline survivors were evaluated through the
existing chronological out-of-sample runner using the standard 60% training,
20% selection, and 20% held-out test split. No new parameters were introduced.

Generated OOS evidence is preserved outside Git at:

```text
results/spy_donchian_oos.json
```

Partition boundaries:

| Partition | Start | End | Rows |
|---|---:|---:|---:|
| Train | 2016-01-04 | 2022-04-19 | 1,585 |
| Selection | 2022-04-20 | 2024-05-24 | 528 |
| Test | 2024-05-28 | 2026-07-09 | 530 |

Training results:

| Entry lookback | Exit lookback | Total return | Annualized return | Sharpe | Max drawdown | Trades | Win rate | Screening |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | 10 | 0.700539 | 0.130057 | 1.149534 | -0.075498 | 29 | 0.551724 | Passed |
| 55 | 10 | 0.307246 | 0.063641 | 0.709271 | -0.098608 | 25 | 0.560000 | Passed |
| 55 | 20 | 0.367878 | 0.074805 | 0.731484 | -0.118312 | 15 | 0.733333 | Screened out |

Training shortlist:

- 20/10 long-only;
- 55/10 long-only.

Selection results:

| Entry lookback | Exit lookback | Total return | Annualized return | Sharpe | Max drawdown | Trades | Win rate | Screening |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 20 | 10 | 0.276538 | 0.183858 | 1.395839 | -0.091294 | 8 | 0.875000 | Screened out |
| 55 | 10 | 0.025892 | 0.017828 | 0.238193 | -0.171450 | 7 | 0.428571 | Screened out |

Selection produced no passing candidate, so no parameter lock was created and
the held-out test partition was not evaluated. The OOS artifact is intentionally
not accepted by the robustness lock loader because it contains no valid lock and
no held-out test metrics. This fail-closed result blocks walk-forward,
robustness, Monte Carlo, dashboard, paper, and live work for this Donchian
candidate unless a new explicitly approved research decision changes scope.

## Evidence classification after policy review — 2026-07-09

The general policy in `docs/low-frequency-oos-evidence-policy.md` was adopted
after the selection results above had already been inspected. It therefore does
not retroactively convert the 20/10 selection row into a valid pass.

The 20/10 long-only result is classified as:

```text
promising_but_insufficient_oos_selection_evidence
```

This is a descriptive research classification, not a parameter lock or promotion.
The 2022-04-20 through 2024-05-24 selection interval is now contaminated for
policy design and cannot be reused as fresh selection evidence under a changed
trade-count floor. The 2024-05-28 through 2026-07-09 held-out test interval
remains untouched and blocked.

Any revisit requires a separate prospective research design using new later data
or a predeclared walk-forward evidence-accumulation plan. The original OOS
artifact and rejection outcome remain unchanged.

## Low-frequency walk-forward evidence result — 2026-07-09

The project owner approved one bounded low-frequency evidence workflow for the
20/10 long-only candidate only. This was evidence accumulation, not parameter
selection. The prior OOS selection interval from 2022-04-20 through 2024-05-24
was not treated as fresh selection evidence, and the held-out OOS test interval
from 2024-05-28 through 2026-07-09 remained excluded.

Generated evidence is preserved outside Git at:

```text
results/spy_donchian_low_frequency_walk_forward.json
```

The bounded run used adjusted daily Yahoo Finance SPY cache rows from
2016-01-04 through 2024-05-24 and evaluated five expanding chronological
validation folds:

| Fold | Train start | Train end | Validation start | Validation end | Trades | Total return | Annualized return | Sharpe | Max drawdown | Evidence | Performance | Combined |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| fold_001 | 2016-01-04 | 2019-01-03 | 2019-01-04 | 2020-01-03 | 5 | 0.077899 | 0.114774 | 1.386410 | -0.046397 | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| fold_002 | 2016-01-04 | 2020-01-03 | 2020-01-06 | 2021-01-04 | 4 | 0.220593 | 0.334721 | 1.618335 | -0.075498 | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| fold_003 | 2016-01-04 | 2021-01-04 | 2021-01-05 | 2022-01-03 | 7 | 0.050563 | 0.074059 | 0.742916 | -0.057554 | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| fold_004 | 2016-01-04 | 2022-01-03 | 2022-01-04 | 2023-01-04 | 3 | 0.021480 | 0.031262 | 0.283107 | -0.091294 | insufficient_evidence | insufficient_evidence | insufficient_evidence |
| fold_005 | 2016-01-04 | 2023-01-04 | 2023-01-05 | 2024-01-05 | 3 | 0.145862 | 0.218002 | 2.341977 | -0.043860 | insufficient_evidence | insufficient_evidence | insufficient_evidence |

Aggregate result:

- sufficient-evidence folds: 0;
- passing sufficient-evidence folds: 0;
- passing percentage: 0.0%;
- worst fold drawdown: -0.091294;
- aggregate status: `insufficient_evidence`;
- reason: the policy requires at least three sufficient-evidence folds and
  observed zero.

This result does not create a parameter lock, does not authorize the protected
held-out OOS test interval, and does not advance the candidate to robustness,
Monte Carlo, dashboard, paper, or live work.
