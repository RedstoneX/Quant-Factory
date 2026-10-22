---
name: vbt-indicators
description: "Find, run, build, and debug VectorBT PRO indicators, including third-party wrappers and custom IndicatorFactory functions. Use when computing features, finding price patterns, or investigating indicator values, shapes, or column levels."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Indicators with VBT

Read `vbt-basics` once for API discovery and shared conventions. For an existing indicator, find it,
run it, and verify its outputs in steps 1 to 3. Use step 4 only for a new calculation. Pattern
search has its own workflow below.

## 1. Find an existing indicator

| Location | Source | Example name |
| --- | --- | --- |
| `vbt` | Built-in Numba indicators, also available as `vbt.RSI` and similar | `vbt:BBANDS` |
| `talib`, `talib_func` | TA-Lib as an indicator class, or as a plain function | `talib:SMA` |
| `pandas_ta`, `ta`, `technical`, `techcon`, `smc` | Pandas TA, ta, freqtrade technical and its consensus classes, Smart Money Concepts | `pandas_ta:ZSCORE` |
| `wqa101` | WorldQuant 101 Formulaic Alphas, numbered 1 to 101 | `wqa101:53` |
| `expr` | An expression built with `vbt.IF.from_expr` | `expr:rolling_max(high, @p_window)` |
| `custom` or your own | Indicators registered with `vbt.IF.register_custom_indicator` | `custom:ZSCORE` |

* List names with `vbt.IF.list_indicators`, by pattern or location, such as
  `vbt.IF.list_indicators("*ma")` or `vbt.IF.list_indicators("talib")`. Listing all locations parses
  every installed library and is slow, so store the result. Third-party locations appear only when
  their library is installed. For Pandas TA, VBT falls back to the maintained `pandas-ta-classic`
  fork when the original package is not installed.
* Get a class with `vbt.indicator("talib:RSI")`. Always pass the location. Without it, the first
  match wins and a warning names the other locations.
* Before running, print the specification with `vbt.phelp(vbt.MACD.run)`, or read `input_names`,
  `param_names`, `param_defaults`, `output_names`, `in_output_names`, and `lazy_output_names`.
  Parameter names differ by library: `window` in VBT, `timeperiod` in TA-Lib, `length` in Pandas TA.
  Some indicators have required parameters without defaults, such as `vbt.PIVOTINFO`, or required
  inputs that data does not provide, such as `periods` in `talib:MAVP`.
* Many WorldQuant alphas rank values across assets, so run them on all symbols in one call. With one
  symbol, every cross-sectional rank is the same. `vbt.VWAP` resets every day unless its `anchor`
  sets another period.
* Built-in moving averages take `wtype`: `"simple"`, `"weighted"`, `"exp"`, `"wilder"`, or
  `"vidya"`. `vbt.RSI`, `vbt.ATR`, and `vbt.ADX` default to Wilder smoothing, `vbt.MA`,
  `vbt.BBANDS`, and `vbt.STOCH` to simple, and `vbt.MACD` to exponential.
* Built-in indicators can select Rust automatically for eligible kernels when a compatible
  `vectorbtpro-rust` is installed. Availability and supported options differ by kernel. See
  `vbt-rust-backend` for dispatch rules. Pass `jitted="nb"` to `run` to force Numba when comparing
  backends.

## 2. Run it with the right parameters

`run` returns an indicator instance, not an array. Read outputs as attributes, such as `rsi.rsi`,
with `unpack()`, `to_dict()`, or `to_frame()`. A single output is also available under the short
name or `output`, such as `sma.sma` for TA-Lib's `real`. Arithmetic, comparisons, and `.vbt` on the
instance use its main output, which is the single output or the one named like the indicator.

### Run from data

* `data.run("vbt:BBANDS", window=20)` passes the features named like the indicator's inputs,
  including `hlc3`, `ohlc4`, and `returns`. Add `unpack=True` to get the output arrays.
* A list of names, classes, or `"expr:..."` strings computes several features and concatenates them
  with `run_func` and `output` column levels. A location runs all its indicators, such as
  `data.run("talib", mavp=vbt.run_arg_dict(periods=14))`, and `data.run("rolling:all")` runs a
  custom location.
