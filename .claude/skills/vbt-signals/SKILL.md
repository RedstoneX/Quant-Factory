---
name: vbt-signals
description: "Build and inspect boolean entry and exit signals with VectorBT PRO. Use when combining conditions, timing or filtering signals, generating stops or random baselines, or debugging missing, repeated, or misaligned signals. Simulation belongs in vbt-backtesting."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Signals with VBT

A signal is a boolean mask broadcastable to the data: `True` requests an entry or exit. It does not
guarantee an order, since the simulator also applies position and conflict rules. Entries and exits
live in separate masks, and `vbt.PF.from_signals` decides what each one does.

Read `vbt-basics` once for API discovery and shared conventions. Use the sections below that apply
to the requested task.

## Start from rules or external events

For a rule computed from price data, start with conditions below. For externally generated events:

1. Establish when each event became available and which symbol it addresses. A publication time, a
   signal time, and an intended fill time can differ. Convert timestamps to the price index's zone.
2. Build one boolean frame per signal type on the price index and columns, initialized to False. Map
   events to that frame with an explicit exact-match or next-available-bar policy. Count events
   outside the history, unknown symbols, and several events mapped to the same bar before combining
   them. Use `vbt-data` for timestamp and bar-label conventions.
3. Keep per-event size, price, or stop instructions in separate aligned arrays. A boolean mask
   cannot preserve several independent orders in one cell. Use the overlap approach below or
   `vbt-callbacks` if those orders must remain distinct or depend on portfolio state.
4. Inspect a few event timestamps against the masks, then choose fill timing in `vbt-backtesting`.
   Already executed fills belong in `vbt-analysis`, where they can be reconstructed directly.

## 1. Express each condition as a mask

| Condition | Code |
| --- | --- |
| Level comparison | `rsi.vbt < 30`, or `rsi.vbt < vbt.Param([30, 40], name="rsi_th")` for several |
| Crossover | `fast.vbt.crossed_above(slow)`, `close.vbt.crossed_below(level)` |
| Indicator helpers | `rsi_ind.rsi_crossed_below(30)`, `bb_ind.lower_above(data.low)` |
| Change over time | `x.vbt > x.vbt.fshift(1)`, or `x.vbt.ago("7d")` for a time-based lag |
| True within the last n bars or a period | `mask.vbt.rolling_any(n)`, `mask.vbt.rolling_all(n)`, `mask.vbt.any_ago("5d")`, `mask.vbt.all_ago("5d")` |
| State turns on | `state.vbt.signals.first()` keeps the first bar of each run of `True` |
| Bars since the previous signal | `mask.vbt.signals.distance_from_last()`, which excludes the current bar by default and returns -1 until a prior signal exists |
| Value at the last signal | `close.where(mask).ffill()` |
| Calendar | `wrapper.fill(False)` then `mask.vbt.set(True, every="W-MON", inplace=True)` |
| Time window | `mask.vbt.set_between(True, every="monday", start_time="12:00", end_time="17:00", inplace=True)` |

* `crossed_above` needs a value below the other series before it, then `wait + 1` consecutive values
  above it, and marks one `True` per crossing. A series that starts above does not cross, and a NaN
  resets the state, so a crossover right after an indicator's warm-up is not reported. Pass
  `skipna=True` to bridge gaps, and `wait=1` to require one confirming bar. If the series crosses
  back during `wait`, no signal is set. Equality does not establish a below state and interrupts
  confirmation after the series has moved above.
* A comparison is `True` on every bar the condition holds, while a crossover is `True` once. Use a
  comparison for a state filter and a crossover for an event. `first(after_false=True)` on a
  comparison still fires on the first bar after an indicator's warm-up, because NaN compares as
  `False`. Use `crossed_above` there.
* Build empty masks with `data.symbol_wrapper.fill(False)` or `mask.vbt.wrapper.fill(False)`, and
  set values with boolean masks or `vbt.BaseAccessor.set`. `set` takes `every`, `on`, `at_time`,
  `start`, `end`, and `indexer_method`, and places a signal at the next bar when the time is not in
  the index. Pass `indexer_method="ffill"` for the last bar at or before the time, such as an exit
  at the session close, and `None` for exact matches only. `mask.vbt.xloc[vbt.pointidx(...)] = True`
  does the same.
