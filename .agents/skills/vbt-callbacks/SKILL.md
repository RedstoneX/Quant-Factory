---
name: vbt-callbacks
description: "Write and debug Numba callbacks for VectorBT PRO simulations. Use when decisions depend on positions, cash, fills, or stop state, or when custom orders, rebalancing, multiple fills per bar, or simulation outputs cannot be expressed as arrays. Covers from_signals and from_order_func. Use vbt-custom-simulators to write the simulation loop yourself."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Callbacks in VBT simulations

A callback is a Numba function that the simulator calls while it runs. In `from_signals`, custom
callbacks select a dynamic simulator. Compilation and execution costs depend on the callbacks and
whether the simulator is staticized. Follow `vbt-backtesting` for the overall procedure, and use
this skill for the callback.

Read `vbt-basics` once for API discovery and shared conventions. Use the sections below that apply
to the requested task.

## 1. Confirm that the task needs callbacks

Supply per-bar sizes, stops, and prices known before simulation as array arguments of
`vbt.PF.from_signals` or `vbt.PF.from_orders` when their execution model fits. Use a callback when a
decision depends on simulation state, such as positions, cash, fills, or stops, or when execution
and output requirements exceed the array-based interface. This includes several fills per bar,
custom pending-order handling, and outputs collected during simulation. Choose the callback contract
below before allocating memory.

## 2. Pick the callback and know when it runs

`vbt.PF.from_signals` calls these functions, in this order:

```text
pre_sim_func_nb                      once
  pre_group_func_nb                  once per group
    pre_segment_func_nb              per bar and group, after the state is updated at the open
      signal_func_nb                 per column, returns 4 signals
        adjust_func_nb               called by the built-in signal function only
    pre_order_segment_func_nb        after all signals, before orders are sorted and executed
      post_order_func_nb             after each order, filled or not
    post_segment_func_nb             at the end of the bar, after the state is updated at the close
  post_group_func_nb                 once per group
post_sim_func_nb                     once
```

| Task | Callback |
| --- | --- |
| Decide signals from the state | `signal_func_nb` returning long entry, long exit, short entry, and short exit |
| Change stops, limits, or order arrays while keeping the signal arrays | `adjust_func_nb` |
| React to a fill, such as setting the stops of a new position or resetting memory | `post_order_func_nb`, with `vbt.pf_nb.order_filled_nb`, `vbt.pf_nb.order_opened_position_nb`, and similar checks |
| Change, cancel, or reorder the pending orders of a bar | `pre_order_segment_func_nb`, through `c.order_info[col]` and `vbt.pf_nb.fill_col_order_info_nb` |
| Add or charge cash, such as deposits, fees, or taxes | Write `cash_deposits` in `pre_segment_func_nb` or `cash_earnings` in `post_order_func_nb` |
| Compute something once per bar for a whole group | `pre_segment_func_nb` or `post_segment_func_nb` |
| Build orders freely, such as custom rebalancing | `vbt.PF.from_order_func` (see below) |

* Each `pre_*` callback returns a tuple passed to the next inner stage and its matching `post_*`
  callback. An inner pre-callback must return any inherited objects it wants to forward. For
  example, the output of `pre_segment_func_nb` arrives right after the context in `signal_func_nb`,
  `pre_order_segment_func_nb`, and `post_segment_func_nb`.
* Passing `signal_func_nb` replaces the built-in signal function, which is the only caller of
  `adjust_func_nb`. Put the adjustment logic in the signal function, or pass
  `vbt.Rep("adjust_func_nb")` and `vbt.Rep("adjust_args")` in `signal_args` and call it there.
* In serial execution, the simulator runs one group through all rows, then the next group. Within a
  group it collects every column's signals before executing any orders for that bar. Decisions
  therefore see the state before those orders, even if an earlier column also signals an entry. A
  limit such as a maximum number of positions, checked with `vbt.pf_nb.get_n_active_positions_nb`,
  must also count the entries approved earlier on the same bar in your own memory. Keep groups
  independent when parallelizing or chunking. Cross-group reads depend on traversal and can observe
  unfinished state.
* `from_signals` permits one order per column and bar. An entry cannot be followed by a separate
  stop or limit exit on that bar, although a limit entry itself may fill on its creation bar. With
  `skip_empty=True`, the pre-order-segment callback runs when a group has a signal or active
  stop/limit to process, even if it produces no order. The post-order callback runs for attempted
  orders, including rejected ones, but not for ignored signals or a limit order that was only
  placed. An empty segment may bypass both. Put bookkeeping that must advance on quiet bars, such as
  daily counters, in a segment callback, or pass `skip_empty=False`.
