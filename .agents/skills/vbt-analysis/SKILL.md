---
name: vbt-analysis
description: "Inspect VectorBT PRO portfolios, trades, positions, drawdowns, and performance metrics. Use when analyzing a backtest, external fills or return series, reconciling metrics, grouping or stacking portfolios, or working with event records. Use vbt-plotting for custom charts."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Analyzing results with VBT

Read `vbt-basics` once for API discovery and shared conventions. Use the sections below that apply
to the requested task.

## Choose the input that answers the question

| Available input | Analysis path |
| --- | --- |
| A completed `vbt.PF` | Inspect its columns and records below |
| Executed fills from another system | [Reconstruct a portfolio](#analyze-external-fills) from the fills and valuation prices |
| A time series of period returns | Use `returns.vbt.returns(freq=..., year_freq=...)` for return metrics and drawdowns |
| Prices or portfolio value without external cash flows | Convert with `vbt.ReturnsAccessor.from_value`, setting `init_value` when the first period has a known starting value |
| Events or periods outside a portfolio | Use [ranges and records](#ranges-mapped-arrays-and-custom-records) |

Return metrics need returns over time. One total profit per asset or trade is not a period-return
series. Confirm whether values are decimal returns, percentages, log returns, prices, or currency
P&L before calculating a ratio. Returns alone do not identify filled orders or round trips.

## 1. Inspect the portfolio

* Print `pf.wrapper.columns` and `pf.wrapper.freq`. Columns carry parameter levels, and annualized
  metrics need the frequency. Check the year frequency as described in `vbt-basics`, and pass
  `year_freq` to the simulation or to the accessor methods that take it.
* Check grouping with `pf.wrapper.grouper.is_grouped()`. A grouped portfolio reports one value per
  group, `pf.wrapper.get_columns()` returns the groups, and `pf[...]` selects groups when group
  selection is enabled. Pass `group_by=False` to a method or to `stats` for one value per column,
  such as `pf.get_sharpe_ratio(group_by=False)`. With cash sharing, `pf.regroup(False)` raises,
  because the columns share one cash balance. Ungrouped asset metrics do not create independently
  funded simulations. Select whole cash-sharing groups for portfolio-level analysis.
* Select one column with `pf["A"]` or `pf[(10, "A")]` before heavy analysis. `pf.stats(column=...)`
  computes every column first and selects afterwards. Iterate with
  `for label, col_pf in pf.items()`, and keep columns by a metric with
  `pf.loc[:, pf.sharpe_ratio > 1]`.
* Select a date range with `pf.loc["2024-03":"2024-06"]`. The range must be contiguous, and its
  starting cash and positions are carried from just before the range. Slicing does not rerun
  decisions with fresh capital, and trades crossing the boundary need that context when interpreted.
  For scattered dates, such as a market regime, index the returns instead, such as
  `pf.returns_acc.loc[mask].stats()`. Metric methods also take `sim_start` and `sim_end`, such as
  `pf.get_sharpe_ratio(sim_start="2023", sim_end="2024")`. They use only the returns in the range,
  which open positions from before it still affect, while `rec_sim_range=True` also restricts the
  value, cash, and orders they depend on.
* `pf.long_view` and `pf.short_view` return portfolios with only the long or short positions, for
  metrics by side. `pf.apply_weights(weights, rescale=True)` reweights the columns of a finished
  portfolio across every series and metric without rerunning it.

## 2. Pick the records that answer the question

| Records | Contents |
| --- | --- |
| `pf.orders` | One record per filled order, with side, size, price, fees, and stop type when recorded |
| `pf.entry_trades` | One record per order that opened or increased a position |
| `pf.exit_trades` | One record per closing or reducing order, plus any remaining open trade |
| `pf.positions` | One record per position, from its first entry to its final exit |
| `pf.drawdowns` | One record per drawdown of the portfolio value |
| `pf.trade_history` | Every order with its entry or exit trade and position, as one DataFrame |

* The three trade views count differently whenever positions are built or reduced in several orders.
  One entry followed by three partial exits is one entry trade, three exit trades, and one position.
  Their unfiltered P&L sums are equal, including open marked-to-market P&L and fees. Filtering
  closed records can break this equality when part of a position remains open. `pf.trades` selects
  the view configured by `pf.trades_type`, which defaults to exit trades.
* Every trade and position view also contains the open one at the end of the data. Filter with
  `status_closed` or `status_open`, and with `winning`, `losing`, `direction_long`, or
  `direction_short`. For any other condition, pass one boolean per record to `apply_mask`, such as
  `trades.apply_mask(trades.returns.values < -0.05)`.
* `records_readable` returns a DataFrame with timestamps and labels. Fields such as `pf.trades.pnl`
  are mapped arrays: `sum()`, `mean()`, and `count()` reduce them per column, `values` returns one
  value per record, and `to_pd()` places each value at the record's exit bar. When several records
  share a bar, `to_pd()` keeps only the last one and warns, so pass `reduce_func_nb="sum"` to add
  them up, `repeat_index=True` to keep all of them, or `ignore_index=True` to stack the values
  without dates.
* Realized P&L per day is the closed trades' P&L summed by day:
  `pf.exit_trades.status_closed.pnl.to_pd(reduce_func_nb="sum").resample("1D").sum()`.
  `pf.asset_pnl` reports each bar's realized and unrealized asset P&L. `pf.total_profit` includes
  the marked value of remaining positions and cash earnings, but excludes external deposits and
  withdrawals. Final value minus initial value includes those external cash flows.
* Records have their own statistics, such as `pf.trades.stats(column="A")` for profit factor,
  expectancy, SQN, streaks, and edge ratio, and `pf.drawdowns.stats(column="A")`. Expectancy is in
  currency per trade. `pf.trades.get_expectancy(use_returns=True)` gives it as a return.
* `pf.trades.mae` and `mfe` give the worst and best price excursion of each trade, with `_returns`
  variants relative to the entry. They and `edge_ratio` use high and low, so simulate with a
  `vbt.Data` instance or pass them. Without them, excursions use the close only.
* For a metric computed over each trade's bars, cut the series per trade with
  `pf.trades.status_closed.get_projections(pf.log_returns, rebase=False)`.

## 3. Compute metrics

`pf.stats()` computes a set of metrics, as one row per column when there are several columns.

* List metric names with `pf.metrics`, then compute a subset:
  `pf.stats(["sharpe_ratio", "max_dd"])`, or select by tag, such as `tags="trades"`.
* `pf.stats()` has few return metrics. `pf.returns_stats()` adds annualized return and volatility,
  Sortino, skew, value at risk, alpha, and beta, and `vbt.ReturnsAccessor.metrics` lists them.
* Add a metric as a tuple of a name and settings. `calc_func` is either an attribute path such as
  `"trades.status_closed.duration.mean"` or a function whose arguments are resolved by name, such as
  `lambda self, group_by: ...`. To receive a portfolio attribute such as `trades`, also set
  `resolve_trades=True`. A function that returns a dict adds one row per key.
* Every metric is also a property or method: `pf.total_return`, `pf.sharpe_ratio`,
  `pf.max_drawdown`, and `pf.returns_acc` for the returns accessor with rolling versions such as
  `rolling_sharpe_ratio`. Use `pf.get_returns_acc(year_freq=..., use_asset_returns=...)` to change
  settings.
* Settings that apply to every metric go into `settings`, such as `trades_type="positions"` to
  compute trade metrics over positions, `incl_open=True`, `use_asset_returns=True`, `risk_free`, and
  `daily_returns=True`, which resamples intraday returns to days before return metrics.
* The benchmark is the close price of each column by default and appears as Benchmark Return. Pass
  `bm_close` to the simulation for another benchmark, such as an index, or `bm_close=False` for
  none. Pass `bm_returns` to `get_returns_acc` or to `settings` to override it afterwards.
* Resample returns to calendar months with `pf.returns_acc.resample_returns("MS")`, which compounds
  the returns within each bin. `pf.resample("1D")` resamples the whole portfolio, for example before
  plotting intraday data.
* For portfolios without shared cash, `pf.stats(group_by=True)` and `pf.regroup(True)` aggregate
  columns by summing their values. This does not rerun orders with a common cash pool. Shared-cash
  portfolios restrict regrouping to preserve their simulated cash pools. Group returns depend on the
  combined capital and cash flows, rather than the sum or unweighted mean of column returns.
* `vbt.PF.column_stack` joins separately simulated portfolios as columns. Pass keys to label them,
  such as `wrapper_kwargs=dict(keys=pd.Index(["s1", "s2"], name="strategy"))`, since duplicate
  columns can conflict, and `group_by="strategy"` for one equity curve per strategy. Cash-sharing
  configurations must match. Other shared settings, such as the year frequency, must be compatible
  or explicitly resolved. Benchmark arrays can differ and are stacked with their columns. Inspect
  index alignment and missing prices when portfolios cover different dates.

`vbt.PF.row_stack` joins consecutive periods. Each later window's initial cash becomes a deposit at
its start, so value jumps while returns account for the flow. `combine_init_cash=True` counts it all
as initial capital, diluting later returns. To carry one account forward, continue from the prior
final state and use `chained=True`, as described in `vbt-backtesting`.

This program scales into one position with three buys and closes it with two sells per symbol. The
different entry-trade, exit-trade, and position counts explain why a report must name its record
type. Explicit order sizes keep the focus on accounting and metrics:

```python
import numpy as np
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=120, timeframe="1D", seed=42)
size = data.symbol_wrapper.fill(np.nan)
size.iloc[[0, 10, 20]] = 1.0
size.iloc[40] = -1.0
size.iloc[60] = -2.0
pf = vbt.PF.from_orders(
    data,
    size=size,
    size_type="amount",
    fees=0.001,
    init_cash=10_000,
    year_freq="365 days",
    price="open",
)

assert (pf.entry_trades.count() == 3).all()
assert (pf.exit_trades.count() == 2).all()
assert (pf.positions.status_closed.count() == 1).all()
closed = pf.trades.status_closed
print(closed.records_readable[["Column", "Entry Index", "Exit Index", "PnL", "Return"]])
print(closed.pnl.sum())
np.testing.assert_allclose(pf.entry_trades.pnl.sum(), pf.exit_trades.pnl.sum())
np.testing.assert_allclose(pf.positions.pnl.sum(), pf.total_profit)
print(closed.apply_mask(closed.returns.values < -0.03).count())

avg_hold = dict(
    title="Avg Hold",
    calc_func="trades.status_closed.duration.mean",
    apply_to_timedelta=True,
)
metrics = ["total_return", "bm_return", "max_dd", "sharpe_ratio", "win_rate"]
metrics.append(("avg_hold", avg_hold))
print(pf.stats(metrics))
print(pf.stats(["total_trades", "win_rate"], settings=dict(trades_type="positions")))
print(pf.stats(["start_value", "end_value", "total_return"], group_by=True))
print(pf["A"].returns_acc.resample_returns("MS"))
```

For leveraged portfolios, reconstructing free cash from orders alone can differ from simulation. Use
`save_state=True` when building the portfolio to retain its actual `pf.free_cash` series. The
`vbt-backtesting` skill covers cash, debt, and execution assumptions.

## 4. Plot one column at a time

`pf.plot()` accepts a single column only. Select it first, or pass `column=...`, and choose subplots
from `pf.subplots`:

```python
fig = pf["A"].plot(subplots=["orders", "trade_pnl", "cumulative_returns", "underwater"])
```

* Add a custom panel as a tuple, such as `("rsi", dict(title="RSI", plot_func=plot_rsi, rsi=rsi))`,
  where `plot_rsi(self, rsi, add_trace_kwargs=None, fig=None)` draws into the panel it is given.
  Arguments are resolved by name, like those of custom metrics. Hide the benchmark with
  `settings=dict(bm_returns=False)`.
* `pf.plot(per_column=True)` overlays every column on one figure. Records plot themselves too, such
  as `pf.trades["A"].plot()`, `pf.trades.plot_mae_returns(column="A")`, and
  `pf.drawdowns["A"].plot()`. Any series plots with `.vbt.plot()`, such as `pf.value.vbt.plot()`.
* Use `vbt-plotting` for custom subplots, overlays, heatmaps, styling, large figures, and exporting
  without a display.

## 5. Report

Report the columns analyzed, the frequency and year frequency, the benchmark and risk-free rate,
whether open trades were included, and the metrics with their units. Name the records a trade count
came from.

## Analyze external fills

Construct `vbt.PF(close, order_records=fills, ...)` when executions have already happened. The
constructor trusts supplied fills and reconstructs accounting from them. It does not run sizing,
slippage, or rejection rules again. Use `vbt-backtesting` when those outcomes must be simulated.

Map each fill to the correct symbol and bar in the price wrapper. Preserve separate fills when
several occur on one bar, and supply actual sizes, prices, fees, starting cash, initial holdings,
and external cash flows where applicable. Check timestamp zones and distinguish a fill time from a
signal time. Missing execution history cannot be recovered from closing prices.

This two-fill example checks fees, realized profit, and the value between fills:

```python
import numpy as np
import pandas as pd
import vectorbtpro as vbt

close = pd.Series([100.0, 105.0, 110.0], index=pd.date_range("2024-01-01", periods=3, freq="D"))
fills = [
    dict(idx=0, size=2, price=100, fees=1, side="Buy"),
    dict(idx=2, size=2, price=110, fees=1, side="Sell"),
]
pf = vbt.PF(close, order_records=fills, init_cash=1000, freq="1D")
np.testing.assert_allclose(pf.value, [999, 1009, 1018])
np.testing.assert_allclose(pf.total_profit, 18)
np.testing.assert_allclose(pf.exit_trades.status_closed.pnl.sum(), 18)
assert pf.orders.count() == 2
print(pf.trade_history)
```

Reconcile cash, positions, and a few fills against the source system before comparing summary
metrics. Then use the same record and metric workflow as for a simulated portfolio. The constructor
and `vectorbtpro.records.base.Records.resolve_records_arr` document accepted record formats.

## Ranges, mapped arrays, and custom records

Records describe events without a portfolio, such as the periods where a condition holds. They store
one row per event with its column and bars, and map fields to one value per event.

* `mask.vbt.ranges` turns every run of `True` into a range, and does the same for runs of valid
  values in a float array. There is no `Ranges.from_mask`, and `vbt.Ranges.from_array` builds the
  same records with options. Signal masks also give `partition_ranges`, `between_ranges`, and
  `delta_ranges`, as described in `vbt-signals`.
* For ranges created from a mask, `end_idx` is the first bar after a range, except for a range still
  open at the end of the data, which ends at the last bar and has the status open. Filter with
  `status_closed`, `filter_min_duration(10)`, or `apply_mask`, and mark the first or last bar of
  each range with `first_pd_mask` or `last_pd_mask`. `stats()` reports coverage and duration
  quantiles.
* Fields such as `ranges.duration` are mapped arrays. They reduce per column with `mean`, `max`,
  `describe`, and `value_counts`. `top_n` selects records with the largest values, and `to_pd`
  places mapped values at their associated bars. `records.map_array(arr)` wraps an array with one
  value per record, such as the return over each range, so it reduces the same way.
* For events that no built-in class describes, define a structured dtype with `id`, `col`, and `idx`
  fields and subclass `vbt.Records` with `override_field_config` and `attach_fields` from
  `vectorbtpro.records.decorators`. Like built-in records, sort them by column and then by bar,
  which takes the faster code path, and number them from 0 within each column. The instance needs
  the wrapper of the array its indices refer to, such as `close.vbt.wrapper`. Pass the configuration
  to the decorator, or define `_field_config` in the class body and apply the bare
  `@override_field_config`. Both merge it with the configuration of the base class.

Run this program to see ranges, a mapped array, and a custom record class:

```python
import numpy as np
import vectorbtpro as vbt
from vectorbtpro.records.decorators import attach_fields, override_field_config

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=300, timeframe="1D", seed=42)
close = data.close
above = close.vbt > close.vbt.rolling_mean(20)

ranges = above.vbt.ranges
print(ranges.records_readable.head(3))
print(ranges.status_closed.duration.describe())

start = ranges.get_field_arr("start_idx")
last = ranges.last_idx.values
col = ranges.get_field_arr("col")
range_return = ranges.map_array(close.values[last, col] / close.values[start, col] - 1)
print(range_return.mean())

move_dt = np.dtype([("id", np.int64), ("col", np.int64), ("idx", np.int64), ("move", np.float64)])


@attach_fields
@override_field_config(dict(dtype=move_dt, settings=dict(move=dict(title="Move"))))
class Moves(vbt.Records):
    pass


returns = close.pct_change().values
rows, cols = np.nonzero(np.abs(np.nan_to_num(returns)) > 0.02)
order = np.lexsort((rows, cols))
records = np.empty(len(order), dtype=move_dt)
records["col"], records["idx"] = cols[order], rows[order]
records["id"] = np.concatenate([np.arange(n) for n in np.bincount(cols, minlength=close.shape[1])])
records["move"] = returns[rows[order], cols[order]]
moves = Moves(close.vbt.wrapper, records)
print(moves.records_readable)
print(moves.count(), moves.move.mean())
np.testing.assert_array_equal(moves.count().values, np.bincount(cols, minlength=close.shape[1]))
np.testing.assert_allclose(moves.move.values, returns[rows[order], cols[order]])
```

## Pitfalls

* Trade metrics of `pf.stats()` such as Win Rate count closed trades only, while records such as
  `pf.trades.win_rate` count every trade they hold. Filter records with `status_closed`, or pass
  `settings=dict(incl_open=True)` to `stats`. Total Trades explicitly includes open trades by
  default, so its count is not necessarily the denominator of the displayed Win Rate.
* When a user counts round trips, use closed `pf.positions`, or select the positions view with
  `settings=dict(trades_type="positions")` in `stats`. Check each metric's open-trade setting.
* `pf.trade_history` annotates opening and closing orders with their respective trade-view P&L.
  Summing that column mixes views and can double-count realized P&L. Entry annotations can also
  include open P&L. Sum one trade view instead.
* Returns are computed on the whole portfolio value, including cash that is not invested, so a
  strategy that invests 10% of its cash shows about a tenth of its asset return, volatility, and
  drawdown in a simple unlevered case. Sharpe is unchanged only under constant positive scaling with
  compatible risk-free assumptions. Changing exposure over time can change it. Pass
  `use_asset_returns=True` to `returns_stats` or `get_returns_acc`, or in `settings` to `stats`, to
  measure returns on the invested capital. Total Return and Max Drawdown in `stats` do not change.
* `risk_free` and `required_return` are annual rates, such as `risk_free=0.04`, deannualized with
  the annualization factor before they are subtracted from every return. Both default to zero. Older
  versions took them per bar, except `required_return` in Omega. If the docstring of
  `vbt.ReturnsAccessor.sharpe_ratio` does not call `risk_free` annual, convert an annual rate with
  `pf.returns_acc.deannualize(0.04)`.
* Max Drawdown includes a drawdown that is still active at the end of the data, and so does Max
  Drawdown Duration. Filter `pf.drawdowns.status_recovered` to measure recovered drawdowns only.
  `pf.drawdowns.stats()` leaves active drawdowns out of its summaries unless
  `settings=dict(incl_active=True)`. `pf.drawdown` is the series of the current percentage below the
  peak, while `pf.drawdowns` holds the records.
* Average drawdown has two meanings: `pf.drawdowns.avg_drawdown` averages the depth of the records,
  so many shallow ones dominate, while `pf.drawdown.mean()` averages over time. Name the one you
  report. Depths are relative to the peak value including idle cash, so
  `(dd.start_val - dd.valley_val).max()` gives the largest fall in currency. When value falls below
  zero through leverage or shorts, drawdowns exceed 100%.
* Resampling puts each bin under its start label, so `"ME"` puts each month end into the next
  month's bin. Use `"MS"` for calendar months and `"YS"` for calendar years. `returns_acc.annual()`
  cuts bins of the year frequency from the first bar, which are not calendar years.
* Annualized metrics extrapolate. A backtest of a few weeks produces extreme annualized returns and
  ratios, so report the period next to them. Durations count bars times the frequency, not the
  calendar time between the first and last bar.
* The Sharpe ratio is the mean excess bar return divided by its standard deviation, times the square
  root of the bars per year, not annualized return over annualized volatility. For a risk-free rate
  that changes over time, subtract an aligned series of per-bar rates from the returns and pass
  `risk_free=0`. Bars without a position keep their zero returns, since waiting in cash is part of
  the strategy. Set them to NaN only to measure the time in the market.
* The Sharpe ratio is NaN for all-zero returns with zero risk-free rate. Order or trade count alone
  does not establish this: initial holdings or cash earnings can produce returns without new trades.
* QuantStats, through `pf.qs` or `pf.returns_acc.qs`, receives the VBT annualization factor and
  `risk_free`, so comparable metrics can use consistent annualization. This does not guarantee every
  metric matches: compare `pf.qs.sharpe()` with `pf.sharpe_ratio` on identical returns and settings.
  QuantStats must be installed separately.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/features/backtesting/orders-and-execution/#portfolio-from-fills`: constructing a portfolio from
  execution records
* `/api/portfolio/trades/`: how entry trades, exit trades, and positions are built from orders
* `/api/portfolio/base/`: stats, custom metrics, returns stats, and plots of a portfolio
* `/cookbook/portfolio/#metrics`: year frequency, invalid returns, and metrics in Numba
* `/api/generic/stats_builder/`: every setting of `stats`, including custom metrics and tags
* `/features/analytics/trade-analytics/`: MAE, MFE, edge ratio, and trade signals
* `/cookbook/plotting/`: subplots, layouts, themes, and exporting figures
* `/api/generic/ranges/`: building, filtering, projecting, and plotting ranges
* `/api/records/base/` and `/api/records/mapped_array/`: mapping, reducing, and extending records