* To restrict entry decisions to a session, combine entries with a time mask. Filter by the
  execution bar too when fills are delayed, such as with `price="nextopen"`. Pending limit and stop
  orders can still fill outside it. Specify whether these orders remain active outside the session
  and enforce that rule in the simulation, using `vbt-callbacks` when needed. Removing bars also
  removes their price path and can hide stop hits. For exits after a duration or at a time,
  `td_stop` and `dt_stop` in `from_signals` are simpler than masks, as described in
  `vbt-backtesting`.
* To use a daily signal on hourly bars, compute it on resampled data and bring it back with
  `mask.vbt.signals.realign_closing(hourly_index, ffill=False)`, which places each signal once, at
  the last hour of the day it became known. `mask.vbt.signals.realign` aligns to the open of each
  bar, which places the signal before the daily close that produced it. Without `ffill=False`, the
  last daily value persists until the next daily close. See `vbt-data` for alignment in general.
* For event detection, `vbt.SIGDET` flags z-score outliers and `vbt.PIVOTINFO` tracks confirmed
  pivots. Read the pivot pitfall in `vbt-indicators` before using its outputs as signals.

This small check distinguishes a warm-up boundary from a crossover and verifies the default cleaning
rule for simultaneous signals:

```python
import numpy as np
import pandas as pd
import vectorbtpro as vbt

values = pd.Series([np.nan, 2.0, 0.0, 1.0, 2.0, 3.0])
assert values.vbt.crossed_above(1.0).tolist() == [False, False, False, False, True, False]
assert values.vbt.crossed_above(1.0, wait=1).tolist() == [False, False, False, False, False, True]

entries = pd.Series([True, True, False, True, False])
exits = pd.Series([False, True, True, False, True])
clean_entries, clean_exits = entries.vbt.signals.clean(exits)
assert clean_entries.tolist() == [True, False, False, True, False]
assert clean_exits.tolist() == [False, False, True, False, True]
```

## 2. Combine conditions and parameters

* Combine masks with `&`, `|`, `~`, and `^`, never with `and`, `or`, or `not`, which raise on
  arrays. Put `.vbt` on the left operand of each operation, including nested ones, such as
  `(a.vbt & b).vbt | c`, as described in `vbt-basics`. Without it, Pandas aligns by label and raises
  "Operands are not aligned" or "Length of names must match number of levels" when the parameter
  levels differ.
* Operations through `.vbt` pair columns by position and zip parameter levels. To test every
  combination of the conditions' parameters, build the product first with
  `a, b = vbt.pd_acc.x(a, b)`, then combine.
* A mask without parameter levels, such as a crossover of plain prices, broadcasts against a
  parameterized mask through the `symbol` level they share. Fix a single value with
  `vbt.Default(14)` or `hide_params=True` so that it adds no level that blocks this alignment.
* When the logic has many steps or parameters, put it into an indicator with `vbt.IF.from_expr` or
  `with_apply_func` returning a boolean output, as described in `vbt-indicators`, or write it for
  one parameter combination and decorate it with `@vbt.parameterized`, as described in
  `vbt-optimization`. Both handle the grid and the column levels.
* Signals of one asset can drive another, such as entries on B when A's RSI is high. Select the
  source column as a Series so that it broadcasts to every column of the target.

## 3. Select and time the signals

* Keep the first signal of each run of consecutive `True` values with `mask.vbt.signals.first()`.
  Pass `after_false=True` to skip a run that starts at the first bar. `nth(n)`, `from_nth(n)`, and
  `to_nth(n)` select by position within each run, which gives confirmations: `from_nth(2)` keeps
  signals only from the third consecutive bar.
* `first_after(reset_by)`, `nth_after`, and `from_nth_after` count from the last signal of another
  mask instead, such as the first exit after each entry:
  `exits.vbt.signals.first_after(entries, reset_wait=0)`.
* These methods compare ranks, which you can use directly. `pos_rank()` numbers the signals of each
  run from 0 and marks `False` with -1, `pos_rank(allow_gaps=True)` numbers them across the column,
  and `partition_pos_rank()` numbers the runs. For example, `partition_pos_rank() > 0` drops the
  first run to wait for the next occurrence. `rank(rank_func_nb)` runs a custom Numba ranker, and
  `as_mapped=True` returns a mapped array for reductions by group.
