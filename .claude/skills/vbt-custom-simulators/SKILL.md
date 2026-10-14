---
name: vbt-custom-simulators
description: "Write custom Numba simulators for VectorBT PRO from its order execution functions. Use when writing the simulation loop directly, managing custom accounting, pending-order state, or several account states per asset, stopping some columns early, or running many backtests in a compiled pipeline with reduced overhead. Use vbt-callbacks when built-in callbacks suffice, including multiple fills per bar."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Custom simulators

A custom simulator is a Numba function you write yourself. It loops over groups, columns, and rows,
decides orders, executes them with the same functions that the built-in simulators use, carries the
account state, and writes order records. `vbt.PF` wraps those records for the usual analysis.

A custom loop compiles only the logic the strategy uses and can reduce the built-in simulators'
feature, callback-context, and output overhead. Measure that benefit on the target workload. It can
keep custom state, issue several orders per bar, stop early, or return metrics without records. You
own signal timing, pending orders, stops, valuation, and record storage. The SuperTrend pipeline
tutorial below demonstrates the performance benefit.

The native Rust crate mirrors these functions with full parity. To port a finished simulator, see
`vbt-rust-native`.

Read `vbt-basics` once for API discovery and shared conventions, and `vbt-numba` for compiling,
debugging, and chunking compiled code.

## 1. Choose the layer

| The strategy needs | Use |
| --- | --- |
| Signals, stops, and limit orders expressed as arrays | `vbt.PF.from_signals`, see `vbt-backtesting` |
| Decisions from positions, cash, or fills, with one order per column and bar | `signal_func_nb` or `vbt.PF.from_order_func`, see `vbt-callbacks` |
| Several orders per column and bar, including a custom pending-order queue | `vbt.PF.from_order_func` with `flex_order_func_nb`, see `vbt-callbacks` |
| A built-in simulation and metrics inside one compiled pipeline | Built-in kernels, see "Whole pipelines in Numba" in `vbt-numba` |
| Direct control of account state and execution, such as several account states per asset or stopping some columns early, or reducing measured simulator overhead | A custom simulator |

