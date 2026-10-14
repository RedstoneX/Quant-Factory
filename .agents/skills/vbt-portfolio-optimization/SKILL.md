---
name: vbt-portfolio-optimization
description: "Build and backtest asset weights with VectorBT PRO PortfolioOptimizer. Use when implementing allocation functions, integrating optimizers, scheduling rebalances, simulating target weights, allocating ranked assets, or weighting strategy portfolios. Use vbt-optimization for strategy parameter searches and vbt-callbacks for state-dependent rebalancing."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Portfolio optimization with VBT

`vbt.PFO`, short for `PortfolioOptimizer`, turns data into allocation vectors at chosen dates.
Simulating those allocations is a separate step, so weights can be inspected before any backtest.

Read `vbt-basics` once for API discovery and shared conventions. Choose the allocation method,
define its observation and execution dates, then inspect the weights before simulating. Use the
final section for multiple optimizer groups or retained state.

## 1. Choose how weights are produced

| Weights come from | Constructor |
| --- | --- |
| A fixed vector, or a DataFrame of weights on the rebalancing dates | `vbt.PFO.from_allocations` |
| A vector bought on the first bar and left to drift | `vbt.PFO.from_initial` |
| A DataFrame of weights on every bar, with NaN rows where nothing changes | `vbt.PFO.from_filled_allocations` |
| Equal or random weights | `vbt.PFO.from_uniform`, `vbt.PFO.from_random` |
| A function called at each rebalancing date | `vbt.PFO.from_allocate_func` |
| A function over a window of past data, such as the last 90 days | `vbt.PFO.from_optimize_func` |
| PyPortfolioOpt, such as minimum volatility or maximum Sharpe | `vbt.PFO.from_pypfopt` |
| Riskfolio-Lib | `vbt.PFO.from_riskfolio` |
| Online portfolio selection algorithms | `vbt.PFO.from_universal_algo` |

* The first argument of the function-based constructors is a wrapper with symbols as columns, such
  as `data.symbol_wrapper`. Pass the arguments of the function after it.
* The function returns one weight vector per call: an array in column order, or a Series or dict
  keyed by symbol. It cannot return weights for many dates at once. Pass such a DataFrame to
  `from_allocations` instead.
* Templates pass the current step to the function. `from_allocate_func` provides
  `vbt.Rep("index_point")`, the row of the allocation date. `from_optimize_func` provides
  `vbt.Rep("index_slice")` and the bounds `index_start` and `index_end`, which is exclusive. Both
  provide `i`, the step number.
* An optimization function receives only its window when an array is wrapped in `vbt.Takeable`, such
  as `vbt.Takeable(data.close)` or `vbt.Takeable(data)`.
* Compute indicators and rankings once on the full data and pass them in only if every row uses
  information available by that row. Computed inside each window, rolling indicators restart their
  warm-up with NaN. With `vbt.Takeable`, the last row of the window is the latest value.
* Pass `jitted_loop=True` with a Numba optimization function to run thousands of windows in a
  compiled loop.
* `from_universal_algo` runs its algorithm once over the whole history in plain Python and returns
  weights for every bar, which rebalance whenever they change unless dates are passed with `on`. It
  is slow on long histories.
* `from_pypfopt` takes `prices=` or `returns=`, and `from_riskfolio` takes `returns=`, plus the
  options of each library, such as `target="min_volatility"`. Both libraries are optional
  dependencies, and both optimize over every column of the window. To select assets first, drop
  columns with missing data, or cap and round the weights, write a function that calls
  `vbt.pypfopt_optimize` or `vbt.riskfolio_optimize` on the window and pass it to
  `from_optimize_func`.

## 2. Choose the schedule, lookback, and timing

* `every` sets the rebalancing dates, such as `every="MS"` for each month start, `every="W"` for
  weekly, or an integer for every N rows. Without it, `from_allocate_func`, `from_uniform`,
  `from_random`, and `from_allocations` with a single vector rebalance on every bar. Use
  `from_initial` to buy once. `from_optimize_func`, `from_pypfopt`, and `from_riskfolio` optimize
  once over all data and return no allocation, because no bar follows the window.