* `entries.vbt.signals.clean(exits)` keeps alternating pairs: the first entry, then the first exit
  after it, and so on. It drops an entry and an exit on the same bar, starts with an entry, and
  accepts a single mask to act like `first`. Pass `keep_conflicts`, `force_first=False`, or
  `reverse_order=True` to change this. Combine several exit masks with `|` before cleaning, so that
  the first exit after each entry wins. It cleans only two masks. For long and short masks, combine
  `long_entries | short_exits` and `long_exits | short_entries`, clean, and split them back, or
  write a Numba loop as in `/cookbook/signals/#cleaning`.
* With accumulation disabled, `from_signals` ignores repeated entries in the same direction while a
  position is open and ignores exits while flat. Opposite entries follow the reversal/conflict
  rules. Cleaning is not required for a simulation. Clean to count or analyze signals. Do not clean
  when the simulation uses `accumulate` or stops, because an early stop exit makes later entries
  valid again.
* To keep the first signal per day or another period, use
  `mask.vbt.groupby_transform("1D", first_nb)`. `first_nb` is a Numba function that receives the
  rows of one period as a two-dimensional array, even for a Series, and returns a mask of the same
  shape with only the first `True` of each column. Keep a period without signals all `False`:
  `np.argmax` returns 0 for it, so check the value at that position before setting it.
* Shift with `mask.vbt.signals.fshift(n)`, which fills with `False`. Pandas `shift` turns a boolean
  mask into objects with NaN. Shift only forward. A negative shift, or `bshift`, uses future bars,
  and so does keeping the last signal of each run, which needs the next bar. The execution timing
  itself (`price="nextopen"`, or `fshift` with `price="open"`) is covered in `vbt-backtesting`.

## 4. Generate exits that depend on entries

Prefer stops in `from_signals`, such as `sl_stop`, `tsl_stop`, `tp_stop`, and `td_stop`: they are
simpler and handle positions correctly. Generate exit masks only to analyze them, to test stops
outside a simulation, or for exit logic that stops cannot express. Generators suit logic where a
signal depends on the previous opposite signal. When it depends on the simulation, such as the
position or cash, use `signal_func_nb` as described in `vbt-callbacks`.

| Generator | Purpose |
| --- | --- |
| `vbt.OHLCSTX`, `vbt.OHLCSTCX` | Stop loss, trailing stop, trailing take profit, and take profit on OHLC, with `stop_price` and `stop_type` outputs |
| `vbt.STX`, `vbt.STCX` | A stop on one series, with `entries`, `entry_ts`, `ts`, `follow_ts`, and a negative `stop` for a downward cross |
| `vbt.RAND`, `vbt.RPROB` | Random entries by count or by probability |
| `vbt.RANDX`, `vbt.RPROBX`, `vbt.RPROBCX` | Random exits after given entries |
| `vbt.RANDNX`, `vbt.RPROBNX` | Random entry and exit pairs |

* The suffix `X` generates exits after each entry, and `CX` chains them: it also returns
  `new_entries` without the entries that arrived while a previous one was still open. Use the `CX`
  version whenever entries can repeat before an exit, otherwise the exits do not belong to the
  entries that the simulation executes.
* `OHLCSTX` takes `entries`, `entry_price`, `open`, `high`, `low`, and `close`, in this order. Pass
  the close as `entry_price` when entries are computed on the close, and `is_entry_open=True` only
  when they fill at the open. `is_entry_open` controls which entry-bar prices are usable, while
  `wait` controls when exits may start. Use `wait=0` only when entry-bar exits are intended. Stops
  are fractions, such as `sl_stop=0.05`, so convert an absolute distance with
  `distance / entry_price`. Within a bar it assumes the stop loss is hit before the take profit.
  `stop_type_readable` tells which stop fired.
* Parameters of generators broadcast with the data. Wrap a fixed value in `vbt.Default` to hide its
  level, pass a list to test several values, and pass a two-dimensional array such as
  `np.array([[0.03, 0.08]])` for one value per column, since `per_column` is not supported.
* To simulate the exits of `ohlcstcx = vbt.OHLCSTCX.run(...)`, fill them at the stop price with
  `price = ohlcstcx.stop_price.fillna(ohlcstcx.close)`, and pass `ohlcstcx.new_entries`,
  `ohlcstcx.exits`, and `price=price` to `from_signals`. Without `price`, every exit fills at the
  close.
* For a random benchmark, generate as many signals as the strategy produces with `vbt.RANDNX`,
  passing `n` per column, `input_shape`, `input_index`, `input_columns`, and `seed`. Compare the
  strategy with the distribution over many seeds, not with one run. Exact counts look into the
  future of each column, so use random signals only as benchmarks. `mask.vbt.shuffle(seed=42)`
  permutes each column and keeps its count.
