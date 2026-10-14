---
name: vbt-optimization
description: "Run, parallelize, and manage memory for VectorBT PRO parameter searches. Use when testing parameter combinations, sampling large grids, merging results, or resuming long runs. Use vbt-cross-validation to evaluate selected parameters out of sample and vbt-portfolio-optimization for asset weights."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Parameter optimization with VBT

Read `vbt-basics` once for API discovery and shared conventions. Begin with one verified pipeline
and a small serial search. Choose the grid size and execution approach below, then use the later
sections for parameter options, result storage, and parallel execution.

## 1. Size the grid

For a Cartesian grid, multiply the number of values of every parameter, then multiply by symbols to
estimate the number of result columns. Zipped parameters and conditions reduce that count. Six
parameters with ten values each are a million combinations. Estimate the memory of approaches that
keep combinations as columns: rows times combinations times symbols times 8 bytes per float64 array.
Boolean masks typically use one byte per element, and structured order records have their own size.
Indicators, signals, and a portfolio each hold several such arrays. Then decide whether to test the
full grid or a random subset.

When the research question allows staged selection, search signal parameters first, then search
stops, sizing, and asset selection for the retained configurations. A thousand signal combinations
with a hundred values each for SL and TP are ten million combinations in one grid, but far fewer in
stages. Staged search can miss interactions between signal and exit parameters. Treat it as a search
tradeoff, and retain the full joint search when those interactions define the strategy. Every added
dimension also raises the chance of fitting noise.

## 2. Choose how to run it

| The grid varies | Approach |
| --- | --- |
| Arguments of one indicator or one simulation, such as windows or stops | Pass lists to indicator `run` methods and `vbt.Param` to simulation arguments. One call computes all combinations as columns. |
| Several steps of a pipeline | Write a function that takes one value per parameter and decorate it with `@vbt.parameterized`. Each combination runs separately. |
| Signal parameters, followed by one simulation | Parameterize only the signal function with `merge_func="column_stack"` and simulate all columns at once. Faster than a whole pipeline per combination, but all signals stay in memory. |
| Too many combinations for one call, but each call is cheap | `@vbt.parameterized` with `mono_n_chunks` or `mono_chunk_len`, so the function receives a chunk of combinations as lists |
| Arrays too large for memory | `@vbt.chunked` splits the arrays of one call, such as columns, and merges the results |
| A large grid dominated by per-call Python overhead | Consider compiling the whole pipeline in Numba with `nogil=True`, from signals through `vbt.pf_nb.from_signals_nb` to a metric, and run it on threads, as described in `vbt-numba` |
| A budget that cannot cover the full search space | Consider an external optimizer, such as Optuna, calling a function that returns one metric per combination. It tests far fewer combinations, but shows no landscape to judge robustness. |

A wide call can reduce setup overhead, but holds all combination columns at once.
`@vbt.parameterized` can reduce peak memory when each call returns a small result, but retains those
results for merging and pays setup overhead per call. One millisecond of overhead is 17 minutes over
a million combinations.

### Start with a small serial search

This program samples entry lookbacks, exit lookbacks, and stop distances for a price-channel
breakout. Entry thresholds use prior highs and exit thresholds use prior lows. Each call returns
only Sharpe ratios, and the merged result is ranked across symbols. The condition keeps exit
lookbacks shorter than entry lookbacks:

```python
import numpy as np
import vectorbtpro as vbt


@vbt.parameterized(merge_func="concat", show_progress=False)
def channel_sharpe(data, entry_window, exit_window, sl_stop):
    upper = data.high.vbt.rolling_max(entry_window).shift(1)
    lower = data.low.vbt.rolling_min(exit_window).shift(1)
    pf = vbt.PF.from_signals(
        data,
        entries=data.close > upper,
        exits=data.close < lower,
        sl_stop=sl_stop,
        price="nextopen",
    )
    return pf.sharpe_ratio


data = vbt.GBMOHLCData.pull(["A", "B"], start="2020-01-01", periods=1000, timeframe="1D", seed=42)
windows = np.arange(5, 105, 5)
sharpe = channel_sharpe(
    data,
    vbt.Param(windows),
    vbt.Param(windows, condition="exit_window < entry_window"),
    vbt.Param([0.02, 0.05, 0.1]),
    _random_subset=50,
    _seed=42,
)
print(sharpe.index.names, len(sharpe))
assert len(sharpe) == 50 * len(data.symbols)
assert sharpe.index.is_unique
assert (sharpe.index.get_level_values("exit_window") < sharpe.index.get_level_values("entry_window")).all()
assert np.isfinite(sharpe).any()
mean_sharpe = sharpe.groupby(["entry_window", "exit_window", "sl_stop"]).mean()
print(mean_sharpe.sort_values().tail(5))
```