* For custom dates, pass them as `on=` to `from_allocate_func`, which moves each date to the next
  available bar. Pass a list or `pd.Index`, not a `vbt.Param`, which makes one group per date. For
  `from_optimize_func`, pass lists of window bounds as `start=` and `end=`, or pass `index_ranges`.
* `lookback_period`, such as `"90D"`, sets the window of `from_optimize_func` and the integrations.
  Without it, each window covers only the period since the previous rebalancing date. For an
  expanding window, pass `start=0, exact_start=True, fixed_start=True` along with `every`.
* An optimization window ends before its allocation date: the allocation is placed on the bar after
  the window. The simulation fills orders at the close of that bar by default, a bar later than
  needed. Pass `price="open"` to fill at its open, the first price after the window.
  `price="nextopen"` delays the fill by another bar.
* `alloc_wait=0` places the allocation on the last bar of the window, so orders fill at the close
  the function has just read. This assumes execution at the observed close. Use an explicit
  close-execution model for that assumption, or fill at a subsequent price.
* `from_allocate_func` has no window. A precomputed array read at `index_point` includes the close
  of the allocation bar, so fill at that close at the earliest, or read the previous row and fill at
  the open.
* The first allocation comes only after the first full lookback period, so the portfolio holds cash
  until then. Groups with different lookbacks start on different dates. Compare them from the latest
  first allocation date, for example with `pf.loc[start:]`.
* For live trading, the schedule creates a window only once the data reaches the next rebalancing
  date, so the weights to trade at that date are missing while the data ends on the bar before. Call
  the function on the latest window directly, or pass `index_ranges=(starts, ends)` whose last end
  is the number of rows, together with `alloc_wait=0`, to retrieve its weights. Execute only after
  the information is available. Without `alloc_wait=0`, that window is marked Open and excluded from
  the default allocation output.

## 3. Inspect the allocations

* In the default target-weight simulation, a NaN weight leaves that asset unchanged, and 0 requests
  its closure. A dict or Series that omits a symbol gives it NaN. For a rotation into the top N
  assets, return 0 for all other assets.
* `from_filled_allocations` skips all-zero rows and rows that repeat the previous row by default.
  Pass `nonzero_only=False` when an all-zero row should close every position, and
  `unique_only=False` when a repeated row should rebalance the drifted weights back.
* Empty or all-NaN allocations produce no rebalance. Existing positions remain subject to the
  simulation's other rules. Solver failures can instead raise, depending on the integration. The
  PyPortfolioOpt and Riskfolio wrappers accept `ignore_errors=True` to return empty weights on
  exceptions. Inspect skipped dates so failures are not mistaken for deliberate decisions to hold.
* `rescale_to=(0, 1)` normalizes positive weights to sum to 1 and rejects negative weights.
  `(-1, 1)` normalizes present long and short sides separately to 1 and -1. Zeros and NaNs remain
  unchanged, and an absent side is not created.

* `pfo.allocations` lists the weights by allocation date. `pfo.alloc_records.records_readable` shows
  each window's start, end, and allocation date, and `pfo.plot()` draws them. `pfo.stats()` shows
  the mean weight per asset and how much of the data the windows cover.
* Check finiteness, symbol order, net exposure (sum of weights), and gross exposure (sum of their
  absolute values). Long-only targets summing to less than 1 normally leave cash. For long/short
  targets, net exposure alone does not describe cash or collateral requirements. Investigate missing
  allocation dates, which can indicate windows that returned no weights.
* Select one group of a grid with `pfo[key]`, or pass `column=key` to `pfo.plot`.
* Edit weights before simulating with `pfo.replace(allocations=...)`, such as the average of two
  models on matching dates, and combine optimizers built on different columns with
  `vbt.PFO.column_stack`.

## 4. Simulate and compare with a baseline