* Route an argument to one indicator with `vbt.run_func_dict`, keyed by the run name such as
  `talib_sma` or by position in the list, such as `timeperiod=vbt.run_func_dict({0: 10, 1: 50})`.
  Pass all arguments of one indicator with `talib_bbands=vbt.run_arg_dict(timeperiod=20)`.
* Indicators that fail in a list are dropped with a warning that names them. Pass
  `raise_errors=True` to raise instead.
* `"talib_func:sma"` calls TA-Lib through `vbt.talib_func` without building an indicator, which is
  faster for one combination. `vbt.talib_func("SMA")(close, timeperiod=20)` does the same on arrays
  and handles DataFrames, missing values, and `timeframe`.

### Parameters and column levels

* A list of values runs one combination per value and adds a level such as `rsi_window` above the
  symbols. Lists of several parameters are zipped after singleton lists are expanded to the longest
  list. Other lengths must match. Pass `param_product=True` for every combination.
* Filter a product with a condition and sample combinations to reduce computation:
  `fast_window=vbt.Param([10, 20, 30], condition="fast_window < slow_window")` together with
  `param_product=True`, and `random_subset=100` with `seed`. Ordinary parameter lists can still
  build the full product before sampling, so sampling does not guarantee low preparation memory.
* A parameter passed explicitly adds its level even when it equals the default. Wrap a single value
  in `vbt.Default` to keep the input's columns, or pass `hide_params=True`, or a list of parameter
  names to hide.
* Pass `short_name` to tell two runs of the same indicator apart, such as
  `vbt.MA.run(close, [10, 20], short_name="fast")`, which names the level `fast_window`.
* Combine outputs of different runs through `.vbt`, as described in `vbt-basics`. Plain Pandas
  operators align by label and raise "Can only compare identically-labeled" when levels differ.