The threshold shift excludes the current bar from the channel. `price="nextopen"` separately delays
execution of the close-based decision. These shifts have different jobs. Keep the indicator's
singleton parameter levels out of each return value when adapting this pattern to indicator classes,
so the decorator supplies the search levels only once.

## 3. Build the grid

With `@vbt.parameterized`, wrap each tested argument in `vbt.Param`:

* Parameters form a Cartesian product. Give several parameters the same `level` to zip them. Once
  one parameter has a `level`, every parameter needs one, or the call raises "Please provide level
  for all product parameters".
* `condition="fast_window < slow_window"` filters combinations using argument names. A `vbt.Param`
  inside a dict or tuple argument is found and named by its path, such as `p_fast` for
  `p=dict(fast=vbt.Param(...))`, or pass `name`. Parameters inside other objects, such as class
  instances, are not found. Pass their arguments and build the object inside the function.
* `random_subset` samples combinations. With the default `build_grid=None` and no conditions, it
  avoids materializing the full product. `build_grid=True` explicitly materializes it. For sparse
  conditions on a huge grid, use `build_grid=False` with an integer subset and bound the search with
  `max_guesses` or `max_misses`. Check the returned count: there may be fewer valid combinations
  than requested.
* A dict value, such as `vbt.Param({"sma": sma_func, "ema": ema_func})`, labels the values with its
  keys, which also makes functions and other objects usable as parameters. `keys` renames the values
  and `hide=True` drops the level.
* `vbt.Param(data)` runs the pipeline once per symbol. An indicator instance splits into one
  instance per column, and a condition refers to its levels as `__level_name__`. To compute an
  indicator once and pair its columns, run it on all windows, make two copies with
  `sma.rename_levels({"sma_timeperiod": "fast"})` and `"slow"`, and pass
  `vbt.Param(fast_sma, condition="__fast__ < __slow__")` and `vbt.Param(slow_sma)`.
* Pass decorator options when calling by prefixing them with an underscore, such as
  `_random_subset=100`, `_seed=42`, or `_execute_kwargs=...`.
* Return `vbt.NoResult` to skip a combination, for example when its inputs are invalid. When every
  combination is skipped, the call raises `NoResultsException`, unless `raise_no_results=False`.
* Pass `vbt.Rep("config_idx")` as an argument to receive the position of the current combination.
* Preview the grid without running it with `vbt.combine_params`, which takes a dict of `vbt.Param`
  and returns the combinations and their index.

Parameters of indicators and simulations:

* Indicator `run` methods zip parameter lists after broadcasting singleton lists. Pass
  `param_product=True` for the product, and `random_subset` with `seed` to sample it. Ordinary
  indicator parameter lists can materialize the full product before sampling, as described in
  `vbt-indicators`, which also covers decorated functions whose outputs differ in shape from the
  inputs.
* In `vbt.PF.from_signals`, several `vbt.Param` arguments form a product. Sample it with
  `broadcast_kwargs=dict(random_subset=1000, seed=42)`.
* Include `np.nan` among stop values, such as `sl_stop=vbt.Param([np.nan, 0.02, 0.05])`, to test the
  strategy without that stop.
* Arguments of custom callbacks become parameters when passed in `broadcast_named_args`, such as
  `broadcast_named_args=dict(wait=vbt.Param([0, 5, 10]))` with `vbt.Rep("wait")` in the callback
  arguments. Each value tiles the inputs, so memory grows with every value.

For a grid too large to build, such as billions of combinations:

* `_grid_indices=slice(0, 1_000_000)` runs one slice of the grid without building the rest.
  Conditions are applied after slicing, so the result can contain fewer combinations than the slice
  length. Keep parameter order and value order fixed when resuming consecutive slices.
