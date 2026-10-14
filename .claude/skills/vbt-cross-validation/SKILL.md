---
name: vbt-cross-validation
description: "Evaluate VectorBT PRO strategies out of sample with splitters, walk-forward analysis, train-only parameter selection, and robustness checks. Use when building train/test workflows, warming up split calculations, stitching test periods, or investigating overfitting."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Cross-validation with VBT

Read `vbt-basics` once for API discovery and shared conventions. Use the sections below that apply
to the requested task.

## Define the evaluation before choosing an API

Set these policies before running a grid:

* Choose the score and whether parameters are shared across symbols or selected per symbol.
* Decide which observations warm up indicators and which bars contribute to the score. A splitter
  cuts inputs. It does not automatically supply indicator history.
* Fit models, thresholds, and other learned transformations on training data only. Causal indicators
  can be precomputed on the history and sliced, but whole-sample normalization cannot.
* Decide what happens to an open position when selected parameters change. Independent flat-start
  tests and one continuous deployment answer different questions. Slicing an existing portfolio
  preserves its boundary state.
* Keep a final period unused by strategy and selection-rule changes.

Step 2 compares the three ways to apply a splitter, and step 3 shows each one. All of them need the
policies above.

## 1. Build the splitter and inspect it

A `vbt.Splitter` holds ranges of the index, one row per split and one column per set, such as train
and test.

| Scheme | Constructor |
| --- | --- |
| Walk-forward with fixed train and test lengths | `vbt.Splitter.from_rolling(index, length=..., split=..., offset=..., offset_anchor_set=None, backwards="sorted")` |
| A fixed number of windows | `vbt.Splitter.from_n_rolling(index, n=..., split=...)`. With `length="optimize"` and `optimize_anchor_set=1`, it finds the longest windows whose test sets do not overlap. |
| Expanding train set | `vbt.Splitter.from_expanding(index, min_length=..., offset=..., split=-test_length)` or `vbt.Splitter.from_n_expanding` |
| Calendar periods, such as three years of training and one of testing | `vbt.Splitter.from_ranges(index, every="Y", lookback_period="4Y", split=...)` |
| One split per group or period, such as each month or each market regime | `vbt.Splitter.from_grouper(index, by="M")` |
| Purged folds that avoid leakage between overlapping labels | `vbt.Splitter.from_purged_walkforward`, `vbt.Splitter.from_purged_kfold` |
| Random windows for bootstrapping | `vbt.Splitter.from_n_random(index, n=..., min_length=..., seed=...)` |
| Any scikit-learn splitter | `vbt.Splitter.from_sklearn`. To validate a model, `vbt.SplitterCV` works as a scikit-learn cross-validator. |
| Explicit or computed ranges | `vbt.Splitter.from_splits(index, [[train_slice, test_slice], ...])` or `vbt.Splitter.from_split_func` |

* `split` divides each window into sets: a fraction such as `0.7`, a number of rows, or a tuple of
  them. A negative number sizes the last set, so `split=-100` gives the test set 100 rows and the
  train set the rest. Pass `set_labels=["train", "test"]`.
* Lengths and offsets also accept durations, such as `"180 days"`.
* By default, `from_rolling` starts each window at the end of the previous first set. Depending on
  train/test lengths, test periods can have gaps or overlap. For walk-forward analysis, where test
  periods follow each other, pass `offset` as minus the test length with `offset_anchor_set=None`,
  and `backwards="sorted"` to keep the most recent data.
* Add a gap between train and test with `vbt.RelRange(length=10, is_gap=True)` inside `split`. For
  purged splitters, pass `pred_times` and `eval_times` describing each sample's information
  interval, plus any `purge_td` or `embargo_td` required by the experiment. Both time arrays default
  to the index, so the splitter cannot infer a forward-looking label horizon.
* Ranges are positions in the splitter's index, and taking remaps them to each object's own index by
  date. Build the splitter from a daily index and apply it to intraday data. The index of every
  object must have the same type and timezone as the splitter's index.
* Inspect every splitter before using it: `splitter.index_bounds` lists the dates of each range,
  `splitter.stats()` reports coverage and overlap, and `splitter.plot()` draws the ranges. The test
  sets of a walk-forward analysis must not overlap: `Overlap Coverage [%]: test` must be 0.

## 2. Choose how to apply the splitter

The three tools are layers of one mechanism. `vbt.Splitter` holds the ranges, cuts objects with
`take`, and runs a function per range with `apply`. `@vbt.split` builds the splitter from each
call's inputs and runs `apply`. `@vbt.cv_split` adds `@vbt.parameterized` and an automatic selection
between train and test.