* The context `c` holds the state. Index per-column fields such as `c.last_position`,
  `c.last_pos_info`, and `c.last_sl_info` with `c.col`. Cash and value fields such as `c.last_cash`
  have one element per group when cash is shared, so read them through helpers such as
  `vbt.pf_nb.get_cash_nb`, `vbt.pf_nb.get_free_cash_nb`, and `vbt.pf_nb.get_value_nb`. List the
  fields with `get_attrs` on `vbt.pf_enums.FSSignalContext`, and the helpers with `get_attrs` on
  `vbt.pf_nb`. `c.order_result` in `post_order_func_nb` holds the status, size, and fill price.
* Write only to stop and limit records, order arrays you passed, and your own memory. Writing to
  fields such as `c.last_cash` or `c.last_position` changes the simulation but not the order
  records, so the portfolio rebuilt from the orders disagrees with it.

### Timing and look-ahead

The signal function runs at the start of the bar, before the bar's stops and limit orders are
checked. Reading the current bar's high, low, or close is look-ahead unless the order fills at the
close and the decision does not also change earlier intrabar execution, such as an active stop.
`vbt.pf_nb.get_value_nb` there uses the open valuation, or the carried valuation when open is
missing. For an order at the open, read the previous bar and pass `price="open"`. Guard the first
bar, because index -1 wraps to the last row:

```python
is_entry = c.i > 0 and vbt.pf_nb.select_nb(c, entries, i=c.i - 1)
```

`price="nextopen"` and `from_ago` make the simulator read order arrays from an earlier row. A custom
signal function must apply the same offset: pass `vbt.Rep("from_ago")` in `signal_args` and read its
inputs at `c.i - abs(vbt.pf_nb.select_nb(c, from_ago))`, guarding negative rows. Otherwise it can
use current-bar information for an earlier fill. Warnings do not detect every form of look-ahead.

## 3. Pass arrays and memory with templates

Callbacks receive positional arguments only, through `signal_args`, `adjust_args`,
`post_order_args`, and the other `*_args` arguments.

* Built-in arguments such as `entries`, `size`, or `sl_stop` are broadcast before the simulation.
  Pass them to a callback with `vbt.Rep("entries")`. Put custom arrays in `broadcast_named_args` and
  pass them the same way, so they gain the columns that `vbt.Param` adds. A raw array in `*_args` is
  not broadcast: direct indexing can exceed its shape after expansion. Flexible selectors can reuse
  singleton dimensions, but cannot supply missing parameter-specific data. Scalars can be passed
  directly.
* Read the current element with `vbt.pf_nb.select_nb(c, arr)`, an earlier row with `i=...`, and a
  column from a segment-level callback, which has no current column, with
  `vbt.pf_nb.select_from_col_nb`.
* Order arguments are stored as one-element arrays when they are constant. To write a size or price
  from a callback, supply a full array with a template, such as
  `size=vbt.RepEval("np.full(wrapper.shape_2d, np.nan)")`, and write `size[c.i, c.col]`, or pass
  `arg_config=dict(size=dict(full_shape=True))`. The same applies to `cash_deposits`, which a
  pre-segment callback writes per group when `c.track_cash_deposits` is true. Compiled code normally
  omits bounds checks, so writing past the default array can corrupt memory or crash. In a price
  array, `-np.inf` means the open and `np.inf` the close.
* Keep state between bars in one-dimensional arrays with one element per column, or per group when
  cash is shared, and index them with `c.col` or `c.group`. Create them with `vbt.RepFunc` from a
  function that takes `target_shape` or `wrapper`. Each template occurrence calls the function
  again, so to share one array between two callbacks, cache it in a dictionary created right before
  the simulation. Alternatively, allocate shared memory in a pre-callback and pass it down through
  its returned tuple. Use fresh memory for independent runs and preserve it deliberately for
  continuation. Group several arrays in a named tuple, and use a Numba typed list for state of
  unknown size.
* `c.index[c.i]` is the bar's timestamp in nanoseconds. Use `vbt.dt_nb` helpers, such as
  `vbt.dt_nb.month_nb`, for calendar rules like resetting a daily loss limit.
* Change an active stop through its record, such as `c.last_sl_info[c.col]["stop"]`, from
  `adjust_func_nb` or the signal function. The fill that opens a position resets its stop records
  from the stop arguments, so a stop written before the entry is lost. Set the stops of a new
  position in `post_order_func_nb` once `vbt.pf_nb.order_opened_position_nb` is true. Set a
  price-stop argument to `np.inf` to start a stop inactive and activate it later. Read position
  metrics from `c.last_pos_info[c.col]`, whose fields follow `vbt.pf_enums.trade_dt`.