* To test combinations across several runs, such as two moving averages and an RSI, build one grid
  with `vbt.combine_params`, putting conditions that link the runs there, and run each indicator on
  its list from the grid. The lists are zipped, so the outputs pair column by column:

  ```python
  grid = vbt.combine_params(
      dict(
          fast_window=vbt.Param(windows, condition="fast_window < slow_window"),
          slow_window=vbt.Param(windows),
          rsi_window=vbt.Param([14, 21]),
      ),
      build_index=False,
  )
  fast = vbt.MA.run(data.close, grid["fast_window"], short_name="fast")
  slow = vbt.MA.run(data.close, grid["slow_window"], short_name="slow")
  rsi = vbt.RSI.run(data.close, grid["rsi_window"])
  entries = fast.ma_crossed_above(slow).vbt & rsi.rsi_below(30)
  ```

  Do not filter crossed columns by their levels afterwards. `run_combs` covers only copies of one
  indicator. When the indicator instances are not needed, a function decorated with
  `@vbt.parameterized` is simpler, as described in
  [Parameterized functions](#parameterized-functions).
* Generated helpers exist for every input and output: `rsi.rsi_crossed_below(30)`,
  `rsi.rsi_above(70)`, and `rsi.rsi_stats()` for numbers, `_and`, `_or`, and `_xor` for booleans,
  and `_readable` for enumerated outputs. They return arrays with the indicator's columns.
  `rsi.rsi_above([60, 70])` tests several thresholds as a new column level.
* Select after running with Pandas indexing, such as `rsi.loc["2024"]` or `rsi[(14, "A")]`, with
  `ma.window_loc[20]`, or with `ma.tuple_loc[[(10, "simple"), (20, "exp")]]`.
* `per_column=True` applies the n-th combination to the n-th column only, for example the best
  window of each symbol. Signal generators such as `vbt.OHLCSTX` do not support it.

### Missing values and timeframes

* Most VBT indicators tolerate missing values. Some TA-Lib functions propagate one missing value
  through all later outputs. Pass `skipna=True` to compute on valid rows only, and add
  `split_columns=True` for DataFrames. It works for indicators built with `with_apply_func`,
  including TA-Lib ones, but not with `jitted_loop=True`.
* `skipna` puts missing values back, so boolean outputs become floats. Compare them with `== 1` or
  fill them before using them as signals.
* Choose a missing-price policy before computing indicators, as described in `vbt-data`.
* TA-Lib indicators and `vbt.talib_func` take `timeframe`, such as `timeframe=["1h", "4h", "1d"]` to
  test several as a parameter. They resample the input, compute on completed bars, and align the
  result back without look-ahead. Parameters apply to the target timeframe. When the index has gaps,
  pass the source frequency with `broadcast_kwargs=dict(wrapper_kwargs=dict(freq="1h"))`.
* All inputs of one run share one index. For other indicators, resample the data first and realign
  the output, as described in `vbt-data`.
* Wide grids create large outputs: one column per combination and symbol for each output. For
  float64 outputs, estimate rows times columns times 8 bytes per output, plus intermediate arrays.
  Test a subset first, and use `vbt-optimization` for large grids.

## 3. Verify the outputs

* Print the columns of each output and check the parameter levels before combining outputs with
  other arrays.
* Rolling outputs commonly start with missing values until enough observations are available.
  Boolean comparisons often turn these rows into `False`. Do not fill warm-up values in a way that
  creates signals. When testing on a slice, such as a cross-validation split, compute indicators on
  enough earlier history and drop the warm-up rows afterwards. Recursive indicators can need more
  history than their window length. Compare against a longer prefix to choose the buffer.
* Check custom indicators for look-ahead: run them on all rows and on the first half of the rows,
  and confirm that the shared rows are identical.
* Compare a custom indicator with a reference implementation, such as a TA-Lib function or a Pandas
  calculation, on one column.
* Libraries and platforms can seed moving averages differently. Match the formula, `wtype`, window,
  input prices, and initialization before comparing. Inspect both the warm-up and later values.
  Convergence depends on the data and parameters, so do not assume a fixed number of bars.

## 4. Build a custom indicator only if none fits

| Logic | Factory method |
| --- | --- |
| A formula over inputs and parameters, written as a string | `vbt.IF.from_expr` |
| A function over one parameter combination | `vbt.IF(...).with_apply_func` |
| A function that handles all parameter combinations itself | `vbt.IF(...).with_custom_func` |
| Outputs with another shape, index, or timeframe than the inputs, or a pipeline of several indicators | `@vbt.parameterized`, described in [Parameterized functions](#parameterized-functions) |

### Expressions

* `@in_` marks inputs, `@p_` parameters, and `@out_` outputs. Open, high, low, close, and volume are
  recognized without a prefix. The first line can name the class, with an optional short name in
  brackets, such as `SuperTrend[st]:`. The last line lists the outputs, or a one-liner can use
  `@out_name:formula`.
* Functions resolve from NumPy and the Numba functions of `vbt.nb`, so `rolling_mean` means
  `vbt.nb.rolling_mean_nb`. `@talib_ema(x, n)` calls TA-Lib on two-dimensional arrays, and
  `@res_talib_atr` runs another indicator and adds its parameters with a prefix, such as
  `atr_timeperiod`. Pass your own functions and parameter defaults as keyword arguments.
* Pass `keep_pd=True` to use Pandas methods such as `close.shift()`. Print the parsed expression
  with `return_clean_expr=True`.

### Apply functions

* An apply function receives each input as a two-dimensional NumPy array with one column per symbol,
  and one value per parameter. Pass defaults as keyword arguments to `with_apply_func`.
* Pass `takes_1d=True` to receive one column at a time as a one-dimensional array, which suits
  TA-Lib and most hand-written loops. "input array has wrong dimensions" from TA-Lib means it is
  missing. Pass `keep_pd=True` to receive Pandas objects, which "'numpy.ndarray' object has no
  attribute" errors ask for. Pass `pass_wrapper=True` to receive the index and columns while keeping
  NumPy arrays. Do not convert inside the function.
* Other arguments that are neither inputs nor parameters, such as a threshold array with another
  shape, are forwarded as keyword arguments from `run`. For `jitted_loop=True`, list their names in
  `kwargs_as_args` on `with_apply_func` to pass them positionally in that order.
* A custom function must return arrays with one column per input column and combination, or it
  raises "All outputs must have the number of columns = #input columns x #parameters". Use
  `with_apply_func` unless the function needs all combinations at once. For other output shapes, see
  [Parameterized functions](#parameterized-functions).
* Declare in-place outputs with `in_output_names` and their dtype in `in_output_settings`, cache
  work shared by combinations with `cache_func`, and set output dtypes in `attr_settings` so that
  boolean outputs get `_and` helpers.
* To reuse another indicator inside an apply function, call it with `return_raw=True`, or call its
  kernel from `vbt.ind_nb` in Numba code.
* When the arguments passed to an apply function are unclear, replace it temporarily with a function
  that prints the type and shape of each argument.

### Speed and registration

* A Numba-compiled apply function can reduce Python overhead. Measure it on representative inputs.
  Run its combinations on several threads with `jitted_loop=True`, `jitted_warmup=True`, and
  `execute_kwargs=dict(engine="threadpool", n_chunks="auto")` in `run`. Python functions need
  processes, such as `execute_kwargs=dict(engine="pathos", n_chunks="auto", distribute="chunks")`,
  with serializable functions and arguments. Ensure workers can import dependencies, and do not rely
  on worker changes to globals reaching the parent process.
* `return_raw="outputs"` returns only the NumPy output arrays, `return_raw=True` returns the raw
  results without building the instance, and `run_unique=True` computes repeated combinations once.
* `vbt.IF.register_custom_indicator(ZScore, "rolling:ZSCORE")` makes an indicator available by name
  in `data.run` and `vbt.indicator`. Registration lasts for the current process only.
* For bar-by-bar updates in live trading, use the accumulators in `vbt.nb` and `vbt.ind_nb`, such as
  `vbt.ind_nb.rsi_acc_nb`, described in `/tutorials/from-python-to-rust/live/`. Each takes the
  previous state and one observation and returns the next state, which the caller stores per symbol
  and parameter. Numba rolling accumulators also need the value leaving the window, so keep the
  recent values. Rust accumulators keep their own buffers and can be cloned to branch from a warmed
  up state. To match a batch result, start from the same bar with the same settings, since
  exponential averages depend on where they start.

Run this program to see built-in and custom indicators side by side:

```python
import numpy as np
import vectorbtpro as vbt
from numba import njit


@njit
def zscore_nb(close, window):
    mean = vbt.nb.rolling_mean_nb(close, window)
    std = vbt.nb.rolling_std_nb(close, window)
    return (close - mean) / std


ZScore = vbt.IF(
    class_name="ZScore",
    input_names=["close"],
    param_names=["window"],
    output_names=["zscore"],
).with_apply_func(zscore_nb, window=20)

Deviation = vbt.IF.from_expr(
    """
    Deviation:
    deviation = close / rolling_mean(close, @p_window) - 1
    deviation
    """,
    window=20,
)

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=300, timeframe="1D", seed=42)

zscore = ZScore.run(data.close, window=[10, 20])
deviation = data.run(Deviation, window=vbt.Default(50))
print(zscore.zscore.columns)
print(deviation.deviation.columns)
print(zscore.zscore_crossed_below(-2).sum())

features = data.run(
    ["vbt:RSI", "vbt:ATR"],
    window=vbt.run_func_dict(vbt_rsi=21, vbt_atr=14),
    hide_params=True,
)
print(features.columns)

half = data.iloc[:150]
full_zscore = ZScore.run(data.close, window=10).zscore
half_zscore = ZScore.run(half.close, window=10).zscore
assert full_zscore.loc[half.index].equals(half_zscore)
reference = (data.close - data.close.rolling(10).mean()) / data.close.rolling(10).std(ddof=0)
np.testing.assert_allclose(full_zscore.to_numpy(), reference.to_numpy(), atol=1e-10, equal_nan=True)
assert zscore.zscore.shape[1] == 4
assert deviation.deviation.columns.equals(data.close.columns)
print("Indicator prefix check passed")
```

The apply function and expression build reusable indicator classes. `data.run` supplies inputs by
name and combines built-in outputs into a feature table. The assertions check the custom indicator
against Pandas, preserve its prefix when input is truncated, and verify output columns.

### Parameterized functions

The factory requires every output to match the inputs' shape and index. `@vbt.parameterized` runs
any function once per combination of the arguments wrapped in `vbt.Param` and merges what it
returns. Outputs can have any shape, and inputs can be `vbt.Data` instances or arrays that do not
broadcast together.

* Use the factory for an analyzable indicator with generated helpers, plots, and stats, or for a
  compiled loop over combinations with `jitted_loop=True`. Use the decorator for quick or flexible
  parameterization. It returns plain outputs and adds Python overhead per call, but keeps only what
  each call returns, which can need less memory than one wide run.
* `merge_func` takes one merge function per output. `"column_stack"` puts each combination's columns
  side by side and pads shorter outputs with missing values, `"concat"` stacks scalars and Series
  under the parameter index, and `None` returns a list.
* To combine several indicators into one, call `data.run` or indicator classes inside the function
  and return the outputs, such as entries and exits. Pass `hide_params=True` to the inner runs.
  Otherwise their parameter levels, such as `rsi_window`, repeat the levels the decorator adds.
* The decorator adds conditions, custom labels with `keys`, sampling, and parallel execution. See
  `vbt-optimization` for these options. Indicator `run` methods read the values of a `vbt.Param` but
  ignore its `keys`.

This program groups closes into bricks of three sizes. Each combination returns a series of bricks
whose length depends on the size, a trend series aligned with the input, and the number of bricks:

```python
import numpy as np
import vectorbtpro as vbt


@vbt.parameterized(merge_func=["column_stack", "column_stack", "concat"], show_progress=False)
def brick_features(close, brick_size):
    levels = (close / brick_size).round() * brick_size
    bricks = levels[levels.diff() != 0]
    trend = np.sign(bricks.diff()).reindex(close.index).ffill()
    return bricks.reset_index(drop=True), trend, len(bricks)


data = vbt.GBMOHLCData.pull("A", start="2024-01-01", periods=500, timeframe="1D", seed=42)
bricks, trend, n_bricks = brick_features(data.close, vbt.Param([1.0, 2.0, 5.0], name="brick_size"))
print(n_bricks)
assert bricks.columns.equals(trend.columns)
assert (bricks.notna().sum() == n_bricks).all()
assert trend.index.equals(data.index)
```

Each brick is known at the close of the bar that forms it, so `trend` can be used from that bar on.

## Patterns and projections

A pattern is a short sequence of values, such as `np.array([1, 3, 2, 4])` for a rise, a pullback,
and a breakout. VBT stretches it over a window of prices and scores the fit from 0 to 1.

| Need | Tool |
| --- | --- |
| Similarity on every bar for a few fixed windows | `vbt.PATSIM.run(price, vbt.Default(pattern), window=[20, 40])` |
| Matches over a range of window lengths, as records | `price.vbt.find_pattern(pattern, window=20, max_window=40, min_similarity=0.85)` |
| What happened after each match or signal | `ranges.with_delta(10).get_projections()` |

* `rescale_mode` defaults to `"minmax"`, which compares shapes. `"rebase"` compares relative price
  changes, so the pattern must be in price units, such as the last bars of the price itself. Other
  options, such as `max_error`, `error_type="relative"`, and `invert=True` for the mirrored pattern,
  are listed in `vbt.phelp(vbt.PatternRanges.from_pattern_search)`.
* `find_pattern` returns `vbt.PatternRanges`, records with a similarity field that support the
  methods of ranges described in `vbt-analysis`. `last_pd_mask` marks the last bar of each match,
  which is known at that bar's close, so shift it before filling on that bar.
* The default `overlap_mode="disallow"` lets a better match found later remove an earlier one, so
  `last_pd_mask` warns that it looks ahead. Search with `overlap_mode="allowall"`, or `"allow"` with
  the default `roll_forward=False`, for signals. A range's end index is the bar after the match.
* `PATSIM` compares a fixed pattern with past bars. Choose reference patterns using only data
  available before the evaluated period. Selecting a pattern from future prices leaks information
  even when the similarity calculation itself uses past bars.
* Projections cut the prices after each range, rebased to 1, into one column per event.
  `proj.iloc[-1] - 1` gives the return of each event, and `proj.vbt.plot_projections()` draws them
  with confidence bands. Keep only `status_closed` ranges, since open ones lack the bars that
  follow. For signals, `entries.vbt.signals.delta_ranges(10, close=close)` builds the same ranges,
  as described in `vbt-signals`. Compare the events with all bars or random signals before calling
  them predictive.

This program scores a pattern, searches for it, checks the search for look-ahead, and projects the
10 bars after each match:

```python
import numpy as np
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull("A", start="2020-01-01", periods=800, timeframe="1D", seed=1)
price = data.hlc3
pattern = np.array([1, 3, 2, 4])

patsim = vbt.PATSIM.run(price, vbt.Default(pattern), window=[20, 40])
print(patsim.similarity.max())

search = dict(pattern=pattern, window=20, max_window=40, min_similarity=0.85, overlap_mode="allow")
matches = price.vbt.find_pattern(**search)
print(matches.records_readable.head(3))

half = price.iloc[:500]
half_matches = half.vbt.find_pattern(**search)
assert matches.last_pd_mask.loc[half.index].equals(half_matches.last_pd_mask)
print("Pattern prefix check passed")

projections = matches.with_delta(10).status_closed.get_projections()
print((projections.iloc[-1] - 1).describe())
```

The prefix assertion passes with `overlap_mode="allow"`. The default overlap mode can fail it
because later matches can replace earlier ones.

## Pitfalls

* Label generators look into the future by design and appear in the same list as regular indicators:
  `vbt.FMAX`, `vbt.FMIN`, `vbt.FMEAN`, `vbt.FSTD`, `vbt.FIXLB`, `vbt.MEANLB`, `vbt.TRENDLB`,
  `vbt.BOLB`, and `vbt.PIVOTLB`. Use them only as targets for research, never as signals. Leave a
  gap of at least the label horizon between training labels and the test period, and for pivot and
  trend labels, the time until the outcome is known. `vbt.BOLB` measures upward moves from the
  current low and downward moves from the current high by default, and from beyond the bar's range
  with `mode="range"`.
* The `pivots` and `modes` outputs of `vbt.PIVOTINFO` place each pivot at its own bar before it is
  confirmed, so they look ahead. Use `conf_pivot`, `conf_idx`, and `conf_value` for signals.
* Signal generators such as `vbt.RAND`, `vbt.STX`, and `vbt.OHLCSTX` also appear in the list. They
  generate or process signals rather than compute indicators, and stops are usually simpler to pass
  to `from_signals`, as described in `vbt-backtesting`.
* A function that works on a Series often fails inside the factory because it receives
  two-dimensional NumPy arrays. Use `takes_1d=True`, `keep_pd=True`, or both, instead of converting
  inside the function.
* Built-in exponential and Wilder averages need `window` valid values within the span, so a gap of a
  few missing values blanks a window of output. Pass `minp=0` or `skipna=True` to keep values
  through gaps.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/cookbook/indicators/`: listing, running, retrieving outputs, running from data, parallelization,
  and registration
* `/documentation/indicators/development/`: parameters, inputs, outputs, defaults, custom arguments,
  caching, and stacking of custom indicators
* `/documentation/indicators/parsers/`: TA-Lib, Pandas TA, ta, expression syntax, and WorldQuant
  alphas
* `/documentation/indicators/pipeline/`: how the factory runs custom and apply functions
* `/documentation/indicators/analysis/`: generated helpers, indexing, metrics, and plots
* `/tutorials/superfast-supertrend/`: a Numba indicator from Pandas code to multithreading
* `/tutorials/patterns-and-projections/patterns/`: similarity, `PATSIM`, pattern search, and its
  options
* `/tutorials/patterns-and-projections/projections/`: projections, confidence bands, and event
  studies