| | `vbt.Splitter` directly | `@vbt.split` | `@vbt.cv_split` |
| --- | --- | --- | --- |
| Builds the splitter | You, once, from an index | The decorator, from each call's inputs | The decorator, as in `split` |
| Runs the grid | You, such as all combinations as columns of one simulation per range | `@vbt.parameterized` when stacked below it | Built in, one call per combination |
| Selects parameters | You | You, from the returned grid | Built in through `selection` |
| The function receives | The ranges you take or apply to | Arguments already cut to each range | Arguments cut to each range, one combination at a time |
| Warm-up | Precompute causal signals on the full history, then take | `index_from` with `vbt.Rep("range_")` | As in `split` |
| Result index | Whatever the merge returns | `split`, `set`, then any parameter levels | `split`, `set`, and the selected parameters, or the grid with `return_grid` |
| Best for | A large causal signal grid simulated once per range, stitched test periods, or a model fitted per split | Any function per range, or a full grid for your own selection rule | The standard loop of selecting on train and evaluating on test |
| Example | [Step 3](#use-vbtsplitter-for-a-precomputed-signal-grid) | [Step 3](#use-vbtsplit-for-functions-and-custom-selection) | [Step 3](#use-vbtcv_split-for-automatic-selection) |

* `@vbt.split` above `@vbt.parameterized` runs the whole grid inside each range, while the reverse
  order runs all ranges for each combination. Both return the same values, with the levels ordered
  `split`, `set`, parameters or parameters, `split`, `set`, and parallelize at different levels.
* Override decorator options at call time with an underscore, such as
  `_splitter_kwargs=dict(by="Y")` or `_execute_kwargs=dict(engine="pathos")` to run ranges in
  parallel.

## 3. Run the evaluation

Each decorator cuts the arguments in `takeable_args` to each range. To warm up indicators, pass the
full data with `index_from="data"` and the current range with `vbt.Rep("range_")`, then compute on
earlier bars and trim them, as the `@vbt.split` program below does. Its extra warm-up bar feeds the
one-bar signal shift. Verify a buffer against the full prefix: recursive indicators, or crossover
state spanning a long plateau of equal values, can need more history.

### Use `@vbt.cv_split` for automatic selection

`@vbt.cv_split` runs the grid on each train set, calls `selection` with the train results, and runs
the selected combination on the train and test sets. Every combination pays the overhead of a
separate call, so it fits pipelines that are fast per call. The program in the next subsection runs
it next to the grid it selects from.

* For the default min/max selection, return one score per combination. With several symbols,
  aggregate inside the pipeline, such as `pf.sharpe_ratio.mean()`, or cross-validate each symbol
  separately as shown below.
* `selection` picks the combination with the highest result by default, or the lowest with `"min"`.
  Both need one value per combination, merged with `"concat"`. For another rule, pass a function
  wrapped in `vbt.RepFunc` that receives the merged train results as `grid_results` and returns
  labels wrapped as `vbt.LabelSel([...])`. Filter weak combinations there, such as those with too
  few trades, return several labels to test several combinations, or return `vbt.NoResult` to skip a
  split without acceptable parameters.
* `merge_func="concat"` merges the splits and is copied to the grid. Pass other options of the grid,
  such as `random_subset`, `seed`, or `execute_kwargs`, through `parameterized_kwargs`.
* `return_grid="all"` also runs the full grid on each test set and returns the grid with the
  selection. `return_grid=True` returns the train grid only.
* The pipelines here return metrics. To inspect a selected portfolio, rerun the undecorated pipeline
  with the selected parameters and the same warm-up and evaluation range.

To cross-validate each symbol with its own selection, wrap the decorated function in an outer
`@vbt.parameterized` and route each `vbt.Param` to its decorator with `eval_id`:

```python
@vbt.parameterized(merge_func="concat", eval_id="symbols")
@vbt.cv_split(..., parameterized_kwargs=dict(eval_id="grid"))
def pipeline(data, window): ...


pipeline(vbt.Param(data, eval_id="symbols"), vbt.Param(windows, eval_id="grid"))
```

### Use `@vbt.split` for functions and custom selection

`@vbt.split` alone runs any function per range, such as the return of every quarter:

```python
@vbt.split(splitter="from_grouper", splitter_kwargs=dict(by="Q"), takeable_args=["data"], merge_func="concat")
def quarter_return(data):
    return data.close.iloc[-1] / data.close.iloc[0] - 1
```

This program defines one pipeline without decorators and wraps it both ways. `@vbt.cv_split` selects
the best combination per split. `@vbt.split` over `@vbt.parameterized` returns every combination on
every split and set, whose train argmax matches that selection. The program then selects manually
using the median of each window and its neighbors, which favors stable regions over isolated peaks.
The same rule can be passed to `cv_split` through `selection=vbt.RepFunc(...)`. The selection is
ranked among all combinations on each test set, where a mean near 0.5 places it near the middle of
the grid:

```python
import numpy as np
import pandas as pd
import vectorbtpro as vbt


def ma_sharpe(data, range_, fast_window, slow_window):
    start = max(range_.start - slow_window - 1, 0)
    close = data.close.iloc[start : range_.stop]
    fast = close.vbt.rolling_mean(fast_window)
    slow = close.vbt.rolling_mean(slow_window)
    warmup = range_.start - start
    pf = vbt.PF.from_signals(
        data.iloc[range_],
        entries=fast.vbt.crossed_above(slow).vbt.signals.fshift().iloc[warmup:],
        exits=fast.vbt.crossed_below(slow).vbt.signals.fshift().iloc[warmup:],
    )
    return pf.sharpe_ratio


split_kwargs = dict(
    splitter="from_rolling",
    splitter_kwargs=dict(
        length=400,
        split=300,
        offset_anchor_set=None,
        offset=-100,
        backwards="sorted",
        set_labels=["train", "test"],
    ),
    index_from="data",
    merge_func="concat",
    execute_kwargs=dict(show_progress=False),
)
cv_ma_sharpe = vbt.cv_split(**split_kwargs)(ma_sharpe)
grid_ma_sharpe = vbt.split(**split_kwargs)(vbt.parameterized(merge_func="concat", show_progress=False)(ma_sharpe))

data = vbt.GBMOHLCData.pull("A", start="2020-01-01", periods=1500, timeframe="1D", seed=42)
windows = np.arange(5, 55, 5)
args = (
    data,
    vbt.Rep("range_"),
    vbt.Param(windows, condition="fast_window < slow_window"),
    vbt.Param(windows),
)

best = cv_ma_sharpe(*args)
print(best.unstack("set")[["train", "test"]])

grid = grid_ma_sharpe(*args)
assert grid.index.names == ["split", "set", "fast_window", "slow_window"]
train = grid.xs("train", level="set")
test = grid.xs("test", level="set")
assert best.xs("train", level="set").index.tolist() == train.groupby("split").idxmax().tolist()

smoothed = train.groupby(["split", "fast_window"], group_keys=False).apply(
    lambda sr: sr.rolling(3, center=True, min_periods=1).median()
)
robust = smoothed.groupby("split").idxmax()
result = pd.DataFrame({"train": train[robust].values, "test": test[robust].values}, index=robust.values)
print(result)
percentile = test.groupby("split").rank(pct=True)[robust]
print(result["test"].isna().sum(), percentile.mean())
```

### Use `vbt.Splitter` for a precomputed signal grid

When the signals use only past data, compute them for all combinations once on the full history,
which also warms up indicators before each range, then simulate every range with `splitter.apply`.
Each range evaluates the full grid in one vectorized simulation. The signals of all combinations
must fit in memory, at rows times combinations times one byte per signal array, so split the
combinations into chunks when they do not.

This program runs a walk-forward analysis with 12 contiguous test periods. It runs 45 combinations
on 24 ranges with 24 simulations, selects the best combination on each train set, ranks it on the
following test set, and backtests the selections over all test periods at once:

```python
import numpy as np
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull("A", start="2020-01-01", periods=1500, timeframe="1D", seed=42)
splitter = vbt.Splitter.from_rolling(
    data.index,
    length=400,
    split=300,
    offset_anchor_set=None,
    offset=-100,
    backwards="sorted",
    set_labels=["train", "test"],
)


@vbt.parameterized(merge_func=("column_stack", "column_stack"), show_progress=False)
def ma_signals(close, fast_window, slow_window):
    fast = close.vbt.rolling_mean(fast_window)
    slow = close.vbt.rolling_mean(slow_window)
    return fast.vbt.crossed_above(slow).vbt.signals.fshift(), fast.vbt.crossed_below(slow).vbt.signals.fshift()


windows = np.arange(5, 55, 5)
entries, exits = ma_signals(
    data.close,
    vbt.Param(windows, condition="fast_window < slow_window"),
    vbt.Param(windows),
)


def range_sharpe(close, entries, exits):
    return vbt.PF.from_signals(close, entries, exits).sharpe_ratio


perf = splitter.apply(
    range_sharpe,
    vbt.Takeable(data.close),
    vbt.Takeable(entries),
    vbt.Takeable(exits),
    merge_func="concat",
    execute_kwargs=dict(show_progress=False),
)
train_perf = perf.xs("train", level="set")
test_perf = perf.xs("test", level="set")
assert np.isfinite(train_perf).groupby("split").any().all()
best = train_perf.groupby("split").idxmax()
print(train_perf[best].to_frame("train").assign(test=test_perf[best].values))

percentile = test_perf.groupby("split").rank(pct=True)[best]
print(percentile.mean())

test_mask = splitter["test"].get_mask()
assert test_mask.shape[1] == 12
assert test_mask.sum(axis=1).max() == 1
assert (test_mask.sum(axis=0) == 100).all()
oos_entries = oos_exits = entries.iloc[:, 0].rename(None) & False
for split, (_, fast_window, slow_window) in best.items():
    oos_entries = oos_entries.mask(test_mask[split], entries[(fast_window, slow_window)])
    oos_exits = oos_exits.mask(test_mask[split], exits[(fast_window, slow_window)])
oos = test_mask.any(axis=1)
assert np.all(np.diff(np.flatnonzero(oos)) == 1)
oos_pf = vbt.PF.from_signals(data.loc[oos], oos_entries[oos], oos_exits[oos])
print(oos_pf.stats(["total_return", "sharpe_ratio", "max_dd", "total_trades"]))
```

* `vbt.Takeable` marks an argument to be cut to each range. It works on Pandas objects and on VBT
  objects such as data, indicators, and portfolios. This example simulates each range separately
  with the default flat initial position. Taking an existing portfolio instead preserves its
  boundary state, as noted in the policies above.
* The merged result is indexed by split, set, and the parameter levels of the columns.
* Select ranges with `set_="test"` or `split=[...]`, and run ranges in parallel with
  `execute_kwargs=dict(engine="pathos")`.
* The stitched backtest adopts the new selection's signals at each test boundary and carries
  positions across it. This is one deployment policy: it does not automatically close or reopen a
  position when parameters change. Define that policy before evaluation. For independent test
  periods, start each simulation flat and implement final liquidation. Exit flags on the last bar
  can conflict with entries, so suppress conflicts and verify closed positions. `vbt.PF.row_stack`
  combines existing results. It does not rerun fills or transfer capital between independently
  funded periods.
* For a Numba pipeline, stack the ranges as columns with
  `splitter.take(data.close, into="reset_stacked_by_set")` and run the pipeline once per set. The
  stacked arrays lose their datetime index, so pass `freq` to the simulation.
* To fit a model or optimizer per split, use `splitter.apply` with `vbt.Rep("split_idx")` and
  `vbt.Rep("set_idx")`, passing each train result to its test evaluation. An outer dictionary can
  carry that state in serial execution with train-before-test ordering. In parallel execution, keep
  each split's fit and test in one worker or pass the fitted result explicitly, since worker
  processes do not share an ordinary dictionary.

## 4. Judge the out-of-sample results

* Compare train and test metrics per split. A large drop can indicate overfitting or a change in
  market conditions. Inspect the periods and trades before attributing it to either.
* Rank the selected combination among all combinations on each test period, as in step 3. Account
  for ties, missing metrics, and the number of splits before interpreting the mean percentile.
* For a continuous deployment,
  [stitch the selected signals](#use-vbtsplitter-for-a-precomputed-signal-grid) and compare with
  holding the asset over the same test periods. The example defines the `oos` mask used by
  `vbt.PF.from_holding(data.loc[oos])`.
* Look at the distribution of test results across splits, not only their mean. Few splits give
  little evidence.
* Test the stability of the selection itself: parameters that change on every split are a warning
  sign. A rule that rewards regions of good combinations, such as the neighbor median in step 3, can
  reduce sensitivity to an isolated peak. Evaluate that rule on unseen data too.
* To estimate the uncertainty of a metric, resample blocks of returns with
  `vbt.Splitter.shuffle_splits`, as shown in
  `/tutorials/cross-validation/applications/#row-stacking`.

## 5. Test robustness

A strategy that survives out-of-sample testing can still owe its results to a lucky parameter, a
lucky price path, or the number of combinations tried. Run these checks before reporting it as
robust:

* Parameter sensitivity: compare the selection with its neighbors on the test sets, as in step 4 and
  `vbt-optimization`. Performance that collapses one step away from the selection is evidence of
  sensitivity that needs investigation.
* Execution sensitivity: rerun the stitched backtest with higher costs, such as
  `fees=vbt.Param([0.001, 0.002, 0.005])` and `slippage`, and with signals delayed by one more bar
  with `entries.vbt.signals.fshift()`. Report which cost or delay assumptions remove the measured
  edge and whether those assumptions fit the intended execution setup.
* Data perturbation: run the selection on related symbols, other periods, and other providers it was
  not developed on, and bootstrap blocks of returns with `vbt.Splitter.shuffle_splits` as in step 4.
  `data.mirror_ohlc()` reverses the direction of price moves, which tests whether a long-only result
  depends on the market's trend. Small random noise scaled to each bar's range tests dependence on
  exact price levels.
* Permutation test: shuffle the returns of each of many columns with `returns.vbt.shuffle(seed=42)`,
  rebuild prices with `(1 + shuffled).cumprod()`, and rerun the whole search on every column. The
  p-value `((perm_best >= real_best).sum() + 1) / (n + 1)` accounts for the search itself, unlike a
  comparison of the winner alone. This tests a null under which return observations can be exchanged
  across time. Shuffling individual returns destroys temporal dependence, so use this p-value only
  when that null fits the question. Use block resampling when the experiment needs to preserve local
  temporal dependence.
* Ablation: put the strategy with each filter on and off in separate columns, with the same prices,
  exits, and fees, to see what each rule contributes beyond leaving fewer trades.
* Random baseline: compare the strategy with random signals that trade as often, as described in
  `vbt-signals`, and report the share of random runs it beats.
* `pf.prob_sharpe_ratio` compares with the portfolio's benchmark, which is holding the traded asset
  by default. Call it on `pf.get_returns_acc(bm_returns=False)` to compare with a Sharpe ratio of
  zero.
* Multiple testing: `returns.vbt.returns.deflated_sharpe_ratio()`, or `pf.deflated_sharpe_ratio`,
  gives, for each column, the estimated probability that its true Sharpe ratio exceeds a benchmark
  adjusted for the number and spread of the trials. Each column counts as one trial, so compute it
  on the returns of the whole grid, never on the selected column alone. Columns should represent the
  trials being assessed, not an arbitrary mixture of symbols and strategies. Check missing and
  infinite returns and scores. The implementation replaces missing returns with zero for skewness
  and kurtosis, and its raw column count does not estimate an effective number of independent
  trials. A single column returns NaN, and a grouped portfolio counts each group as one trial.
  Neighboring parameters are correlated, so a grid behaves like fewer independent trials than it has
  columns.
* Probability of backtest overfitting (PBO): split the history into an even number of blocks and
  take every half as train and the other half as test with
  `vbt.Splitter.from_purged_kfold(index, n_folds=8, n_test_folds=4)`, which gives 70 splits. PBO is
  the share of splits where the best combination on the train half ranks below the median on the
  test half. It is not built in: simulate the grid once on the full history, since the halves are
  not contiguous, and compute each combination's metric per set with
  `splitter.apply(..., vbt.Takeable(pf.returns), merge_func="concat")`. Values near 0.5 or higher
  indicate frequent below-median test ranks, rather than a probability that the strategy will lose
  money. This diagnostic uses full-path strategy returns and is distinct from independently
  restarted or deployed walk-forward simulations.

## 6. Report

Report the train and test periods, selection rule, warm-up, position-boundary policy, and metrics
per split. For a continuous walk-forward deployment, include the stitched test backtest and its
baseline. Add the robustness checks actually run and their results. Distinguish the observed test
results from in-sample performance and name any checks that could not run.

## Pitfalls

* A metric that is missing for some combinations, such as a Sharpe ratio without trades, drops out
  of `idxmax` and of ranks, and a selected combination can have no test value. Count missing values
  before selecting and before averaging ranks.
* Selecting on a metric of a single symbol ignores the others. Aggregate across symbols in the
  pipeline or in the selection, or select per symbol.
* Expanding train sets give later splits more data, so interpret train metrics alongside their
  sample lengths and covered regimes.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/cookbook/cross-validation/`: splitter recipes, `cv_split`, skipping, and warm-up
* `/tutorials/cross-validation/workflow/`: walk-forward analysis by hand and how to judge it
* `/tutorials/cross-validation/splitter/`: every way to build, inspect, and modify a splitter
* `/tutorials/cross-validation/applications/`: taking, stacking, applying, iteration schemes,
  bootstrapping, the decorators, and scikit-learn models
* `/features/optimization/time-series-cross-validation/`: purged and combinatorial splitters