* To return custom arrays, pass `in_outputs=dict(name=vbt.RepEval(...))`, write to
  `c.in_outputs.name`, and read the result with `pf.get_in_output("name")`. Your own
  `post_segment_func_nb` replaces the one that implements `save_returns`, `save_value`, and
  `save_state`. Call `vbt.pf_nb.save_post_segment_func_nb` there with flags matching the allocated
  output fields if those built-in outputs are also needed.

This program requests entry on every bar and exits through stops. Its callback permits reentry once
20 bars have elapsed since a losing position closed and requests half of the free cash as order
value before fees. Constant input masks make the effect of position state visible. Each symbol has
independent cash:

```python
import vectorbtpro as vbt
from numba import njit


@njit
def signal_func_nb(c, entries, exits, size, cooldown, alloc):
    if c.i == 0:
        return False, False, False, False
    is_entry = vbt.pf_nb.select_nb(c, entries, i=c.i - 1)
    is_exit = vbt.pf_nb.select_nb(c, exits, i=c.i - 1)
    if not vbt.pf_nb.in_position_nb(c) and vbt.pf_nb.has_orders_nb(c):
        last_pos = c.last_pos_info[c.col]
        if last_pos["pnl"] < 0 and c.row_offset + c.i - last_pos["exit_idx"] < cooldown:
            is_entry = False
    if is_entry:
        size[c.i, c.col] = alloc * vbt.pf_nb.get_free_cash_nb(c)
    return is_entry, is_exit, False, False


data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=300, timeframe="1D", seed=42)
pf = vbt.PF.from_signals(
    data,
    entries=True,
    exits=False,
    signal_func_nb=signal_func_nb,
    signal_args=(vbt.Rep("entries"), vbt.Rep("exits"), vbt.Rep("size"), 20, 0.5),
    size=vbt.RepEval("np.full(wrapper.shape_2d, np.nan)"),
    size_type="value",
    price="open",
    sl_stop=0.05,
    tp_stop=0.05,
    init_cash=10_000,
)
print(pf.orders.records_readable[["Column", "Fill Index", "Side", "Size", "Price", "Stop Type"]])
print(pf.trades.records_readable[["Column", "Entry Index", "Exit Index", "PnL"]])
assert (pf.positions.status_closed.pnl.values < 0).any()
for col in range(len(data.symbols)):
    positions = pf.positions.values[pf.positions.values["col"] == col]
    for previous, current in zip(positions[:-1], positions[1:]):
        if previous["pnl"] < 0:
            assert current["entry_idx"] - previous["exit_idx"] >= 20
assert (pf.orders.values["idx"] > 0).all()
```

For continuation, `c.i` indexes the supplied batch, while record indices include `c.row_offset`. Use
`c.row_offset + c.i` when comparing the current row to a stored fill index or deadline. Final
simulation state does not automatically preserve arbitrary callback memory or prior signal inputs.
The example above reads the previous local row, so a continued batch needs that boundary input
handled explicitly. Follow the continuation checks in `vbt-backtesting`.

## 4. Develop without Numba, then compile

* Follow `vbt-numba` for Python-first debugging, compilation errors, and bounds checking. In this
  simulator, removing `@njit` from callbacks and passing `jitted=False` also permits Python-only
  callback libraries. Verify compiled callbacks with JIT enabled and `NUMBA_BOUNDSCHECK=1`.
* Check callback-specific contracts first: return four flags from a signal function, return a tuple
  from a pre-callback, and use `(0.1,)` for a one-element argument tuple.
* Callback arguments prevent the normal reusable simulator cache. A new process may spend
  substantial time compiling it. Define the callbacks at module level in a `.py` file and pass
  `staticized=dict(path="my_strategy_sim.py")` to write a cacheable copy of the simulator that
  imports them. The copy is rewritten when the callback source, staticization configuration, or VBT
  version changes. Changes to a module imported by the callback are not detected. Restart Python and
  force regeneration with `override=True` after those edits. Give each strategy its own path.
* Group-wise callback simulators support Numba parallel execution across independent groups with
  `jitted=dict(parallel=True)`. Keep callback writes within their own group or column. Thread
  chunking is another option for independent groups, but custom arrays need appropriate chunk
  slicing and merging. Do not split a cash-sharing group. Worker processes may compile again unless
  the simulator is staticized.

## 5. Verify against a simulation without the callback

Rebuild the callback's decisions as arrays for a simple case and run the simulation without the
callback. The orders must match. Then run the verification loop of `vbt-backtesting` and confirm
that the callback's effect shows in the orders, such as fewer trades after adding a cooldown.