* `vbt.pick_from_param_grid(grid, i)` returns the combination at position `i` of the product of a
  dict of value lists, or a random one without `i`. Loop over batches of random picks, run them, and
  keep the best, as in `/tutorials/pairs-trading/`.

## 4. Return small results

Without `merge_func`, the decorator returns a list with one result per combination. Choose a merge
function that fits the result:

| Each call returns | `merge_func` | Merged result |
| --- | --- | --- |
| A number, or a Series with one value per symbol | `"concat"` | One Series indexed by the parameters |
| Arrays with the index of the data, or portfolios | `"column_stack"` | One DataFrame or portfolio with the parameters as column levels |
| Arrays with different indexes, such as one per split | `"reset_column_stack"` | Columns stacked after resetting each index |
| Arrays to be stacked in time | `"row_stack"` | One Series or DataFrame with the parameters as index levels |
| Several results | A tuple, such as `("concat", "column_stack")` | One merged result per returned value |

Return metrics, not portfolios. A portfolio holds its prices, order records, and cached results, so
a list of portfolios grows with every combination. When several metrics are needed, return them as a
tuple or compute them with `pf.stats(metrics)`. When portfolios must be kept, drop their prices with
`pf.replace(open=np.nan, high=np.nan, low=np.nan, close=np.nan)` and restore them before analysis
that needs prices. This does not remove large saved outputs or benchmark arrays, so inspect the
remaining object size. When the number of orders per column is known, `max_order_records` and
`max_log_records` size the record arrays a simulation allocates. For results that do not fit in
memory, save each result to disk inside the function and return nothing.

With `save_returns=True`, the simulation records returns, and return-based metrics such as the
Sharpe ratio, Sortino ratio, and `pf.returns_acc.max_drawdown()` skip rebuilding them. This adds a
stored returns array. Portfolio stats based on trade or drawdown records still need their inputs.

## 5. Run a sample, then scale

Run the pipeline on one combination and inspect the result. Then run a random subset of about 100
combinations and time it with `vbt.Timer` and `vbt.MemTracer` before running the full grid.

Execution is serial by default. Pass `execute_kwargs` to the decorator, or `_execute_kwargs` to the
call, to parallelize. Keys the decorator does not know, such as `engine` or `chunk_len`, are also
passed to execution.

* `dict(engine="threadpool", chunk_len="auto")` runs one chunk of as many combinations as there are
  detected cores at a time, subject to the thread pool's worker limit and the default
  `distribute="tasks"`. It helps only when the function releases the GIL, such as a function
  compiled with `@njit(nogil=True)`. Add `warmup=True` to compile it on one combination first. A
  pipeline of Pandas and VBT calls rarely runs faster on threads.
* `dict(engine="pathos", n_chunks="auto", distribute="chunks")` runs one chunk of combinations per
  process. It pays off when each combination takes long compared to copying its inputs to a process.
  Scripts that use processes must start from an `if __name__ == "__main__":` block.
* Pass either `chunk_len` or `n_chunks`, not both. These split the list of calls for execution and
  differ from the `chunk_len` and `n_chunks` of `@vbt.chunked`, which split its arguments.
* A single simulation with many columns can run on several threads with
  `vbt.PF.from_signals(..., chunked="threadpool")`, but its merged portfolio is as large as before.
  Chunk independent columns or complete shared-cash groups. Splitting time requires carrying all
  simulation and indicator state and is not interchangeable with column chunking.
* With mono-chunks, the function receives each parameter as a list. Pass
  `mono_merge_func=np.column_stack` or `"concat"` in `vbt.Param` to receive arrays instead.
* Decorate a function twice, with `eval_id="outer"` and `eval_id="inner"`, and pass the same
  `eval_id` to each `vbt.Param`, to run slow steps, such as selecting a symbol, once per outer value
  and to use different execution settings per level.
* Other engines are `"processpool"`, `"mpire"`, `"dask"`, and `"ray"`, which connects to an existing
  cluster through `init_kwargs`. Use one level of parallelism: Numba or Rust `parallel=True` inside
  tasks that already run on threads makes them compete for the same cores.
