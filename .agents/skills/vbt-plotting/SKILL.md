---
name: vbt-plotting
description: "Create, combine, customize, and export VectorBT PRO and Plotly charts. Use when plotting prices, indicators, signals, or parameter grids, building subplots, or fixing rendering and performance problems. Use vbt-analysis for portfolio metrics and built-in portfolio subplots."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Plotting with VBT

VBT uses Plotly figures, usually `vbt.Figure`, with widget and resampler variants controlled by
settings. Most high-level plotting methods return a figure and accept `fig=` to draw into an
existing one. Check the method when it returns a plotting wrapper instead.

Read `vbt-basics` once for API discovery and shared conventions. Use steps 1 to 4 to build a figure.
If a figure already exists but fails to display or export, go straight to
[save and check](#5-save-and-check).

## 1. Select one column

Most object plots show one column. `data.plot()` on several symbols raises "Cannot plot OHLC of
multiple symbols", and indicators, records, and portfolios raise "Only one column is allowed".
Select first, such as `data.select("A")`, `data.plot(symbol="A")`, `rsi.plot(column=(14, "A"))`, or
`pf["A"]`. Array accessors are the exception: `df.vbt.plot()` draws one trace per column, so compare
symbols or parameter values there, such as `pf.value.vbt.plot()`.

* To show several columns of an object, loop over `obj.wrapper.columns` and pass the same `fig` to
  each call, or give each column its own subplot as in section 3.
* `data.plots()` draws one candlestick subplot per symbol.

## 2. Pick the method

| What | Method |
| --- | --- |
| OHLC candles with volume | `data.plot()`, or `df.vbt.ohlcv.plot()` on a DataFrame with OHLCV columns |
| One feature for all symbols, rebased to compare | `data.plot(feature="Close", base=1)` |
| An indicator with its inputs | `ind.plot()`, such as `vbt.BBANDS.run(close).plot()` |
| Lines of any Series or DataFrame | `df.vbt.plot()`, `df.vbt.lineplot()`, `df.vbt.scatterplot()` |
| Distributions and comparisons | `df.vbt.histplot()`, `df.vbt.boxplot()`, `df.vbt.barplot()`, `df.vbt.areaplot()`, `sr.vbt.qqplot()` |
| Entries and exits over a price | `entries.vbt.signals.plot_as_entries(close)`, `exits.vbt.signals.plot_as_exits(close)` |
| Periods where a mask is True as shaded zones | `mask.vbt.signals.ranges.plot_shapes(plot_close=False, fig=fig)` |
| A line over a heatmap of another series, such as regimes | `close.vbt.overlay_with_heatmap(labels)` |
| One series against another, with the area between shaded | `sr.vbt.plot_against(other)` |
| A metric over two parameters | `sr.vbt.heatmap(x_level=..., y_level=...)`, with `slider_level` for a third |
| A metric over three parameters | `sr.vbt.volume(x_level=..., y_level=..., z_level=...)` |
| Columns over time as colors, such as masks of many parameter values | `df.vbt.ts_heatmap()` |
| Orders, trades, drawdowns, and ranges | `pf.trades["A"].plot()`, `pf.drawdowns["A"].plot()`, `ranges.plot()` |
| Plotly Express charts | `df.vbt.px.ecdf()`, `df.vbt.px.scatter(x="a", y="b")`, and other Plotly Express functions |

* Indicators plot their main outputs, and each output and input has its own argument, such as
  `upper_trace_kwargs` and `close_trace_kwargs`. Hide one with
  `close_trace_kwargs=dict(visible=False)`, or skip the price with `plot_close=False` when it is
  already on the figure. TA-Lib indicators from `vbt.talib` name the arguments after their outputs,
  such as `upperband_trace_kwargs`.
* Signal markers need the values to place them on, usually the price the simulation fills at.
  `mask.vbt.signals.plot()` draws the mask as a step line, not as markers.
* A heatmap takes a Series with parameter levels, such as `pf.sharpe_ratio`. Levels beyond `x_level`
  and `y_level` must go to `slider_level`, or be selected or aggregated first, such as
  `sr.groupby(["fast_window", "slow_window"]).mean()`, or the heatmap raises. `symmetric=True`
  mirrors a grid where only one triangle is valid.
* Numeric levels are placed by value, so uneven grids such as `[5, 10, 50]` give uneven cells. Pass
  `is_x_category=True, is_y_category=True` for equal cells. Set the color scale in `trace_kwargs`,
  such as `trace_kwargs=dict(colorscale="RdYlGn", zmid=0)` to center it on zero. NaN cells can be
  expected in filtered grids, but can also mean failed runs or misaligned parameter levels. Check
  which combinations are missing.
* Records draw markers as traces and zones as shapes. Hide parts with flags such as
  `plot_ohlc=False`, `plot_close=False`, or `plot_zones=False`. `vbt-analysis` covers the portfolio
  subplots of `pf.plot`.

## 3. Combine plots

* Overlay by passing the figure along: `fig = a.vbt.plot()`, then `b.vbt.plot(fig=fig)`. For a
  figure with one panel, `fig=` is enough. For a figure with subplots, also pick the panel.
* Create subplots with `vbt.make_subplots`, which takes the arguments of
  `plotly.subplots.make_subplots`, such as `rows`, `cols`, `shared_xaxes`, `row_heights`, and
  `specs`. Place each plot with `add_trace_kwargs=dict(row=2, col=1)`. The figure needs subplot
  metadata for `row` and `col` to work. `vbt.make_subplots` supplies it and VBT rendering helpers. A
  figure from Plotly's own `make_subplots` also accepts traces by row and column.
* For two scales on one panel, create the figure with
  `vbt.make_subplots(specs=[[{"secondary_y": True}]])` and pass
  `add_trace_kwargs=dict(secondary_y=True)` to the second plot.
* Plots that create their own subplots, such as `data.plot()` with volume or `pf.plot()`, can be
  extended the same way: pass the returned figure and `add_trace_kwargs=dict(row=1, col=1)` to draw
  on the first panel. `data.plot()` places volume with `volume_add_trace_kwargs`.
* Shape routing depends on the method. Record plots can require `xref="x2", yref="y2"` alongside
  `add_trace_kwargs` for a second-row panel. Some indicator plots, including RSI, infer these
  references from their traces. Inspect `fig.layout.shapes` and the method's shape arguments.
  Secondary axes can change the numbering, so check the axis names in `fig.layout`.
* Add reference lines and bands with Plotly, such as
  `fig.add_hline(y=70, row=2, col=1, line_dash="dot")` and
  `fig.add_vrect(x0=start, x1=end, opacity=0.2)`.
* Several heatmaps on one figure share a color bar position. Move each with
  `trace_kwargs=dict(colorbar=dict(x=...))`.
* To merge traces from separate figures, add them one by one, such as
  `for trace in fig2.data: fig1.add_trace(trace, row=2, col=1)`. This does not transfer layout
  shapes, annotations, or axis settings. Recreate and route those separately.

## 4. Customize

Plotting methods take three kinds of arguments:

* `trace_kwargs` sets properties of the Plotly trace, such as
  `trace_kwargs=dict(line=dict(color="orange", width=2, dash="dot"), name="Fast MA")`. For a
  DataFrame, pass a list with one dict per column. Methods that draw several traces take one
  argument per trace, such as `ohlc_trace_kwargs`, `volume_trace_kwargs`, or `upper_trace_kwargs`.
  Read the names with `vbt.phelp(method)`, and follow forwarded `**kwargs` to the method they reach,
  as `vbt.Data.plot` forwards to `vbt.OHLCVDFAccessor.plot`.
* `add_trace_kwargs` goes to `fig.add_trace`, such as `row`, `col`, and `secondary_y`.
* Any other keyword argument goes to the layout, such as `height=600`, `title_text="..."`,
  `yaxis_type="log"`, or `width=None, height=None` for a responsive size.

After creation, use `fig.update_layout`, `fig.update_xaxes`, `fig.update_yaxes(type="log")`,
`fig.update_traces`, or change `fig.data[i]` directly. Axis methods take `row` and `col` to target
one panel.

* Rename a Series before plotting to set the legend entry, such as `ema.rename("EMA").vbt.plot()`.
  Unnamed Series get no legend entry.
* Make candles recede behind overlays with `ohlc_trace_kwargs=dict(opacity=0.5)`, or draw bars with
  `ohlc_type="ohlc"`. Candle and volume colors are the `increasing` and `decreasing` entries of
  `vbt.settings.plotting["color_schema"]`.
* Set a theme with `vbt.settings.set_theme("dark")`, one of `"light"`, `"dark"`, and `"seaborn"`. It
  applies to figures created afterwards. Restyle an existing figure with
  `fig.update_layout(template="vbt_dark")`. For a custom theme, store
  `vbt.settings.plotting["themes"]["dark"].copy()` under a new name in the same config, change its
  `color_schema` and `template_layout`, and pass the name to `set_theme`.
* Change defaults for every figure in the plotting settings, such as
  `vbt.settings.plotting["layout"]["height"] = 600`.
* OHLC plots hide the range slider of Plotly. Show it after plotting with
  `fig.update_xaxes(rangeslider_visible=True)`.
* Plotly draws the index continuously, including weekends and nights without data. Hide the gaps
  with `fig.auto_rangebreaks()`, which infers the bar frequency from the traces. When pandas infers
  a business frequency, such as business days, nothing is skipped, so pass the bar frequency, such
  as `freq="D"` or `freq="1h"`. Traces with non-datetime x-values make it do nothing, so pass
  `index=df.index` for such figures. Set `vbt.settings.plotting["auto_rangebreaks"] = True`, or a
  dict such as `dict(freq="D")`, to apply it before every `show`. `fig.skip_index(index)` hides
  specific timestamps, such as rows with missing values. Manual breaks also work, such as
  `fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])`.
* `vbt.settings.plotting["pre_render_func"]` runs a function on each figure before it is shown or
  exported as an image.

This program supplies indicator inputs through `data.run`, overlays bands and signal markers, and
puts volatility in a separate subplot. Its second figure maps stop-loss and take-profit distances to
heatmap axes, with a symbol slider:

```python
import os
import tempfile

import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=300, timeframe="1D", seed=42)
a = data.select("A")
bb = a.run("vbt:BBANDS", window=20)
atr = a.run("vbt:ATR", window=14)
entries = a.close.vbt.crossed_below(bb.lower)
exits = a.close.vbt.crossed_above(bb.middle)

fig = vbt.make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
a.plot(plot_volume=False, ohlc_trace_kwargs=dict(opacity=0.5), add_trace_kwargs=dict(row=1, col=1), fig=fig)
bb.plot(plot_close=False, add_trace_kwargs=dict(row=1, col=1), fig=fig)
entries.vbt.signals.plot_as_entries(a.close, add_trace_kwargs=dict(row=1, col=1), fig=fig)
exits.vbt.signals.plot_as_exits(a.close, add_trace_kwargs=dict(row=1, col=1), fig=fig)
atr.atr.vbt.lineplot(trace_kwargs=dict(name="ATR"), add_trace_kwargs=dict(row=2, col=1), fig=fig)
fig.update_layout(height=600, title_text="A with Bollinger Bands and ATR")
print([(trace.type, trace.name) for trace in fig.data])
assert len(fig.data) == 7
assert fig.data[-1].name == "ATR" and fig.data[-1].yaxis == "y2"

pf = vbt.PF.from_holding(
    data,
    sl_stop=vbt.Param([0.03, 0.05, 0.1]),
    tp_stop=vbt.Param([0.05, 0.1, 0.2]),
    price="nextopen",
)
heatmap = pf.total_return.vbt.heatmap(
    x_level="sl_stop",
    y_level="tp_stop",
    slider_level="symbol",
    is_x_category=True,
    is_y_category=True,
    trace_kwargs=dict(colorscale="RdYlGn", zmid=0),
)
print(pf.total_return.index.names, len(heatmap.data))
assert len(heatmap.data) == len(data.symbols)
assert all(len(trace.x) == 3 and len(trace.y) == 3 for trace in heatmap.data)
assert len(heatmap.layout.sliders[0].steps) == len(data.symbols)

out_dir = tempfile.mkdtemp()
fig.write_html(os.path.join(out_dir, "chart.html"))
heatmap.write_html(os.path.join(out_dir, "heatmap.html"))
print(sorted(os.listdir(out_dir)))
```

`data.run` supplies ATR's high, low, and close inputs automatically. The heatmap has one trace per
slider value, here one per symbol. Its portfolios enter once and exit on a stop, so the figure
illustrates a parameter surface rather than a repeated-entry strategy. Total returns are fractions.

## 5. Save and check

* `fig.show()` uses the configured Plotly renderer, which depends on the environment. It may show
  inline, open a browser, or fail in a headless process. Save the figure and tell the user the path:
  `fig.write_html("chart.html")` does not require a display or image-export dependencies.
* `fig.write_html` is the method of Plotly and skips the `auto_rangebreaks` and `pre_render_func`
  settings. Call `fig.auto_rangebreaks()` before saving. `fig.show`, `fig.to_image`,
  `fig.write_image`, and `fig.to_html_str()` apply both. To save HTML with both hooks applied, write
  the string from `fig.to_html_str(include_plotlyjs=True)` to a file. Its default `"cdn"` needs
  network access to load Plotly.js, while `True` embeds it for offline use.
* To put several figures in one HTML file, write `fig.to_html(full_html=False)` of each figure into
  the same file.
* `fig.write_image("chart.png")`, `fig.show_png()`, and `fig.show_svg()` need the `kaleido` package,
  and recent versions of kaleido also need a Chrome installation. If export fails with a browser
  error or hangs, save HTML and report the export limitation. Install export dependencies when
  environment setup is within the authorized task.
* When you cannot look at the figure, check its contents instead: print the trace types and names
  from `fig.data`, and the length of each trace's `x`. Missing traces or empty data show up there.
  By default, line plots with at least 10,000 input values use `scattergl` traces when the global
  `use_webgl` setting is enabled. Inspect the trace type when diagnosing rendering differences.
* In IDEs where figures do not appear, set `import plotly.io as pio` and
  `pio.renderers.default = "browser"`, or `"notebook"` for classic Jupyter. For VBT figures only,
  `vbt.settings.plotting["show_kwargs"]["renderer"] = "iframe"` does the same.
  `vbt.settings.plotting["use_widgets"] = True` switches to `vbt.FigureWidget`, which needs the
  widget dependencies of Plotly. Set it to False to use ordinary figures when the problem comes from
  widget integration.

## Large figures

* Plotly slows down beyond a few hundred thousand points per figure. Plot one symbol and a date
  range, such as `data.loc["2024"]`, resample the object before plotting, such as
  `data.resample("1D")` or `pf.resample("1D")`, or cut an existing figure with
  `fig.select_range(start="2024-03", end="2024-06")`. Integer bounds count bars, which also drops
  the warm-up period of an indicator.
* `vbt.settings.plotting["use_resampler"] = True` resamples traces on the fly when
  `plotly-resampler` is installed. It handles line traces only and can break figures that mix trace
  types. Turn it off for one plot with `make_figure_kwargs=dict(use_resampler=False)`.
* Very large heatmaps can exceed browser rendering limits. Aggregate or resample, then verify the
  exported figure in the target browser.

## Pitfalls

* `df.plot()` and `sr.plot()` without `.vbt` call pandas and matplotlib, which fails with errors
  such as "'Axes' object has no attribute 'update_layout'". Use `sr.vbt.plot()`.
* `plot_volume=False` and `ohlc_trace_kwargs` are arguments of `vbt.Data.plot` and
  `vbt.OHLCVDFAccessor.plot`, not of `df.vbt.plot`. Synthetic data without volume plots candles
  only.
* Each plotting call adds traces with its own legend entries. Repeated calls on one figure, such as
  in a loop over symbols, repeat legend names and the price line. Pass distinct names in
  `trace_kwargs`, `showlegend=False` for repeats, and `plot_close=False` after the first call.
* `add_trace_kwargs` only places traces. Axis titles, ranges, and formats of a subplot are set on
  the figure with `fig.update_yaxes(..., row=2, col=1)`.
* Plots on a shared x-axis need compatible coordinates, but can have different sampling times. Wrap
  computed arrays with their actual datetime index before plotting, such as
  `pd.Series(values, index=close.index)`, instead of plotting them by position.
* Timestamps are shown in the timezone of the index. Convert the index with `tz_convert` before
  plotting to show another timezone, and make range break bounds match it.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/cookbook/plotting/`: plot types, overlays, subplots, themes, range breaks, export, and
  resampling
* `/documentation/indicators/analysis/`: plotting indicators and their outputs, and custom subplots
  with `plots`
* `/api/generic/accessors/`: arguments of `heatmap`, `plot_against`, `overlay_with_heatmap`, and the
  other accessor plots
* `/api/generic/ranges/`: plots of ranges, drawdowns, and their shapes
* `/api/utils/figure/`: `vbt.Figure` methods such as `select_range`, `auto_rangebreaks`, and
  `show_png`
* `/api/_settings/#vectorbtpro._settings.plotting`: every global plotting setting