Go down a layer only when the one above cannot express the strategy or is too slow for the workload.
Keep the higher layer for verification in [step 5](#5-wrap-and-verify).

## 2. Understand the execution model

Within each independent group, process rows in time order. Value holdings before sizing orders,
execute in the chosen call sequence, and carry each order's returned state into the next execution.

The execution functions take explicit account state and return its replacement. Record processing
also mutates caller-owned arrays and counters:

* `vbt.pf_enums.ExecState` holds `cash`, `position`, `debt`, `locked_cash`, `free_cash`,
  `val_price`, and `value`. With cash sharing, cash, free cash, and value belong to the group.
  Position, debt, locked cash, and valuation price belong to the column.
* `vbt.pf_nb.order_nb` creates a `vbt.pf_enums.Order`. Prefer it to the named tuple: it accepts any
  subset of keyword arguments and casts their types, so Numba can unify orders created in different
  branches. `vbt.pf_nb.close_position_nb` targets a zero position, and `vbt.pf_nb.order_nothing_nb`
  is ignored.
* `vbt.pf_nb.execute_order_nb` validates the state and order, resolves the price, converts the size
  to units, and calls `vbt.pf_nb.buy_nb` or `vbt.pf_nb.sell_nb`. These apply direction, reversal,
  leverage, fees, slippage, granularity, partial fills, and the price-area check. It returns a
  `vbt.pf_enums.OrderResult` and the new state, and raises `ValueError` for invalid inputs.
* `vbt.pf_nb.process_order_nb(group, col, i, exec_state, order, ...)` calls `execute_order_nb`,
  writes each fill when `order_records` and `order_counts` are supplied. For `log=True`, also supply
  `log_records` with `vbt.pf_enums.log_dt` and `log_counts`. Nonempty buffers raise `IndexError`
  when a column runs out of capacity. Omitted buffer pairs disable those writes.

A custom loop must respect these rules:

* Status: `result.status` is a field of `vbt.pf_enums.OrderStatus`: filled, ignored, or rejected. An
  unfilled order returns NaN size and price and leaves the state unchanged. Read the reason with
  `vbt.pf_enums.status_info_desc[result.status_info]` when `status_info >= 0`. Update cost basis and
  filled quantities only after a fill. Expiry, cancellation, and trailing updates have their own
  conditions and do not require a fill.
* Price: `price=np.inf` means the close and `-np.inf` the open of the `vbt.pf_enums.PriceArea`.
  Without a price area, both resolve to NaN and the order is silently ignored. Price-area fields
  must be finite or NaN. `PriceAreaVioMode.Ignore` permits prices outside the bar by ignoring the
  violation. `Cap` caps the price, and `Error` raises.
* Size and direction: for non-target sizes with `Direction.LongOnly` or `Direction.Both`, positive
  buys and negative sells. `Direction.ShortOnly` flips the sign. A positive target can sell when
  holdings exceed it. An infinite size uses all available resources. Under `Direction.Both`, selling
  more than a long position reverses it into a short. `size=-np.inf` with `Direction.LongOnly`, or
  `close_position_nb`, only closes.
* Size conversion: `Percent` uses available resources, and `TargetAmount` uses the current position.
  `Value` and `TargetValue` need `val_price` and the multiplier. `ValuePercent` and `TargetPercent`
  also need group `value`. These requirements apply to the `100` variants too. A required NaN
  valuation field ignores the order. Nonpositive `value` rejects value-percent and target-percent
  orders. A required `val_price` must be finite and nonzero.
* Valuation: group `value` is cash plus the sum of `position * val_price * multiplier` for nonzero
  positions. Skip zero positions so `0 * NaN` cannot contaminate the group. Decide whether missing
  prices on held assets carry forward or prevent valuation. Recompute at each decision point.
  Execution keeps this snapshot unless `update_value=True`. With that option, carry the returned
  group `value` and column `val_price` forward as well as the account fields.
* Timing: the gap between the valuation price and the order price is the time between decision and
  execution. Deciding from the close of bar `i` and filling at its open is look-ahead. For a
  next-open fill, store the decision and execute it on the next bar with `price=-np.inf`. When two
  events can trigger within one bar, their order inside the bar is unknown. Choose a rule and state
  it.
* Accounting: `cash` can turn negative with leverage. `free_cash` is what new orders may use, while
  debt and locked cash track borrowed funds. Write all five account fields back after each order.

`vbt.pf_nb.buy_nb` and `vbt.pf_nb.sell_nb` take a `vbt.pf_enums.AccountState` and a size in units,
without validation or size conversion. Call them directly only when units, side, and price are
already known and valid.

## 3. Write the loop

A loop needs these pieces:

* Records: `np.empty((max_records, n_cols), dtype=vbt.pf_enums.order_dt)` with one counter per
  column. One record per bar suffices for one order per bar. Multiply by the maximum number of
  orders per bar otherwise. Return `vbt.nb.repartition_nb(order_records, order_counts)`, which keeps
  only the filled records and requires the two-dimensional layout.
* Inputs: convert scalars and compact arrays once with `vbt.to_2d_array_nb(np.asarray(arr))` into a
  new variable, since Numba cannot change a variable's type, and read elements with
  `vbt.flex_select_nb(arr_, i, col)`. Use `vbt.to_1d_array_nb` and `vbt.flex_select_1d_pc_nb` for
  values per group or column, such as initial cash. Pass `target_shape` explicitly, built with
  `vbt.broadcast_shapes`. With `rotate_cols=True`, columns beyond an array's width wrap around, so a
  parameter grid can reuse untiled price data. Build that target shape with `vbt.tile_shape`.
* Groups: pass `group_lens` from `vbt.Grouper.get_group_lens` or a grouped wrapper. A group's
  columns are contiguous and start at `np.cumsum(group_lens) - group_lens`. Keep cash and free cash
  as group scalars, and position, debt, and locked cash in arrays with one element per column.
* Call sequence: when cash is shared, estimate each order with `vbt.pf_nb.approx_order_value_nb` and
  sort the column indices with `vbt.pf_nb.insert_argsort_nb`, so that sells release cash before
  buys. Both arrays are sorted in place, so refill them on every bar.
* Custom state: keep pending orders, stops, cost bases, or counters in arrays indexed by column or
  slot, with NaN for empty slots. Record arrays with `vbt.pf_enums.limit_info_dt` or
  `vbt.pf_enums.sl_info_dt` reuse the layout of the signal simulator.

This program rebalances three assets that share cash to fixed weights every 20 bars. It values the
group at the open, sorts orders by value, and fills at the close. Missing opening prices are not
forward-filled, so an unpriced holding prevents target-percent orders for that group on that bar.
The reference uses the same policy with `ffill_val_price=False`:

```python
import numpy as np
import vectorbtpro as vbt
from numba import njit


@njit
def rebalance_nb(target_shape, group_lens, open, close, target_pct, init_cash, fees):
    open_ = vbt.to_2d_array_nb(np.asarray(open))
    close_ = vbt.to_2d_array_nb(np.asarray(close))
    target_pct_ = vbt.to_2d_array_nb(np.asarray(target_pct))
    fees_ = vbt.to_2d_array_nb(np.asarray(fees))
    init_cash_ = vbt.to_1d_array_nb(np.asarray(init_cash))
    order_records = np.empty(target_shape, dtype=vbt.pf_enums.order_dt)
    order_counts = np.zeros(target_shape[1], dtype=np.int_)
    group_start_idxs = np.cumsum(group_lens) - group_lens

    for group in range(len(group_lens)):
        from_col = group_start_idxs[group]
        group_len = group_lens[group]
        cash = float(vbt.flex_select_1d_pc_nb(init_cash_, group))
        free_cash = cash
        position = np.zeros(group_len)
        debt = np.zeros(group_len)
        locked_cash = np.zeros(group_len)
        order_value = np.empty(group_len)
        call_seq = np.empty(group_len, dtype=np.int_)

        for i in range(target_shape[0]):
            value = cash
            for c in range(group_len):
                if position[c] != 0:
                    value += position[c] * vbt.flex_select_nb(open_, i, from_col + c)
            for c in range(group_len):
                col = from_col + c
                exec_state = vbt.pf_enums.ExecState(
                    cash, position[c], debt[c], locked_cash[c], free_cash, vbt.flex_select_nb(open_, i, col), value
                )
                order_value[c] = vbt.pf_nb.approx_order_value_nb(
                    exec_state,
                    vbt.flex_select_nb(target_pct_, i, col),
                    vbt.pf_enums.SizeType.TargetPercent,
                    vbt.pf_enums.Direction.Both,
                )
                call_seq[c] = c
            vbt.pf_nb.insert_argsort_nb(order_value, call_seq)

            for k in range(group_len):
                c = call_seq[k]
                col = from_col + c
                size = vbt.flex_select_nb(target_pct_, i, col)
                if np.isnan(size):
                    continue
                exec_state = vbt.pf_enums.ExecState(
                    cash, position[c], debt[c], locked_cash[c], free_cash, vbt.flex_select_nb(open_, i, col), value
                )
                order = vbt.pf_nb.order_nb(
                    size=size,
                    price=vbt.flex_select_nb(close_, i, col),
                    size_type=vbt.pf_enums.SizeType.TargetPercent,
                    fees=vbt.flex_select_nb(fees_, i, col),
                )
                _, exec_state = vbt.pf_nb.process_order_nb(
                    group, col, i, exec_state, order, order_records=order_records, order_counts=order_counts
                )
                cash = exec_state.cash
                free_cash = exec_state.free_cash
                position[c] = exec_state.position
                debt[c] = exec_state.debt
                locked_cash[c] = exec_state.locked_cash

    return vbt.nb.repartition_nb(order_records, order_counts)


data = vbt.GBMOHLCData.pull(["A", "B", "C"], start="2024-01-01", periods=250, timeframe="1D", seed=42)
wrapper = data.symbol_wrapper.regroup(True)
target_pct = wrapper.fill(group_by=False)
target_pct.iloc[::20] = [0.5, 0.3, 0.2]

order_records = rebalance_nb(
    wrapper.shape_2d,
    wrapper.grouper.get_group_lens(),
    data.open.values,
    data.close.values,
    target_pct.values,
    10_000.0,
    0.001,
)
pf = vbt.PF(wrapper, order_records, open=data.open, close=data.close, cash_sharing=True, init_cash=10_000)
ref_pf = vbt.PF.from_orders(
    data,
    size=target_pct,
    size_type="targetpercent",
    val_price=data.open,
    ffill_val_price=False,
    fees=0.001,
    group_by=True,
    cash_sharing=True,
    call_seq="auto",
    init_cash=10_000,
)
print(pf.orders.records_readable[["Column", "Index", "Size", "Price", "Side"]].head(6))
print(pf.allocations.iloc[[20, 40, 60]].round(3))
assert len(pf.orders.values) == len(ref_pf.orders.values) > 0
for field in ["id", "col", "idx", "side"]:
    np.testing.assert_array_equal(pf.orders.values[field], ref_pf.orders.values[field])
for field in ["size", "price", "fees"]:
    np.testing.assert_allclose(pf.orders.values[field], ref_pf.orders.values[field])
np.testing.assert_allclose(pf.value, ref_pf.value)
```

## 4. Add order types and state

`execute_order_nb` fills market orders only. Pending orders and stops are state that the loop stores
and checks on every bar:

* `vbt.pf_nb.check_price_hit_nb(open, high, low, close, price, hit_below=...)` returns the fill
  price, or NaN when the bar does not reach the price. A gap through the price fills at the open.
  `vbt.pf_nb.check_limit_hit_nb` and `vbt.pf_nb.check_stop_hit_nb` first derive the target from an
  initial price and a delta, as in `from_signals`. `vbt.pf_nb.check_td_stop_hit_nb` checks time
  stops.
* Pass the hit price as the order price together with the bar's price area.
* Process several pending orders in the order the price would reach them, such as the nearest level
  first.
* For several positions per asset with separate accounting, keep one account state for each and copy
  the shared cash and free cash into the other states after each order. Give each state its own
  column, for example by tiling the asset columns into a cash-sharing group. Records in one column
  are reconstructed as one position.
* Cash flows that are not orders, such as deposits, financing, or earnings, change `cash` and
  `free_cash` directly. Store them in arrays and pass them to `vbt.PF` as `cash_deposits` or
  `cash_earnings`, otherwise the reconstructed cash differs. Deposits occur before orders and
  earnings after orders in each bar. These flows affect portfolio results, not individual trade P&L.
* For contracts with a multiplier, pass `asset_spec=vbt.pf_enums.AssetSpec(multiplier)` to the
  execution functions and `multiplier` to `vbt.PF`.

This program places three limit buys 1%, 2%, and 3% below the close of an entry bar. They are
eligible on the next 10 bars, then remaining levels expire even if others filled. A partial fill
cancels that level's remainder, while a rejected order stays pending until expiry. It sells
everything 5% above the average entry price. Several levels can fill on one bar. Buy checks take
priority over take profit, which is skipped on a bar with a buy. This is an explicit OHLC ordering
assumption:

```python
import numpy as np
import vectorbtpro as vbt
from numba import njit


@njit
def ladder_nb(open, high, low, close, entries, init_cash, n_levels, step, level_value, tp, expiry):
    n_rows, n_cols = close.shape
    order_records = np.empty((n_rows * n_levels, n_cols), dtype=vbt.pf_enums.order_dt)
    order_counts = np.zeros(n_cols, dtype=np.int_)
    final_state = np.empty((2, n_cols))
    pending = np.empty(n_levels)

    for col in range(n_cols):
        state = vbt.pf_enums.ExecState(init_cash, 0.0, 0.0, 0.0, init_cash, np.nan, np.nan)
        pending[:] = np.nan
        cost = 0.0
        placed_idx = -1

        for i in range(n_rows):
            price_area = vbt.pf_enums.PriceArea(open[i, col], high[i, col], low[i, col], close[i, col])
            if i - placed_idx >= expiry:
                pending[:] = np.nan
            if i > 0 and entries[i - 1, col] and state.position == 0 and np.all(np.isnan(pending)):
                for k in range(n_levels):
                    pending[k] = close[i - 1, col] * (1 - (k + 1) * step)
                placed_idx = i

            bought = False
            for k in range(n_levels):
                hit_price, _, _ = vbt.pf_nb.check_price_hit_nb(
                    open[i, col], high[i, col], low[i, col], close[i, col], pending[k], hit_below=True
                )
                if np.isnan(hit_price):
                    continue
                order = vbt.pf_nb.order_nb(
                    size=level_value,
                    price=hit_price,
                    size_type=vbt.pf_enums.SizeType.Value,
                    direction=vbt.pf_enums.Direction.LongOnly,
                )
                state = vbt.pf_enums.ExecState(
                    state.cash, state.position, state.debt, state.locked_cash, state.free_cash, hit_price, np.nan
                )
                result, state = vbt.pf_nb.process_order_nb(
                    col,
                    col,
                    i,
                    state,
                    order,
                    price_area=price_area,
                    order_records=order_records,
                    order_counts=order_counts,
                )
                if result.status == vbt.pf_enums.OrderStatus.Filled:
                    pending[k] = np.nan
                    cost += result.size * result.price
                    bought = True

            if state.position > 0 and not bought:
                tp_price = cost / state.position * (1 + tp)
                hit_price, _, _ = vbt.pf_nb.check_price_hit_nb(
                    open[i, col], high[i, col], low[i, col], close[i, col], tp_price, hit_below=False
                )
                if not np.isnan(hit_price):
                    result, state = vbt.pf_nb.process_order_nb(
                        col,
                        col,
                        i,
                        state,
                        vbt.pf_nb.close_position_nb(price=hit_price),
                        price_area=price_area,
                        order_records=order_records,
                        order_counts=order_counts,
                    )
                    if result.status == vbt.pf_enums.OrderStatus.Filled:
                        pending[:] = np.nan
                        cost = 0.0

        final_state[0, col] = state.cash
        final_state[1, col] = state.position

    return vbt.nb.repartition_nb(order_records, order_counts), final_state


data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=500, timeframe="1D", seed=42)
entries = data.close.vbt.crossed_above(data.close.rolling(20).mean())
ohlc = [data.open.values, data.high.values, data.low.values, data.close.values]
order_records, final_state = ladder_nb(*ohlc, entries.values, 10_000.0, 3, 0.01, 1_000.0, 0.05, 10)
pf = vbt.PF(
    data.symbol_wrapper, order_records, open=data.open, high=data.high, low=data.low, close=data.close, init_cash=10_000
)
print(pf.orders.records_readable[["Column", "Index", "Size", "Price", "Side"]].head(10))

orders = pf.orders.values
_, fills_per_bar = np.unique(orders[["col", "idx"]], return_counts=True)
assert fills_per_bar.max() > 1
assert (orders["price"] <= data.high.values[orders["idx"], orders["col"]] + 1e-9).all()
assert (orders["price"] >= data.low.values[orders["idx"], orders["col"]] - 1e-9).all()
np.testing.assert_allclose(pf.cash.values[-1], final_state[0])
np.testing.assert_allclose(pf.assets.values[-1], final_state[1])
```

## 5. Wrap and verify

1. Wrap the records with `vbt.PF(wrapper, order_records, close=..., init_cash=...)`. Records do not
   store grouping or anything else that is not an order. Pass the same initial cash, a grouped
   wrapper such as `wrapper.regroup(True)` with `cash_sharing=True` for shared cash, and any cash
   deposits, cash earnings, and multipliers. For initial holdings, also pass `init_position` and
   `init_price`. Pass open, high, and low for analysis and plots. For early termination, return an
   exclusive end index per column and pass it as `sim_end`, or truncate the wrapper and prices for a
   common end. Decide whether to liquidate or mark open holdings to market at that boundary.
2. Compare the loop's final cash and positions with `pf.cash` and `pf.assets` at the last simulated
   bar, as the ladder program does. A difference means that the loop changed balances outside the
   records or that `vbt.PF` received different arguments.
3. Check that each fill's index and price are possible for its bar under the stated timing rule.
4. Rebuild a simple case with a built-in simulator. Compare record identity, order, and side
   exactly, and floating fields and portfolio values within numeric tolerances. Then check missing
   prices, expiry boundaries, rejected and partial fills, and non-unit multipliers on small arrays.
5. Run the verification loop of `vbt-backtesting` on the wrapped portfolio.

## 6. Make it fast

Use `vbt-numba` for debugging, allocation, caching, warm-up, and parallel execution. For simulation:

* Benchmark typical trading activity and the maximum fills per bar, including pending-order checks.
* Parallelize independent groups only. Each worker owns its pending orders, account state, records,
  and outputs. Move the ladder's `pending` allocation inside the column loop before using `prange`.
* For a metrics-only grid, call `execute_order_nb` and compute metrics from the state. For example,
  update returns with `vbt.ret_nb.get_return_nb` and an accumulator from the SuperTrend pipeline
  tutorial below. Match cash-flow adjustments and the simulation horizon, then compare with `vbt.PF`
  on a sample before scaling up.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/documentation/portfolio/simulation/`: execution functions, records, flexible indexing, grouping,
  call sequences, contexts, and performance, built up through six pipelines
* `/tutorials/superfast-supertrend/pipelines/#bonus-own-simulator`: a streaming indicator, order
  execution, and a Sharpe ratio computed in one pass and chunked across a grid
* `/tutorials/portfolio-optimization/dynamic/#bonus-1-own-optimizer`: periodic optimization and
  rebalancing of a cash-sharing group
* `/tutorials/pairs-trading/`: the Engineer level calls `from_signals_nb` and computes metrics in
  Numba
* `/tutorials/from-python-to-rust/static/#numba-kernels`: preparing inputs for `from_signals_nb` and
  wrapping its output
* `/documentation/portfolio/from-signals/#limit-management`: limit order fields and checks to reuse
  in a custom loop
* `vectorbtpro.portfolio.nb.core`: order execution, record, and price hit functions
