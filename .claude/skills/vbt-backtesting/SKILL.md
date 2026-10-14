---
name: vbt-backtesting
description: "Simulate trading strategies with VectorBT PRO, including sizing, costs, execution timing, stops, limits, leverage, and cash sharing. Use when building a backtest, debugging orders and fills, updating an incremental simulation, or resuming saved simulation state. Use vbt-analysis for an existing portfolio and vbt-callbacks for decisions based on simulation state."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Backtesting with VBT

Read `vbt-basics` once for API discovery and shared conventions. Use the numbered steps for a new
simulation. For an existing discrepancy, start with [verification](#5-verify-on-synthetic-data) and
the [execution reference](#execution-reference).

## 1. Check the environment

Use the environment and API checks in `vbt-basics`. Read the installed signature or source for
arguments that are new to the task. Arguments of open-source vectorbt, such as `sl_trail`,
`stop_exit_price="stoplimit"`, or `lock_cash`, do not exist here. Trailing stops use `tsl_stop`, and
stop-limit orders use `stop_order_type="limit"` with `stop_limit_delta`. Defaults are not in the
signature: read the ones specific to signals from `vbt.settings.portfolio["from_signals"]` and
shared ones such as `vbt.settings.portfolio["price"]` from the parent section.

## 2. Choose the simulation method

| The strategy is expressed as | Use |
| --- | --- |
| Entry and exit signals, with optional stops and limit orders | `vbt.PF.from_signals` (default) |
| Target sizes or weights per bar, without signals | `vbt.PF.from_orders`, or `from_signals` with `order_mode=True` when stops are needed |
| Weights from a portfolio optimizer | `vbt.PF.from_optimizer` |
| Signals whose decision depends on the simulation state (position, cash, last order) | `from_signals` with `signal_func_nb` |
| Logic that is not signal-shaped, such as custom rebalancing across assets | `vbt.PF.from_order_func` |
| Several orders per column and bar, including custom pending-order logic | `vbt.PF.from_order_func` with `flex_order_func_nb`, see `vbt-callbacks` |
| A buy-and-hold benchmark | `vbt.PF.from_holding` |
| Direct control of account state and execution, or reducing measured simulator overhead | Your own Numba loop, see `vbt-custom-simulators` |

The rows with `signal_func_nb` and `from_order_func` need Numba callbacks. Read the `vbt-callbacks`
skill before writing one.

## 3. Prepare data and signals

* Pass a `vbt.Data` instance as the first argument. It supplies open, high, and low, which fills and
  stops need. When passing a DataFrame of closes instead, also pass `open`, `high`, and `low`,
  otherwise the simulator cannot reconstruct the bar's actual price range, and stop outcomes can
  differ.
* Decide the direction. `from_signals` trades long only by default, so `exits` only close longs. For
  shorts, pass `short_entries` and `short_exits` alongside `entries` and `exits`. Avoid
  `direction="both"` with `entries` and `exits`: it turns `exits` into short entries, so an exit can
  open or reverse into a short under the default conflict rules.
* Decide when a signal can be executed. By default an order fills at the close of the signal bar
  (`price="close"`). That is only realistic when the signal uses information available before that
  close. Otherwise, use `price="nextopen"`, or shift the signals with `vbt.SignalsAccessor.fshift`
  and use `price="open"`. Never shift OHLC, only signals and arguments linked to them. A limit
  placed at the close fills from the next bar. Treating it as filled because the same bar's low
  touched it uses a low that happened before the signal existed.
* Rows without a price place no order, including exits. With `price="nextopen"`, a signal before an
  empty weekend or holiday row never fills, so drop rows where the market is closed. For a
  point-in-time universe, mask prices outside each symbol's membership with NaN and exit on its last
  priced bar.
* Give indicators their warm-up history with `sim_start` and `sim_end` instead of slicing the data.
  The simulation starts flat at `sim_start`, while signals use the full history. `sim_start="auto"`
  starts each column at its first signal.
* For a list of events or fills, pass a DataFrame or list of dicts as `records`, with `date` or
  `row`, `symbol` or `col`, and argument columns such as `size`, `price`, or `long_entry`. A
  timestamp inside a bar maps to the next bar, so floor intraday times to bar starts first. A later
  record for the same symbol and bar overwrites an earlier one.
* Make sure the index has a frequency and choose the year frequency, as described in `vbt-basics`.
  Annualized metrics such as the Sharpe ratio depend on both. Pass `freq` and `year_freq` to
  `from_signals` when needed.
* Check the signal code for look-ahead: compute the signals on all rows and on the first half of the
  rows, and confirm that the shared rows are identical. A difference can reveal future data use,
  such as a negative shift or a whole-sample statistic. First keep seeds, settings, and alignment
  identical. Agreement on one cut is useful evidence, but does not prove the absence of look-ahead.

## 4. Build the simulation call

Start from this program and change one thing at a time:

```python
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=500, timeframe="1D", seed=42)
rsi = vbt.RSI.run(data.close, window=14).rsi
entries = rsi.vbt.crossed_below(30)
exits = rsi.vbt.crossed_above(70)

pf = vbt.PF.from_signals(
    data,
    entries=entries,
    exits=exits,
    price="nextopen",
    fees=0.001,
    slippage=0.0005,
    sl_stop=0.05,
    stop_entry_price="price",
    td_stop="30 days",
    init_cash=10_000,
)
orders = pf.orders.values
assert len(orders) > 0
assert (orders["idx"] > orders["signal_idx"]).all()
assert (orders["size"] > 0).all()
print(pf.orders.records_readable[["Column", "Signal Index", "Fill Index", "Side", "Price", "Stop Type"]])
print(pf.stats()[["Total Return [%]", "Max Drawdown [%]", "Total Trades"]])
```

Indicator outputs carry parameter levels, so the columns above are `(14, "A")` and `(14, "B")`.
Select a column with the full tuple, for example `pf.stats(column=(14, "B"))`.

Pass `return_prep_result=True` to receive the prepared, broadcast arguments instead of a portfolio.
Inspect or change them with `replace(..., nested_=True)` and pass the result back to `from_signals`.

Before changing the example, choose the position size and capital pool, the handling of repeated or
conflicting signals, and the trigger and fill assumptions for stops. The
[execution reference](#execution-reference) groups these choices and their arguments.

## 5. Verify on synthetic data

For a new strategy or a change to execution logic, run a small reproducible simulation. Use
synthetic data for general checks and the supplied inputs for a reported discrepancy. For custom
compiled code, follow the JIT checks in `vbt-basics`:

1. Run the simulation with `log=True` and print `pf.orders.records_readable`. Check that orders
   exist, that sides match the signals, that sizes match the requested size, and that fill prices
   follow the chosen price, slippage, and price-area rules. For a missing or smaller order, find the
   reason in the status columns of `pf.logs.readable`. Logs describe attempted orders. If signal
   conflicts suppress an order before execution, inspect the masks and conflict rules too.
2. Check `pf.stats()` for signs of a broken setup: zero trades, trades on every bar, a win rate of
   100% with many trades, or returns that look too good.
3. Compare a few trades against the signals by hand. For each surprise, check the execution
   reference below and fix the cause, not the symptom.
4. Repeat the look-ahead check from step 3 after every change to the signal code.

Resolve unexpected differences before scaling the simulation. A check that cannot run is a
limitation to report, not a passed check.

## 6. Run on real data and report

Report the call you ran, the key statistics, the number of trades, and any assumption you made about
execution price, fees, slippage, and the year frequency. Say which checks from step 5 passed. For
trade lists, custom metrics, or charts, read the `vbt-analysis` skill.

## Execution reference

Arguments by concern. Enum-typed arguments accept field names as lowercase strings, such as
`size_type="valuepercent100"`.

| Concern | Arguments | Enum |
| --- | --- | --- |
| Direction | `direction`, or `long_entries`, `long_exits`, `short_entries`, `short_exits` | `vbt.pf_enums.Direction` |
| Size | `size`, `size_type`, `size_granularity`, `min_size`, `max_size` | `vbt.pf_enums.SizeType` |
| Repeated signals | `accumulate` | `vbt.pf_enums.AccumulationMode` |
| Conflicting signals | `upon_long_conflict`, `upon_short_conflict`, `upon_dir_conflict`, `upon_opposite_entry` | `vbt.pf_enums.ConflictMode`, `vbt.pf_enums.OppositeEntryMode` |
| Execution | `price`, `fees`, `fixed_fees`, `slippage` | `vbt.pf_enums.PriceType` |
| Stops | `sl_stop`, `tsl_stop`, `tsl_th`, `tp_stop`, `delta_format`, `stop_entry_price`, `stop_exit_price`, `stop_exit_type`, `stop_order_type` | `vbt.pf_enums.StopEntryPrice`, `vbt.pf_enums.StopExitPrice`, `vbt.pf_enums.DeltaFormat` |
| Time stops | `td_stop`, `dt_stop`, `time_delta_format` | `vbt.pf_enums.TimeDeltaFormat` |
| Limit orders | `order_type="limit"`, `limit_delta`, `limit_tif`, `limit_expiry`, `limit_reverse`, `limit_delay`, `limit_order_price`, `upon_adj_limit_conflict`, `upon_opp_limit_conflict` | `vbt.pf_enums.OrderType` |
| Capital | `init_cash`, `init_position`, `init_price`, `allow_partial`, `leverage`, `leverage_mode`, `cash_sharing`, `group_by`, `multiplier` | `vbt.pf_enums.LeverageMode` |
| Cash flows | `cash_deposits`, `cash_dividends`, `cash_earnings` | |
| Diagnostics | `log`, `price_area_vio_mode` | `vbt.pf_enums.PriceAreaVioMode` |

Price-stop deltas default to fractions of the stop reference price, so `sl_stop=0.05` is 5%. Pass
`delta_format="absolute"` for price distances or `"target"` for stop prices. Size a position as a
share of equity with `size_type="valuepercent"`, where `size=0.1` is 10%. The current default
`stop_entry_price="price"` anchors stops to the order price before slippage. Use `"fillprice"` to
include slippage or `"close"` to anchor them to the entry bar's close. Choose explicitly when timing
matters.

Broadcastable order and signal arguments accept arrays: pass a scalar, a Series per row, a DataFrame
per row and column, or wrap values in `vbt.Param` to test each of them as a separate column:

```python
pf = vbt.PF.from_signals(data, entries=entries, exits=exits, price="nextopen", sl_stop=vbt.Param([0.03, 0.05, 0.1]))
```

A price array may use `-np.inf` for the bar's open and `np.inf` for its close. Start it from the
close and overwrite the signal bars, because a NaN price places no order. Prices outside the bar's
low-to-high range are accepted by default. Pass `price_area_vio_mode="error"` to catch fills the bar
could not have produced, or `"cap"` to clip them, such as after slippage.

To give an argument different values for different signal types, build an array and use the signals
as masks:

```python
sl_stop = data.symbol_wrapper.fill()
sl_stop[long_entries] = 0.05
sl_stop[short_entries] = 0.02
```

### Size and capital

* `from_signals` rejects target size types such as `"targetpercent"`, since a target can contradict
  the signal. Use `"valuepercent"` for a share of equity, `from_orders` for target weights, or
  `order_mode=True`. `"percent"` is a share of available cash for entries and of the position for
  exits, so under shared cash each buy leaves less for the next asset, while `"valuepercent"` refers
  to the group's value.
* In `from_orders`, a NaN size places no order and keeps the position, and `np.inf` buys with all
  available cash. `-np.inf` closes a long with `direction="longonly"`, but with the default
  `direction="both"` it can open or reverse into a short. Use `size=0, size_type="targetamount"` to
  close either side. Target weights are fractions of the group's value. Without leverage, weights
  that sum above 1 fill the first columns and starve the last ones.
* `size_granularity` rounds every order down, including closing orders, so a fractional position
  from earlier orders may not close completely. `min_size` and `max_size` follow `size_type`.
* The default `init_cash` is 100. With `cash_sharing=True`, it is the balance of each group.
  `init_cash="auto"` finds the cash the orders need, and `"autoalign"` gives every column the
  largest requirement. Both reject sizes relative to cash or value. Simulate those with real cash
  and call `pf.replace(init_cash="auto")` afterwards. `init_position` and `init_price` start from
  existing holdings. Partial fills are allowed, so a fixed `size` larger than the cash allows is
  reduced, with PartialFill in the log. Pass `allow_partial=False` to reject such orders.
* When sharing cash, the default all-in size can let the first order consume all available cash. Use
  finite amounts or equity fractions, and choose the call sequence deliberately. Automatic sorting
  uses estimated order values and does not guarantee that every requested allocation fills.
* `leverage` scales the position only when the size is limited by cash, as with the default all-in
  `size`. A finite size such as `size=5` with `size_type="amount"` stays 5 units, and leverage only
  sets how much of it may be borrowed. `leverage_mode="lazymult"` or `"eagermult"` multiplies the
  size by the leverage. Check `pf.orders.records_readable` before scaling `size` yourself, or
  exposure is scaled twice.
* Leverage borrows only once own cash runs out by default, while `leverage_mode="eager"` borrows on
  every order. Fees are paid from own cash. There is no automatic liquidation or simulation halt
  when equity reaches zero. Equity-relative size types reject orders at nonpositive equity, but
  other orders, including exits, can still fill. Stop a group early with
  `vbt.pf_nb.stop_group_sim_nb` in a callback if needed. Charge borrowing costs or funding as
  negative `cash_earnings` from a callback, which is limited to free cash.
* `multiplier` scales order values, cash flows, and profit for futures, such as `multiplier=50` for
  E-mini S&P 500 contracts. Prices can be zero or negative. Rolls and daily variation margin are not
  modeled, so back-adjust the series or roll with your own signals. Convert prices of other
  currencies to the account currency before simulating.
* `cash_dividends` takes dividends per share and multiplies them by the position. Use unadjusted
  prices with it, such as `vbt.YFData` with `auto_adjust=False`, because adjusted prices already
  include dividends. `cash_deposits` adds cash, and negative values withdraw up to the free cash.
  Deposits count as invested capital, so they do not raise returns. Flows that depend on the
  account, such as management fees or taxes, go into `cash_earnings` from a callback.
* `cash` is not the money available. A short adds its sale proceeds to `cash`, and a leveraged long
  can make it negative. Use `free_cash` for available funds under the simulator's collateral rules,
  and `value` for equity. With leverage, pass `save_state=True` and inspect the saved
  `pf.free_cash`: reconstruction from orders alone assumes unleveraged free-cash accounting.

### Repeated and conflicting signals

* With accumulation disabled, further entries in the same direction are ignored while that position
  is open. Enable accumulation to add on repeated entries, subject to sizing and cash limits.
* An entry and an exit on the same bar cancel each other by default. Choose a winner with
  `upon_long_conflict` or `upon_short_conflict`.
* With accumulation disabled, the default opposite-entry rule reverses the position in one order.
  Its size includes the old position plus the new one, so it is double only when both are equal.
  Accumulation can instead reduce the position. Use `upon_opposite_entry="close"` to only close.
* With `accumulate=True`, an exit reduces the position by `size` instead of closing it. With a small
  size, one exit may leave a position open, though repeated exits can finish closing it.
  `accumulate="addonly"` scales in while each exit closes the whole position, and `"removeonly"`
  scales out of a single entry, such as two exits of `size=0.5` and `1.0` with
  `size_type="percent"`.
* A reversal is one order for both legs, so they share a price and an order type, and a `max_size`
  below both legs together turns it into a plain exit. To close at market and reopen with a limit,
  exit on one bar and enter on the next.

### Limit orders

* With `order_type="limit"`, the limit price is `price` moved by `limit_delta`, and the order is
  checked against the high and low of later bars. `limit_reverse=True` flips the trigger side, which
  makes a stop-entry order for breakouts. `limit_tif` and `limit_expiry` end it, and
  `limit_delay=True` keeps it from filling on its creation bar.
* After a gap through the level, the default `limit_order_price="autolimit"` fills an ordinary limit
  at its limit price and a stop-entry at the open. `"limit"` lets an ordinary limit take the better
  open. Slippage does not apply to limit fills.
* Each column keeps one pending limit. A new signal in the same direction is ignored while it waits,
  unless `upon_adj_limit_conflict="cancelexecute"` re-quotes it. An opposite signal cancels it and
  executes. The size is resolved when the order fills, not when it is placed.
* Several resting orders at once, such as grids, need a callback or a custom simulator.

### Stops and intrabar execution

* On a datetime index, `td_stop` counts time, so pass a timedelta such as `td_stop="5 days"`, or
  count bars with `time_delta_format="rows"`. A bare number means nanoseconds and warns.
* `from_signals` permits one order per column and bar. A stop initialized by an entry cannot then
  execute a second order on that bar. Use finer bars or a flexible order function when the strategy
  needs multiple fills, and state the assumed intrabar price path.
* Stops are checked from the bar after the entry, even when the entry fills at the open. Within a
  bar, the open, the range between open and close, and the close are processed in order. When a stop
  loss and a take profit fall in the same part, the stop loss wins, and a trailing stop is checked
  before the bar's new high can raise it. Test tight stops on finer bars.
* Stop values are read when a position opens and stay fixed, so an ATR series sets the distance at
  entry but does not trail the current ATR. Change an active stop from `adjust_func_nb` through
  `c.last_sl_info`, as described in `vbt-callbacks`. When an entry adds to a position,
  `upon_stop_update` decides whether the stop is replaced, which it is by default. When one stop
  closes the position, the others are cleared.
* `tsl_th` delays the trailing stop until the price has moved by that threshold, which makes it a
  trailing take profit. `stop_ladder="uniform"` or `"weighted"` with a list of stop values scales
  out at each level. `stop_exit_type="reverse"` reverses the position when a stop fires.
* Time stops count from the open of the entry bar and fill at the open of the bar where they expire.
  `dt_stop` takes a date, a period such as `"M"`, or a time of day such as `"16:00"`.
* `stop_exit_price="stop"` fills at the open when the bar gaps through the stop. Use `"hardstop"` to
  request the exact stop threshold even through a gap. Slippage and price-area rules still apply,
  and a threshold outside the observed range may be an unrealistic fill assumption.
* Stop detection uses the supplied OHLC prices. `stop_exit_price="close"` chooses the fill price
  after a stop has triggered. It does not make the trigger close-only. For a rule evaluated only at
  the close, express that decision as an exit signal or callback and verify its execution timing.

## Continue a simulation

Use this path to extend a historical simulation as bars arrive:

1. Create the original portfolio with `attach_preparer=True`. Keep the source data and any custom
   callback memory alongside it.
2. Update the data as described in `vbt-data`. Separate newly available completed bars from revised
   historical bars. A revision needs an explicit replay policy because continuing from the current
   state does not repair earlier decisions.
3. Recompute causal indicators on the available history, or advance their accumulators with the
   retained state. Slice the new rows and matching signal, size, and stop arrays only after their
   required history has been included.
4. Assign `pf = pf.update(new_data, entries=new_entries, exits=new_exits, ...)`. This returns the
   old and new results stacked by default. For a long loop, `stack=False` returns only the new
   segment, avoiding repeated copies of the growing history. Keep that segment as the cursor for the
   next update and store completed segments separately.
5. Compare a small split run with one uninterrupted run, including orders and final state. Include a
   boundary with an open position and a delayed signal. Carry custom callback memory explicitly as
   described in `vbt-callbacks`.

To resume after a restart, save a portfolio built with `attach_preparer=True` with `pf.save(path)`
and restore it with `vbt.PF.load(path)`. To change parameters or retrain between periods, pass
`last_state=pf.last_state` to the next simulation and join the segments with
`vbt.PF.row_stack(*pfs, chained=True)`. `pf.last_state` also holds pending stops and limits, such as
`last_tsl_info`, and `vbt.pf_nb.get_tsl_info_target_price_nb(tsl_info, position)` returns the
trailing stop level to mirror at a broker. `vbt.wait("1h", floor=True)` sleeps until the next bar
boundary in a polling loop.

A signal delayed beyond the last row is not automatically a pending market order in the final state.
Carry the signal and argument history needed by `from_ago` or next-bar execution across the
boundary. `pf.orders` contains simulated fills, so it cannot list a next-open market fill before
that next bar exists. Keep prospective decisions separate when integrating with an external
execution system.

The complete polling and replay recipe is in `/tutorials/from-python-to-rust/live/`, especially
`#continuation-state`, `#high-level-vbt`, and `#live-data`. Use
`vectorbtpro.portfolio.base.Portfolio.update` for the installed contract.

## Documentation

Read these pages with `get_page` when the task goes beyond the steps above:

* `/documentation/portfolio/from-signals/`: mechanics, conflicts, orders, and stops
* `/documentation/portfolio/from-orders/` and `/documentation/portfolio/simulation/`: simulation
  without signals and how cash, debt, and free cash are accounted. Writing your own simulator is
  covered by `vbt-custom-simulators`
* `/tutorials/from-python-to-rust/live/`: data updates, input history, callback memory, and
  continuation checked against a full run
* `/tutorials/stop-signals/`: comparing stop types and their parameters at scale
* `/cookbook/portfolio/`: short recipes for common requests