`pfo.simulate(data)` and `vbt.PF.from_optimizer(data, pfo)` rebalance to the target weights with
`vbt.PF.from_orders` by default, with cash shared within each optimizer group and automatic order
sequencing based on estimated order values. Inspect the sequence when targets compete for cash.

* Pass simulation arguments such as `fees`, `slippage`, `price`, and `init_cash` to `simulate`. Pass
  `min_size` to skip small rebalancing orders. `freq` is the frequency of the data, not of the
  rebalancing.
* Direction is inferred from the signs of the weights. Shorts lock collateral, so targets must fit
  available cash, collateral, and fees. For leveraged targets, configure `leverage` and consider
  `leverage_mode="eager"` so borrowing is available for target sizing. Default lazy borrowing can
  leave targets underfilled. Verify orders and achieved exposure.
* For stops, pass `pf_method="from_signals"` with `sl_stop`, `tp_stop`, or `tsl_stop`. A stopped
  asset stays in cash until the next allocation date buys it back. Read `vbt-backtesting` for stop
  arguments.
* Rebalancing when weights drift past a threshold, or any decision that depends on cash or current
  positions, needs `vbt.PF.from_order_func`, as described in `vbt-callbacks`.
* Compare with an equal-weight or buy-and-hold baseline over the same period. Start the baseline on
  the first allocation date of the strategy, or the strategy's months in cash distort the result.
* Check simulated weights with `pf.allocations` on allocation dates. Weights at the close can drift
  from targets filled at the open. Fees, slippage, partial or rejected orders, size limits, missing
  prices, and borrowing constraints can also create differences.
* Analyze the result as described in `vbt-analysis`. Validate the choice of lookback and schedule
  out of sample as described in `vbt-cross-validation`.

This program allocates by inverse volatility over the last 90 days each month, fills at the open of
the allocation bar, and compares it with equal weights over the same period:

```python
import numpy as np
import vectorbtpro as vbt


def inverse_volatility(close):
    volatility = close.pct_change(fill_method=None).std()
    if not np.isfinite(volatility).all() or (volatility <= 0).any():
        raise ValueError("Each asset needs finite positive volatility")
    weights = 1 / volatility
    return weights / weights.sum()


data = vbt.GBMOHLCData.pull(
    ["A", "B", "C", "D"],
    start="2020-01-01",
    periods=730,
    timeframe="1D",
    seed=42,
)

inv_vol_pfo = vbt.PFO.from_optimize_func(
    data.symbol_wrapper,
    inverse_volatility,
    vbt.Takeable(data.close),
    every="MS",
    lookback_period="90D",
)
start = inv_vol_pfo.allocations.index[0]
equal_pfo = vbt.PFO.from_uniform(data.symbol_wrapper, every="MS", start=start)

print(inv_vol_pfo.alloc_records.records_readable.head(3))
print(inv_vol_pfo.allocations.head(3))
print(equal_pfo.allocations.index[0])
assert equal_pfo.allocations.index[0] == start
assert np.isfinite(inv_vol_pfo.allocations.to_numpy()).all()
np.testing.assert_allclose(inv_vol_pfo.allocations.sum(axis=1), 1.0)
records = inv_vol_pfo.alloc_records.values
np.testing.assert_array_equal(records["alloc_idx"], records["end_idx"])

for name, pfo in [("inverse volatility", inv_vol_pfo), ("equal weight", equal_pfo)]:
    pf = pfo.simulate(data, price="open", fees=0.001).loc[start:]
    print(name)
    print(pf.stats(["total_return", "sharpe_ratio", "max_dd", "total_orders"]))
```

## 5. Report

Report the weighting method, the schedule and lookback, the fill price, the first allocation date,
the costs, and the metrics of the strategy next to the baseline over the same period, including the
number of orders.

## Multiple groups and allocation state

* Wrap any argument in `vbt.Param` to build one group of assets per value, and compare the groups in
  one simulation. Use `group_configs` for groups that differ in several arguments or in the function
  itself. A `vbt.Param` nested in a list is found only with
  `param_search_kwargs=dict(incl_types=list)`.
