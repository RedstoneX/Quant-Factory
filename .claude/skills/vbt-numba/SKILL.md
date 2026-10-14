---
name: vbt-numba
description: "Write, integrate, debug, and profile custom Numba kernels for VectorBT PRO. Use when implementing compiled array calculations, rolling or streaming functions, or kernel pipelines, or diagnosing compilation errors and crashes. Use vbt-callbacks for simulation callback timing and state, and vbt-custom-simulators to write the simulation loop itself."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Numba with VBT

VBT uses compiled kernels for array calculations and simulations. Many APIs accept custom functions
compiled with `@njit`. Eligible built-in kernels can also dispatch to Rust.

Read `vbt-basics` once for API discovery and shared conventions. For a compilation error or crash,
start with [debugging](#4-debug-with-numba-disabled-then-compile). For a working but slow
calculation, start with [profiling and execution](#5-make-it-fast). Use steps 1 to 3 when
implementing a new kernel.

## 1. Look for an existing kernel

Vectorized accessor methods and existing kernels are faster to write and already tested. List a
namespace with `get_attrs` (`vbt mcp get-attrs vbt.nb`) and read a kernel with `get_source`.

| Namespace | Contents |
| --- | --- |
| `vbt.nb` | Generic kernels: rolling and expanding statistics, EWM and Wilder averages, shifting, filling, crossovers, apply and reduce, and accumulators |
| `vbt.ind_nb` | Built-in indicators, such as `atr_nb` and `bbands_nb`, and their accumulators |
| `vbt.sig_nb` | Signal ranking, cleaning, generators, and stop placement |
| `vbt.ret_nb` | Returns, drawdowns, and ratios, including rolling versions |
| `vbt.pf_nb`, `vbt.rec_nb` | Simulators, order execution, records, and trade metrics |
| `vbt.dt_nb` | Date and time parts of nanosecond timestamps, such as `hour_nb` and `weekday_nb` |

* Kernels ending in `_1d_nb` take one column, and those ending in `_nb` usually take a
  two-dimensional array, so pass `arr[:, None]` for one column. Call them from your own `@njit`
  functions, such as `vbt.nb.rolling_mean_1d_nb(close, window)`.
* `vbt.ATR.run`, `vbt.PF.from_signals`, TA-Lib, and Pandas TA cannot run inside `@njit`. Call the
  kernels instead, such as `vbt.ind_nb.atr_nb`. Kernels take enum members as integers, such as
  `vbt.pf_enums.SizeType.ValuePercent100`, and do not resolve the high-level API settings at call
  time. Pass every option you rely on. Their defaults may differ from accessors, such as `ddof=0` in
  `vbt.ret_nb.sharpe_ratio_nb`.
* Accessor methods call these kernels for you, such as `df.vbt.rolling_mean(20)`, and resolve a
  string such as `df.vbt.rolling_apply(20, "mean")` to a kernel such as `vbt.nb.mean_reduce_nb`.
* Accessors and the JIT registry can select Rust for built-in kernels, as in `vbt-rust-backend`.
  Direct calls to `*_nb` functions inside your own `@njit` function remain on Numba.

## 2. Write the kernel

Write it as plain Python on NumPy arrays that Numba can compile unchanged:

* Pass NumPy arrays, never Pandas objects. `vbt.to_2d_array(df)` gives a two-dimensional array, and
  `df.vbt.wrapper.wrap(out)` or `data.symbol_wrapper.wrap(out)` restores the labels afterwards. Cast
  object columns with `.astype(np.float64)` first.
* Write a `_1d_nb` function for one column first, then a two-dimensional wrapper that loops over the
  columns, unless the logic needs several columns at once.
* Allocate outputs with `np.full(shape, np.nan)` or `np.full(shape, False)`. Use `np.empty` only
  when every element is written, because unwritten elements hold garbage. `np.full_like(x, False)`
  inherits the dtype of `x`. Give integer arrays an explicit `np.int64` dtype, because the default
  integer is 32 bits on some Windows setups. Use floats for anything that can be missing, and check
  `np.isnan` explicitly, rather than testing equality with NaN. Ordered comparisons with NaN are
  false, while `NaN != value` is true.
* Writing to an argument changes the caller's array. Copy an input before modifying it.
* Inside `@njit`, call functions that Numba can compile or supports as intrinsics. Compute anything
  from TA-Lib, statsmodels, or Pandas before the call and pass the result as an array.
* Pass datetimes and timedeltas as nanoseconds with `vbt.dt.to_ns`, and convert every timestamp
  compared with them the same way. By default, `vbt.dt.to_ns` preserves the wall-clock time of a
  timezone-aware index, so `vbt.dt_nb.hour_nb` returns local hours. Pass `tz_naive_ns=False` for UTC
  instants. `index.asi8` also represents UTC but uses the index's unit, which need not be
  nanoseconds. Do not mix local clock values and UTC instants.
* Pass parameters that may be scalars or arrays as flexible arrays and read them with
  `vbt.flex_select_nb(arr, i, col)`, `vbt.flex_select_1d_pc_nb(arr, col)` per column, or
  `vbt.flex_select_1d_nb(arr, k)` per combination. A one-element array then applies everywhere.
* Pass every value as an argument, since Numba freezes globals at compile time. Pass lists as NumPy
  arrays, dictionaries as `numba.typed.Dict`, and groups of arrays as a `namedtuple`.
* Check every index against the array bounds, especially `i - n` lookbacks and `i + 1` lookups. A
  negative index silently reads from the end of the array, even with bounds checking.

### One pass with accumulators

Path-dependent logic, such as SuperTrend, belongs in one loop that carries its state. Accumulators,
such as `vbt.nb.rolling_mean_acc_nb`, `vbt.ind_nb.rsi_acc_nb`, and
`vbt.ret_nb.rolling_sharpe_ratio_acc_nb`, return the value of one bar and the state for the next:

* Build the input state by keyword, such as `vbt.nb.RollMeanAIS(i=i, value=..., ...)`, and copy the
  loop of the matching `_1d_nb` kernel from `get_source`, which shows the initial state, the value
  leaving the window, and any reset the accumulator needs.
* Combine accumulators and your own variables in one loop, as in
  `/tutorials/superfast-supertrend/streaming/`. To continue on a new bar, keep the state, absolute
  row position, and any history needed to supply values leaving the window. The returned state alone
  may not contain that history.
* Named tuples are immutable. Keep state that must change across calls in arrays, one element per
  column, or in a structured array created with `np.dtype([...], align=True)`. Arrays cannot grow in
  place, so preallocate the maximum size and keep a count.

## 3. Plug it into VBT

| Method | Function receives | Returns |
| --- | --- | --- |
| `df.vbt.rolling_apply(window, f)` | the values of one window of one column | a scalar |
| `df.vbt.reduce(f, *args)` | one column | a scalar per column |
| `df.vbt.map(f)` | one element | a value |
| `df.vbt.apply_along_axis(f)` | one column | an array of the same length |
| `df.vbt.groupby_apply(by, f)`, `df.vbt.resample_apply(rule, f)` | the values of one group of one column | a scalar per group |
| `df.vbt.groupby_transform(by, f)` | the rows of one group, always two-dimensional | an array of the same shape |
| `vbt.pd_acc.rolling_apply(window, f, *args)` | `from_i`, `to_i`, `col`, then `*args` | a scalar |

* Extra positional arguments are passed after the data, as in
  `df.vbt.reduce(f, vbt.dt.to_ns(df.index), 9)`. `window` takes an integer or a frequency such as
  `"7d"`, and `minp` sets the minimum number of observations.
* The meta form, called on `vbt.pd_acc`, receives the window bounds and the column, so it can read
  several arrays. Pass them with `vbt.Rep("a")` and `broadcast_named_args=dict(a=df1, b=df2)`, or as
  two-dimensional arrays with `wrapper=df.vbt.wrapper`. `to_i` is exclusive.
* Indicators, signal generators, and simulations take compiled functions as described in
  `vbt-indicators`, `vbt-signals`, and `vbt-callbacks`.

Run this program to write a one-pass kernel, check it, and pass a function to an accessor:

```python
import numpy as np
import vectorbtpro as vbt
from numba import njit, prange


@njit(nogil=True)
def bars_above_mean_1d_nb(close, window):
    if window < 1:
        raise ValueError("Window must be positive")
    mean = np.full(close.shape, np.nan)
    bars = np.full(close.shape, np.nan)
    cumsum = 0.0
    nancnt = 0
    count = 0
    for i in range(close.shape[0]):
        in_state = vbt.nb.RollMeanAIS(
            i=i,
            value=close[i],
            pre_window_value=close[i - window] if i >= window else np.nan,
            cumsum=cumsum,
            nancnt=nancnt,
            window=window,
            minp=window,
        )
        out_state = vbt.nb.rolling_mean_acc_nb(in_state)
        cumsum = out_state.cumsum
        nancnt = out_state.nancnt
        mean[i] = out_state.value
        if not np.isnan(mean[i]):
            count = count + 1 if close[i] > mean[i] else 0
            bars[i] = count
        else:
            count = 0
    return mean, bars


@njit(nogil=True, parallel=True)
def bars_above_mean_nb(close, window):
    mean = np.empty(close.shape, dtype=np.float64)
    bars = np.empty(close.shape, dtype=np.float64)
    for col in prange(close.shape[1]):
        mean[:, col], bars[:, col] = bars_above_mean_1d_nb(close[:, col], vbt.flex_select_1d_pc_nb(window, col))
    return mean, bars


@njit
def zscore_nb(window):
    std = np.std(window)
    if std == 0 or np.isnan(std):
        return np.nan
    return (window[-1] - np.mean(window)) / std


data = vbt.GBMOHLCData.pull(["A", "B", "C"], start="2024-01-01", periods=1000, timeframe="1h", seed=42)
close = data.close

mean, bars = bars_above_mean_nb(vbt.to_2d_array(close), np.array([24]))
np.testing.assert_allclose(mean, close.vbt.rolling_mean(24).values)
print(close.vbt.wrapper.wrap(bars).tail(3))

print(close.vbt.rolling_apply(24, zscore_nb).tail(3))

sample = np.array([1.0, 2.0, 3.0, np.nan, 4.0, 5.0, 6.0])
sample_mean, sample_bars = bars_above_mean_1d_nb(sample, 2)
np.testing.assert_allclose(sample_mean, [np.nan, 1.5, 2.5, np.nan, np.nan, 4.5, 5.5])
np.testing.assert_allclose(sample_bars, [np.nan, 1.0, 2.0, np.nan, np.nan, 1.0, 2.0])
assert np.isnan(zscore_nb(np.ones(3)))
```

## 4. Debug with Numba disabled, then compile

* Disable Numba while writing the kernel with `NUMBA_DISABLE_JIT=1`, as described in `vbt-basics`.
  `vbt.is_numba_enabled()` shows the result. This does not disable Rust dispatch. Select
  `jitted="nb"` in APIs that could otherwise select Rust.
* `jitted=False` in a VBT method runs only that method's outer kernel in Python. Inner kernels stay
  compiled, so a user function passed to them must still be decorated with `@njit`, otherwise it
  raises "non-precise type pyobject". Disable Numba globally to step through everything in Python.
* Read a `TypingError` from the bottom: "This error may have been caused by the following
  argument(s)" names the argument whose type Numba cannot handle.

| Message | Usual cause |
| --- | --- |
| "non-precise type pyobject", "Cannot determine Numba type of <class 'pandas...'>" | A Pandas object, a plain Python function, or an object array was passed |
| "Untyped global name" | An uncompiled function, such as from TA-Lib, called inside the kernel |
| "reflected list" | A Python list was passed instead of a NumPy array |
| "Unknown attribute" | A Pandas or Python method used on a NumPy array or scalar |
| "No implementation of function", "kws not supported" | A NumPy function or array method called with unsupported arguments or dtypes, such as `arr.max(axis=1)` |
| "Cannot unify" | A variable holds different types on different paths, such as a scalar and an array, or arrays with different dimensions |
| "No definition for lowering" with a named tuple field | A field of an immutable named tuple was assigned |

* A crashing kernel or garbage values can indicate an index out of bounds, which compiled code does
  not check by default. Set `NUMBA_BOUNDSCHECK=1` before importing vectorbtpro, or use
  `@njit(boundscheck=True)`, to raise `IndexError` instead. Rerun with Numba disabled for a full
  traceback. If it still crashes, inspect memory use, dependency versions, and a minimal reproducer
  before assigning a cause.
* Validate a kernel against a slow reference, such as Pandas code or its Python function
  `f.py_func`, on one column with missing values. `py_func` exists on a Numba dispatcher, not on the
  plain function returned when JIT is disabled, and can still call compiled inner kernels. Then run
  the final version with Numba enabled.

## 5. Make it fast

* The first call compiles, which takes seconds per function and argument types. A call with other
  types or dimensions, such as an integer instead of a float, compiles again, and so does a function
  redefined by rerunning its notebook cell. Time a kernel only after a warm-up call.
* Use `@njit(cache=True)` in a stable importable `.py` module for predictable disk-cache reuse.
  Notebook caching depends on the Numba version and source locator, while plain `exec` definitions
  usually have no cacheable source. A service can warm kernels on small inputs at startup. If a
  cache is stale, `vbt.clear_pycache()` clears VBT's package caches by default. Pass your module's
  directory to clear its `__pycache__` directories, then restart the process. This does not cover
  every external Numba cache location.
* `jitted=dict(parallel=True)` runs VBT kernels that support it over columns in parallel, and
  `chunked="threadpool"` uses the registered chunking specification to distribute work across
  threads. For column kernels this splits columns, while shared-cash simulations must keep each
  group intact. These paths need enough independent work to offset scheduling overhead, so measure
  them. Start with one layer of parallelism to avoid oversubscribing CPU threads. In your own
  kernels, `@njit(parallel=True)` with `prange` over columns does the same. Write only to the
  current column inside the loop.
* See `vbt-rust-backend` for how memory layout affects backend performance. Benchmark on the layout
  the pipeline produces.
* `@vbt.register_jitted(task_id_or_func=vbt.nb.rolling_mean_nb, jitter="np")` registers your own
  NumPy version of a built-in kernel, which `jitted="np"` then selects. Without an explicit
  `jitter`, registration infers it from the function's suffix, such as `_np`.
* `@njit(nogil=True)` lets threads run the function at the same time, as `vbt-optimization` and
  `vbt-indicators` need. Loop once over the data on scalars, since array expressions inside loops
  allocate on every step.

### Whole pipelines in Numba

When a grid is too large for one wide simulation, write the pipeline as one `@njit(nogil=True)`
function that loops over combinations and returns a metric per column and combination, as in
`/tutorials/superfast-supertrend/pipelines/` and the engineer level of `/tutorials/pairs-trading/`:

* Shift boolean signals with `vbt.nb.fshift_nb(mask)`. Simulate with `vbt.pf_nb.from_signals_nb`,
  where `group_lens` holds one entry per group, and columns in one group share cash.
* Pass `save_returns=True` and compute metrics from `sim_out.in_outputs.returns` with `vbt.ret_nb`,
  or build trades with `vbt.rec_nb.col_map_nb` and `vbt.pf_nb.get_exit_trades_nb`. To analyze one
  run fully, pass its output to `vbt.Portfolio(data, sim_out, ...)` with the same grouping, cash
  sharing, and initial cash.
* Run chunks of combinations on threads with `vbt.chunked`, sized by
  `vbt.ArraySizer(arg_query="fast_windows", axis=0)`, with `vbt.ArraySlicer(axis=0)` for each
  parameter array and `None` for other arguments in `arg_take_spec`, `merge_func="concat"`, and
  `execute_kwargs=dict(engine="threadpool")`. Each thread then stays in compiled code.
* When the built-in kernel cannot express the strategy, or its overhead dominates, write the
  simulation loop itself as described in `vbt-custom-simulators`.

```python
import numpy as np
import pandas as pd
import vectorbtpro as vbt
from numba import njit


@njit(nogil=True)
def pipeline_nb(close, fast_windows, slow_windows, fees, ann_factor):
    n_cols = close.shape[1]
    group_lens = np.full(n_cols, 1, dtype=np.int64)
    out = np.empty(fast_windows.shape[0] * n_cols, dtype=np.float64)
    for k in range(fast_windows.shape[0]):
        fast = vbt.nb.rolling_mean_nb(close, fast_windows[k])
        slow = vbt.nb.rolling_mean_nb(close, slow_windows[k])
        entries = vbt.nb.fshift_nb(vbt.nb.crossed_above_nb(fast, slow), fill_value=False)
        exits = vbt.nb.fshift_nb(vbt.nb.crossed_above_nb(slow, fast), fill_value=False)
        sim_out = vbt.pf_nb.from_signals_nb(
            target_shape=close.shape,
            group_lens=group_lens,
            close=close,
            long_entries=entries,
            long_exits=exits,
            fees=fees,
            save_returns=True,
        )
        returns = sim_out.in_outputs.returns
        out[k * n_cols : (k + 1) * n_cols] = vbt.ret_nb.sharpe_ratio_nb(returns, ann_factor, ddof=1)
    return out


data = vbt.GBMOHLCData.pull(["A", "B", "C"], start="2024-01-01", periods=1000, timeframe="1h", seed=42)
close = data.close
ann_factor = close.vbt.returns(freq="1h").ann_factor
fast_windows = np.array([10, 10, 20, 20])
slow_windows = np.array([50, 100, 50, 100])
sharpe = pipeline_nb(vbt.to_2d_array(close), fast_windows, slow_windows, 0.001, ann_factor)
param_index = pd.MultiIndex.from_arrays([fast_windows, slow_windows], names=["fast_window", "slow_window"])
sharpe = pd.Series(sharpe, index=vbt.combine_indexes((param_index, close.columns)))
print(sharpe.groupby(["fast_window", "slow_window"]).mean())

fast = close.vbt.rolling_mean(10)
slow = close.vbt.rolling_mean(50)
entries = fast.vbt.crossed_above(slow).vbt.fshift(1, fill_value=False)
exits = fast.vbt.crossed_below(slow).vbt.fshift(1, fill_value=False)
pf = vbt.PF.from_signals(close, entries, exits, fees=0.001, freq="1h")
np.testing.assert_allclose(sharpe.loc[10, 50].values, pf.sharpe_ratio.values)
```

The example shifts close-based signals one bar and fills at the following close. Use open prices
explicitly if the intended fill is the next open. Warm the pipeline before timing it. Compilation
cost depends on the signatures, code, and available caches, including those of nested kernels.

## Pitfalls

* A kernel that works on Series fails inside VBT when it receives two-dimensional arrays. Check
  `ndim` in the table above, and index rows first, as `arr[i, col]`.
* `np.argmax` of an all-`False` array is 0, not -1, so code that marks `np.argmax(mask)` as the
  first signal marks the first row of an empty group too. Loop until the first `True` instead.
* Scalar division by zero raises `ZeroDivisionError` under `@njit`'s default `error_model="python"`,
  including for floats. With `error_model="numpy"`, it produces `inf` or NaN. Handle zero
  explicitly, including a zero standard deviation in `zscore_nb`.
* `np.nan` cast to a boolean is `True`. Do not pass `fastmath=True`, which assumes no NaN values.
* Dot access to a field, such as `record.stop`, works with Numba disabled only for record dtypes, as
  in VBT. Define your own as `np.dtype((np.record, np.dtype([...], align=True)))`, or use brackets,
  such as `record["stop"]`.
* Numba supports a subset of Python and NumPy, including only some exception constructs. Keep
  validation errors simple and compile a small reproducer when argument support is unclear. When an
  array operation is unsupported, use a supported operation or write the loop. Remove `print` after
  debugging, since it is slow.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/features/performance/compute-backends/`: parallel Numba, jitting, and backend selection
* `/features/tooling/time-series-operations/`: Numba datetime and meta methods
* `/tutorials/superfast-supertrend/`: a Numba indicator, an accumulator, threads, and pipelines
* `/tutorials/pairs-trading/`: a Numba pipeline over hundreds of thousands of combinations
* `/tutorials/from-python-to-rust/static/#numba-kernels`: kernel-level simulation and metrics
* `/api/generic/nb/`: every generic kernel with its signature