* For custom logic, `vbt.SignalsAccessor.generate`, `generate_exits`, and `generate_both` call a
  Numba placement function on each segment, and `vbt.SignalFactory` with `with_place_func` turns it
  into an indicator with parameters. The function returns the position of the last signal it placed,
  relative to `ctx.from_i`, or -1. In an exit placement function, `ctx.to_i` is the next entry,
  which is known only in hindsight. Use it only to bound the loop.
* `generate_exits` searches only up to the next entry, so an entry followed too soon by another gets
  no exit. Pass `until_next=False` together with `skip_until_exit=True` to search further and skip
  the entries that the simulation would ignore. `generate_both` alternates an entry and an exit
  function. Pass arrays to it through `broadcast_named_args` and `vbt.Rep`, with
  `broadcast_kwargs=dict(post_func=np.asarray)` so that the functions receive NumPy arrays.

## 5. Inspect before simulating

* Print the columns and `mask.sum()` of every mask. Zero signals, signals on most bars, or columns
  from a zipped instead of a crossed grid show up here first.
* `mask.vbt.signals.stats(column=...)` reports the count, rate, distances, and partitions.
  `settings=dict(target=exits)` adds overlaps and the distance from each entry to the next exit.
* `entries.vbt.signals.between_ranges(target=exits)` returns ranges from each entry to its exits,
  and `partition_ranges()` returns runs of consecutive signals. Their `duration` is a mapped array
  with `mean`, `max`, and `describe`.
* `entries.vbt.signals.delta_ranges(30, close=close)` returns the 30 bars after each signal as
  ranges, for an event study of what follows a signal before any trading rule is added.
* Plot signals over prices with `mask.vbt.signals.plot_as_entries(y=close)` and `plot_as_exits` on
  one column, passing `fig=` to add to an existing figure. `mask.vbt.signals.plot()` draws the mask
  as a line, not as markers.
* Check signal code for look-ahead: run it on all rows and on the first half of the rows, and
  confirm that the shared rows are identical.

This program combines two conditions, checks their history and columns, and simulates the signals
with next-open execution:

```python
import vectorbtpro as vbt


def make_signals(data):
    bb = vbt.BBANDS.run(data.close, window=20, hide_params=True)
    rsi = vbt.RSI.run(data.close, window=14, hide_params=True).rsi
    oversold = rsi.vbt < vbt.Param([30, 40], name="rsi_th")
    touch = data.low.vbt.crossed_below(bb.lower)
    entries = oversold.vbt.rolling_any(3).vbt & touch
    exits = data.high.vbt.crossed_above(bb.middle)
    return entries, exits


data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=500, timeframe="1D", seed=42)
entries, exits = make_signals(data)
print(entries.columns)
print(entries.sum())

half_entries, half_exits = make_signals(data.iloc[:250])
assert entries.iloc[:250].equals(half_entries)
assert exits.iloc[:250].equals(half_exits)
print("Signal prefix checks passed")

assert entries.columns.names == ["rsi_th", "symbol"]
assert entries.shape[1] == 2 * len(data.symbols)

entries, exits = entries.vbt.signals.fshift(), exits.vbt.signals.fshift()
pf = vbt.PF.from_signals(data, entries, exits, price="open")
print(pf.total_return)

assert len(pf.orders.values) > 0
assert (pf.orders.values["idx"] > 0).all()
```

`oversold` carries the `rsi_th` level and `touch` does not, so they broadcast through `symbol`. The
prefix assertions check that truncating inputs leaves earlier signals unchanged. Signals are shifted
one bar and filled at the next open because they use the close of their own bar.

## Compare with a random signal baseline

This independent example compares a weekly calendar rule with 20 random runs on the same prices. It
marks Monday and Friday decision bars and fills at the following open, with the same fees in every
run. Each random column requests as many signal pairs as the strategy has cleaned exit signals. A
final unmatched strategy entry is excluded from that count. Count signals before shifting and filled
trades afterwards because the last signal can fall beyond the available prices.