## from_order_func

`vbt.PF.from_order_func` does not implement signal, stop, or limit handling for you. Its
`order_func_nb` is called for every column of each active bar and returns `vbt.pf_nb.order_nb(...)`,
`vbt.pf_nb.close_position_nb()`, or `vbt.pf_nb.order_nothing_nb()`. Its differences from
`from_signals`:

* Target size types are valued at `c.last_val_price`, which is the bar's open, or the previous close
  without open prices, not the order price. When ordering at another price, set `c.last_val_price`
  to it in `pre_segment_func_nb`.
* Orders follow the call sequence, which defaults to column order. When cash is shared,
  `vbt.pf_nb.sort_call_seq_nb` in `pre_segment_func_nb` sorts estimated order values to help release
  cash before buys. Fills still depend on cash, costs, and execution constraints.
* `segment_mask` activates only some bars, such as every 20th. `pre_segment_func_nb` and
  `post_segment_func_nb` run on inactive bars only with `call_pre_segment=True` and
  `call_post_segment=True`.
* For several orders per column and bar, use `flex_order_func_nb`, which returns a column and an
  order until it returns `(-1, vbt.pf_enums.NoOrder)`, and raise `max_order_records`. A
  pending-order queue can live in callback arrays. Expiry, cancellation, and fill priority are
  strategy logic that the callback must implement.
* `row_wise=True` processes all groups of a bar before the next bar, for decisions that need the
  current state of other groups.

When these callbacks become the bottleneck or still cannot express the strategy, write the loop
yourself as described in `vbt-custom-simulators`.

This program rebalances three assets to equal weights at the close every 20 bars:

```python
import numpy as np
import vectorbtpro as vbt
from numba import njit


@njit
def pre_group_func_nb(c):
    order_value_out = np.empty(c.group_len, dtype=np.float64)
    return (order_value_out,)


@njit
def pre_segment_func_nb(c, order_value_out, size, size_type, direction):
    for col in range(c.from_col, c.to_col):
        c.last_val_price[col] = vbt.pf_nb.select_from_col_nb(c, col, c.close)
    vbt.pf_nb.sort_call_seq_nb(c, size, size_type, direction, order_value_out)
    return ()


@njit
def order_func_nb(c, size, size_type, direction):
    return vbt.pf_nb.order_nb(
        size=vbt.pf_nb.select_nb(c, size),
        price=vbt.pf_nb.select_nb(c, c.close),
        size_type=vbt.pf_nb.select_nb(c, size_type),
        direction=vbt.pf_nb.select_nb(c, direction),
        fees=0.001,
    )


data = vbt.GBMOHLCData.pull(["A", "B", "C"], start="2024-01-01", periods=120, timeframe="1D", seed=42)
pf = vbt.PF.from_order_func(
    data,
    pre_group_func_nb=pre_group_func_nb,
    pre_segment_func_nb=pre_segment_func_nb,
    pre_segment_args=(vbt.Rep("size"), vbt.Rep("size_type"), vbt.Rep("direction")),
    order_func_nb=order_func_nb,
    order_args=(vbt.Rep("size"), vbt.Rep("size_type"), vbt.Rep("direction")),
    broadcast_named_args=dict(
        size=1 / 3,
        size_type=vbt.pf_enums.SizeType.TargetPercent,
        direction=vbt.pf_enums.Direction.LongOnly,
    ),
    segment_mask=20,
    cash_sharing=True,
    group_by=True,
    init_cash=10_000,
)
print(pf.orders.records_readable[["Column", "Index", "Side", "Size", "Price"]].head(9))
print(pf.get_asset_value(group_by=False).iloc[[0, 20, 40]].round(2))
assert len(pf.orders.values) > 0
assert (pf.orders.values["idx"] % 20 == 0).all()
weights = pf.get_asset_value(group_by=False).div(pf.value, axis=0).iloc[::20]
np.testing.assert_allclose(weights, 1 / 3, atol=0.002)
```

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/documentation/portfolio/from-signals/#callbacks`: every callback, its context, and its outputs
* `/documentation/portfolio/from-signals/#dynamic`: changing order arrays from a callback
* `/documentation/portfolio/from-signals/#custom-outputs`: filling `in_outputs` during the
  simulation
* `/cookbook/portfolio/#callbacks`: recipes for memory, cooldowns, position limits, dynamic stops,
  value-based stops, same-bar stops, pending orders, order sequence, deposits, and taxes
* `/tutorials/portfolio-optimization/dynamic/`: rebalancing with `from_order_func`
* `vectorbtpro.portfolio.nb.from_order_func.from_order_func_nb`: call hierarchy of `from_order_func`