* Stateless allocation calls can run in parallel with
  `execute_kwargs=dict(engine="pathos", distribute="chunks", n_chunks="auto")`. To use the previous
  weights, pass a list that the function appends to, and run serially. That list is shared by all
  groups of a `vbt.Param`, so reset state per group, such as when `i` is 0. Stored targets differ
  from simulated weights after price drift, fees, or rejected orders. Use simulation callbacks when
  decisions depend on that state.

## Allocation patterns beyond PFO

These multi-asset patterns produce target weights or grouped simulations without a PFO:

* Cross-sectional ranking: compute scores in a table with one column per symbol, rank all dates at
  once with `scores.rank(axis=1)`, turn the selection into weights, and simulate them with
  `vbt.PF.from_orders(close, size=weights, size_type="targetpercent", group_by=True, cash_sharing=True, call_seq="auto")`.
  Rows without weights are NaN, so holdings drift between rebalancing dates. Apply eligibility, such
  as index membership or enough history, before ranking, and keep symbols that join or leave in the
  table with NaN outside their membership. Indicator expressions provide `cs_rank`, `cs_demean`, and
  `cs_rescale` for ranking and demeaning across symbols. A limit that depends on current holdings,
  such as at most five open positions from per-symbol signals, needs a callback, as described in
  `vbt-callbacks`.
* Quintiles of a factor: tile the prices once per quintile with a `quintile` column level and
  simulate with `group_by="quintile"` and `cash_sharing=True`, which gives one portfolio per
  quintile in one call. A rank information coefficient is
  `scores.corrwith(forward_returns, axis=1, method="spearman")`.
* Pairs: `vbt.OLS.run(x, y, window=...)` gives the rolling `slope`, `intercept`, `zscore`, and `r2`.
  Put both legs of each pair in one group with `cash_sharing=True` and `call_seq="auto"`, such as
  `size=0.5, size_type="valuepercent"` per leg for dollar-neutral legs, or a `size` array built from
  `slope` for hedge-ratio sizing. Long and short entries go to opposite legs. Select pairs on one
  period and trade them on a later one.
* Mixes of strategies: `vbt.PF.column_stack(pfs, wrapper_kwargs=dict(group_by=True))` holds finished
  strategies side by side without rebalancing, and `apply_weights(weights, rescale=True)` applies
  fixed weights to them. To rebalance between strategies, treat their `pf.value` series as prices of
  synthetic assets and run a PFO on them, which charges fees at the strategy level. To let
  strategies compete for the same cash while they trade, simulate them together in one cash-sharing
  group.

## Pitfalls

* Expected returns estimated from a short window are noisy, so maximum-Sharpe and mean-variance
  weights can swing between extremes. Compare constraints and alternative objectives out of sample.
  Inspect traded notional and fees as well as Total Orders. Order count alone does not measure
  turnover.
* Applying weights fitted on the whole dataset back to that same period leaks future data. Fit on
  earlier data and evaluate on later data, using a schedule and lookback when weights are updated.
* `i` counts rebalancing steps, not rows. Select rows of a precomputed array with `index_point`, or
  with `index_end - 1` for the last row of a window.
* A PFO instance with several groups from `vbt.Param` simulates one portfolio per group. Plotting it
  raises "Only one group is allowed" until a group is selected.
* Grids of many groups over many assets simulate large arrays. When memory runs short, simulate one
  group at a time with `pfo[key].simulate(data)` and keep only the metrics.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/tutorials/portfolio-optimization/models/`: allocation and optimization functions, index points
  and ranges, groups, Numba loops, and previous and current allocations
* `/tutorials/portfolio-optimization/integrations/`: PyPortfolioOpt, Riskfolio-Lib, and universal
  portfolios, including argument routing and constraints
* `/tutorials/portfolio-optimization/dynamic/`: threshold rebalancing with `vbt.PF.from_order_func`,
  custom optimizers, and simulating in chunks to reuse the portfolio state
* `/api/base/indexing/`: all arguments that select rebalancing dates and windows