```python
import numpy as np
import pandas as pd
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=500, timeframe="1D", seed=42)
entries = data.symbol_wrapper.fill(False).vbt.set(True, every="monday")
exits = data.symbol_wrapper.fill(False).vbt.set(True, every="friday")
assert (entries.index[entries.any(axis=1)].weekday == 0).all()
assert (exits.index[exits.any(axis=1)].weekday == 4).all()
entries, exits = entries.vbt.signals.clean(exits)
n_pairs = exits.sum()
assert (n_pairs > 0).all()
pf = vbt.PF.from_signals(
    data,
    entries.vbt.signals.fshift(),
    exits.vbt.signals.fshift(),
    price="open",
    fees=0.001,
)

random_returns = []
random_closed_trades = []
for seed in range(20):
    rand = vbt.RANDNX.run(
        n=n_pairs.to_numpy(),
        input_shape=entries.shape,
        input_index=entries.index,
        input_columns=entries.columns,
        seed=seed,
        hide_params=True,
    )
    np.testing.assert_array_equal(rand.entries.sum(), n_pairs)
    np.testing.assert_array_equal(rand.exits.sum(), n_pairs)
    rand_pf = vbt.PF.from_signals(
        data,
        rand.entries.vbt.signals.fshift(),
        rand.exits.vbt.signals.fshift(),
        price="open",
        fees=0.001,
    )
    random_returns.append(rand_pf.total_return)
    random_closed_trades.append(rand_pf.trades.status_closed.count())

returns = pd.DataFrame(random_returns, index=pd.RangeIndex(20, name="seed"))
closed_trades = pd.DataFrame(random_closed_trades, index=returns.index)
assert returns.columns.equals(pf.total_return.index)
assert np.isfinite(returns.to_numpy()).all()
print(returns.describe())
print(returns.lt(pf.total_return, axis="columns").mean().rename("fraction_beaten"))
print(pd.DataFrame(dict(signal_pairs=n_pairs, strategy_closed_trades=pf.trades.status_closed.count())))
print(closed_trades.agg(["min", "max"]))
```

The fraction beaten uses strict comparisons, so ties do not count as wins. Twenty seeds illustrate
the workflow. Use more seeds to assess the stability of the comparison. Matching signal counts does
not match holding periods, exposure, or filled trade counts. The counts use the full sample, so this
baseline is a retrospective comparison and supplies no out-of-sample evidence.

## Unraveling signals into positions

Each column of a simulation holds one position at a time. To give every signal its own position,
such as overlapping trades with their own stops, unravel the masks into one column per signal:

* `entries.vbt.signals.unravel()` puts each entry into its own column under a `signal` level.
  `entries.vbt.signals.unravel_between(exits, relation="onemany")` puts each entry with its
  following exits into one column. It drops an entry without an exit before the next entry,
  including the last open one, so pass `incl_open_source=True` when stops close the positions. Other
  relations, such as `"anychain"`, pair signals differently, so print the columns and counts.
* Simulate with `group_by=vbt.ExceptLevel("signal")` and `cash_sharing=True` to get one portfolio
  per original column, with a fixed size such as `size=100, size_type="value"`.
* Unraveling creates a column per signal, and memory grows with the number of signals times the
  number of bars. Test on a short range first, and use `vbt-callbacks` when positions interact.

## Pitfalls

* Signals must be boolean. Compare float masks, such as indicator outputs computed with
  `skipna=True`, with `== 1`, since `astype(bool)` turns NaN into `True`.
* `close[entries]` selects the close on signal bars. To attach a value to signal bars only, such as
  a price, fill an array and assign with the mask: `price = close.vbt.wrapper.fill()`, then
  `price[entries] = close[entries]`.
* `vbt.OHLCSTX` and `vbt.OHLCSTCX` do not infer direction from entry masks. Use `reverse=False` for
  long positions and `reverse=True` for shorts, either in separate runs or as an array sampled at
  entries. Selecting short-entry signals alone does not reverse the stops.
* An exit placed on the entry bar, which `wait=0` allows in the generators, conflicts with the entry
  in `from_signals`, and both are dropped by default. A separate exit mask cannot reproduce an entry
  and a stop fill on the same bar without changing the simulation approach.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/tutorials/signal-development/generation/`: comparisons, crossovers, products, shifting, rolling
  tests, schedules, custom loops, and all generator modes
* `/tutorials/signal-development/pre-analysis/`: ranking, cleaning, durations, and signal statistics
* `/tutorials/stop-signals/`: stop generators over a large grid, compared with random and holding
  exits
* `/cookbook/signals/`: cleaning four masks in Numba
* `/cookbook/indexing/#modify-values-with-accessors`: setting signals at times with `xloc`
* `/features/indicators/trading-signals/`: unraveling, signal detection, and pivots
* `/api/signals/generators/`: parameters of every preset generator