* Progress bars are shown by default. Pass `show_progress=False` to the decorator in scripts, and to
  VBT calls that run inside parallel workers, whose bars interfere with each other.

Memory and long runs:

* Memory growth can come from retained inputs/results, caches, pending tasks, or worker copies.
  Garbage collection cannot release objects that are still referenced. Pass `chunk_len` together
  with `chunk_clear_cache=True` and `chunk_collect_garbage=True` to clear caches and collect garbage
  after every chunk, or an integer to do it every that many chunks. These controls clear registry
  caches and collect garbage, like `vbt.flush`; they do not discard returned results or clear every
  cache type.
* Pass `cache_chunks=True` with `chunk_len` to save the results of each chunk to disk. When the run
  crashes and is called again, finished chunks are loaded instead of recomputed, and the cache is
  deleted after a successful run by default (`post_clear_chunk_cache=True`). A chunk is loaded only
  if its tasks call the same function with the same simple argument values, such as numbers and
  strings. The contents of arrays, data, Pandas objects, and the code of the function are not
  compared, so pass `pre_clear_chunk_cache=True` after changing them. Caching requires
  `distribute="tasks"`, the default.

## 6. Select parameters without overfitting

* Decide on one objective before the search, such as the Sharpe ratio or a score that combines
  several metrics. Ranking by several metrics afterwards picks whichever looks best.
* The best in-sample combination of a large grid can owe its rank to noise. Prefer regions where
  neighboring combinations perform well, such as by averaging a metric over a level or plotting a
  heatmap of two parameters with `sharpe.vbt.heatmap`. A peak with poor neighbors is a warning sign,
  often caused by one exceptional trade. Inspect the trades of the chosen combination.
* Decide whether parameters are shared across symbols or selected per symbol. For shared parameters,
  aggregate across symbols before ranking: `idxmax` on the unaggregated Series picks one symbol's
  best combination. To evaluate an actual shared-cash portfolio per combination, simulate with
  `group_by=vbt.ExceptLevel("symbol")` and `cash_sharing=True`, with an explicit sizing and
  call-sequence policy. That changes fills and capital allocation rather than merely averaging
  metrics.
* Filter out combinations with too few trades, whose metrics are noise.
* When several strategies are needed, choose combinations that differ from each other, such as by
  trade timing or exposure, rather than the top few, which tend to be near-duplicates.
* Validate the chosen parameters on data the search did not see, as described in
  `vbt-cross-validation`, and report both the in-sample and the out-of-sample results.

## Pitfalls

* Indicator `run` methods zip parameter lists unless `param_product=True`. Simulation and
  `parameterized` calls form a product of `vbt.Param` arguments unless their levels request zipping,
  as described in `vbt-basics`. Mixing both in one pipeline duplicates or misaligns combinations.
* `random_subset` without `seed` picks different combinations on every run.
* An exception in one combination stops the whole run. Pass `_skip_errored=True` to skip such
  combinations with a warning, or return `vbt.NoResult` for expected cases.
* `max_order_records=0` with `save_returns=True` speeds up simulations, but only metrics computed
  from returns stay correct, such as the Sharpe ratio and `pf.returns_acc.total()`. Metrics rebuilt
  from order records, such as `pf.total_return`, silently return 0 or NaN.
* Pandas `groupby` drops `NaN` keys, so pass `dropna=False` when a level such as a stop contains
  `np.nan`.
* Avoid shared mutable state between evaluations. Serial results can depend on grid order, threads
  can race, and processes normally hold separate copies. Return each evaluation's data explicitly
  unless sequential state is part of the intended algorithm.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/cookbook/optimization/`: merging, generation, execution, callbacks, total or partial and flat or
  nested parameterization, mono-chunks, chunking, super-chunks, and raw execution
* `/features/optimization/strategy-optimization/`: paramables, lazy grids, mono-chunks, and
  conditional parameters
* `/features/performance/parallel-execution-and-caching/`: chunk caching, chunking, threads, and
  processes
* `/tutorials/pairs-trading/`: staged optimization, a Numba pipeline over hundreds of thousands of
  combinations, unlimited random search, and Optuna
* `/tutorials/superfast-supertrend/pipelines/`: turning a pipeline into a fast Numba function for
  large grids
