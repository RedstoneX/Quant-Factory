---
name: vbt-basics
description: "Shared API discovery, broadcasting, settings, and execution guidance for VectorBT PRO (vectorbtpro). Use when writing, running, or debugging VBT code. Read once before the relevant task skill. VectorBT PRO differs from open-source vectorbt."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Working with VectorBT PRO

VectorBT PRO (`import vectorbtpro as vbt`) is a private package. It is not the open-source
`vectorbt`: names, arguments, and defaults differ, and code written from memory of `vectorbt` is
often wrong. Check the installed API and relevant documentation before writing code.

## Start with the task

Read the shared checks below once per environment, then open the skill for the next decision. Use
later sections of this skill when shapes, labels, settings, or annualization become relevant.

| Request or obstacle | Start here | Continue when needed |
| --- | --- | --- |
| Load files, repair gaps, or combine timeframes | `vbt-data` | `vbt-indicators` for derived features |
| Compute a feature or explain different indicator values | `vbt-indicators` | `vbt-numba` for a custom compiled calculation |
| Turn a trading rule or external events into entries and exits | `vbt-signals` | `vbt-backtesting` to execute them |
| Build a backtest or explain a missing fill | `vbt-backtesting` | `vbt-callbacks` when a decision needs positions, cash, or fill state |
| Write a simulation loop or reduce measured simulator overhead | `vbt-custom-simulators` | `vbt-numba` for compiling and debugging the loop |
| Explain trades, P&L, or risk metrics | `vbt-analysis` | `vbt-plotting` for a custom chart |
| Plot prices, signals, or a parameter grid | `vbt-plotting` | `vbt-analysis` to resolve the quantity being plotted |
| Search parameters or reduce a search's memory use | `vbt-optimization` | `vbt-cross-validation` to evaluate the selection on unseen data |
| Build train/test or walk-forward evaluation | `vbt-cross-validation` | `vbt-optimization` for execution choices |
| Allocate among assets or schedule rebalancing | `vbt-portfolio-optimization` | `vbt-callbacks` for decisions based on simulated holdings |
| Debug a compiled function or a crash | `vbt-numba` | `vbt-callbacks` for simulation context and timing |
| Select or benchmark a Python backend | `vbt-rust-backend` | `vbt-numba` for Python callbacks that remain on Numba |
| Write a native Rust program or port a simulator | `vbt-rust-native` | `vbt-analysis` for results exported to Python |
| Continue a simulation as bars arrive | `vbt-backtesting` | `vbt-data` for updates and `vbt-callbacks` for custom memory |

For a full strategy, work through data, features and signals, then a small simulation. Verify its
orders before parameter search, and evaluate selected parameters out of sample before reporting
performance. Start at the relevant stage when the user already has inputs or results.

## Shared checks

1. Check the installed version first. VBT changes between releases and documentation is a release
   snapshot.
2. Verify the APIs and arguments the task uses against the installed package. Reuse checks already
   made in this session unless the environment changes. Do not guess arguments.
3. Test new calculations and simulations on small, reproducible inputs. Synthetic data such as
   `vbt.GBMOHLCData.pull` avoids provider dependencies. For a reported bug, also reproduce it with
   the supplied inputs. Report what you ran and any checks you could not complete.
4. For Python debugging or quick iteration on small inputs, disable Numba before its first import,
   usually at the top of a fresh script:

   ```python
   import os

   os.environ["NUMBA_DISABLE_JIT"] = "1"
   ```

   Prefer this mode for developing custom Numba functions: they run as Python, giving quick feedback
   and Python tracebacks. Eligible built-in operations can still dispatch to Rust automatically.
   Prefer Rust over compiling Numba for those operations because it has no compilation startup cost
   and is usually faster. Select `jitted="nb"` to request Numba for an operation explicitly.
   `vbt.is_numba_enabled` confirms the Numba setting.

   Once custom functions work on small inputs, verify them with JIT enabled and
   `NUMBA_BOUNDSCHECK=1` to catch compilation errors and invalid indexing. The same functions then
   run compiled for larger inputs. The `run_code` kernel imports vectorbtpro at startup, so changing
   this environment variable inside an existing kernel is too late.
5. Import explicitly in files you write: `import vectorbtpro as vbt`, plus `numpy as np`,
   `pandas as pd`, and `from numba import njit` as needed. Documentation examples and the `run_code`
   kernel use `from vectorbtpro import *`, which also provides these names and shortcuts such as `X`
   and `O` for True and False. When copying an example into a file, add the imports it relies on and
   replace the shortcuts. `vbt.whats_imported` lists every name the star import provides.
6. Keep credentials out of code and output. VBT loads a `.env` file from the working directory on
   import. Do not print the environment or the star import's `env`, or expose credentials through
   saved data objects. Keep dependency installation and provider access within the authorized task.
   A backtest request does not authorize live trading.

## Mental model

* User-facing time series are usually Pandas objects. Kernels operate on NumPy arrays. Columns
  represent assets or strategy instances, and grouped columns can interact through shared cash.
  Arguments broadcast against each other, and parameters add column levels such as `ma_window` on
  top of `symbol`.
* Accessors add VBT methods to Pandas objects: `.vbt` for Indexes, Series, and DataFrames,
  `.vbt.signals` for boolean arrays only, `.vbt.returns` for returns, and `.vbt.ohlcv` for a
  DataFrame with OHLCV columns.
* A `vbt.Data` instance holds features such as Close for each symbol. `data.close` or
  `data.get("Close")` returns a DataFrame for a symbol list, including a one-item list, or a Series
  for a scalar symbol selection. Pass the instance directly to `vbt.PF.from_signals` so that open,
  high, and low are used for fills and stops. Keep indicator outputs separate unless later data
  operations need them as features.
* Treat data, indicators, and portfolios as immutable: use methods that return new instances or
  `replace` to change constructor arguments. Their contained arrays can still be mutated, which can
  leave cached results stale. `replace` rebuilds the object from its configuration and does not
  rerun a simulation's decisions, so test new rules with a new simulation.
* These objects support Pandas indexing with `[]`, `loc`, `iloc`, and `xs`. The selection applies to
  every array inside and returns a new instance, such as `data.loc["2024"]` or `pf["A"]`.
* Numba callbacks (`*_nb`) run inside simulations. Read the `vbt-callbacks` skill before writing
  one, and pass callbacks NumPy arrays of a consistent shape and dtype.

## Find the API for one decision

Start with the part of the task that is uncertain. For example, "align a daily RSI to hourly bars
without using the unfinished daily close" gives a useful search target:

1. Search local knowledge below for a known name or phrase, or use `find_concepts` or `search` for
   discovery. Read the relevant concept's sources or page section. A search excerpt alone can omit
   the timing assumption that makes a recipe correct.
2. Resolve the proposed object and inspect its installed signature or source. Follow forwarded
   arguments to their owner. For this example, check closing alignment in `vbt-data` and the
   installed `vbt.GenericAccessor.realign_closing`.
3. Run the smallest check of the uncertain behavior, such as the first hourly bar where a completed
   daily value appears. Then integrate it into the user's pipeline.

For an error involving a known object, go straight to that object's source and the matching task
skill. Use surrounding Discord replies when a recipe depends on the original user's assumptions.

### Search local knowledge

Reuse local documentation or assets when available. To download and export the installed release's
pages, messages, examples, and concepts without MCP or embeddings:

```bash
vbt pull-assets ./knowledge
rg -n -i 'trailing stop|stop_exit_price' './knowledge/<release>' --glob '*.json'
```

Replace `<release>` with the tag in the printed paths. Searching `./knowledge` includes all
releases. Downloads use configured GitHub access, usually `GITHUB_TOKEN`, and reuse cached assets.
Use `--asset pages` to select a dataset (repeat for several) and `--release TAG` to select a
release. Selected exports are overwritten. Keep datasets on one release and verify APIs against the
installed package.

Each JSON file is a list of records. Page text can live in child headings, messages link to replies,
and concepts contain ranked source URLs. Follow those links for context. API objects appear as fully
qualified names, such as `vectorbtpro.data.base.Data.run` or
`vectorbtpro_rust::portfolio::simulator::SignalSimulator`, instead of links. Pass them to `get_page`
to read their API page. For files already downloaded as `.json.gz`, decompress them or load them
with `vbt.PagesAsset.from_json_file` and the corresponding asset classes. Pages can be exported to
Markdown with `pages.save_to_markdown`.

### Search and inspect through tools

Use the VectorBT PRO MCP tools for ranked discovery or when local assets are unavailable. The same
tools are available through the CLI (`vbt` or `python -m vectorbtpro`), with arguments as options
and `--call` JSON.

| Purpose | MCP tool | CLI |
| --- | --- | --- |
| Python and VBT versions | `get_environment` | `vbt mcp get-environment` |
| Find the topics of a question | `find_concepts` | `vbt mcp find-concepts "query"` |
| Read ranked sources of a topic | `get_concept` | `vbt mcp get-concept ID` |
| Search docs, API, examples, Discord | `search` | `vbt mcp search "query"` |
| Read a docs page or section | `get_page` | `vbt mcp get-page /cookbook/data/` |
| Read a Discord message, an author's consecutive messages, or a thread | `get_message`, `get_message_block`, `get_message_thread` | `vbt mcp get-message URL` |
| Resolve names like `vbt.PF` | `resolve_refnames` | `vbt mcp resolve-refnames NAME...` |
| Find docs mentioning an object | `find` | `vbt mcp find NAME...` |
| List attributes of an object | `get_attrs` | `vbt mcp get-attrs NAME` |
| Read source of an object | `get_source` | `vbt mcp get-source NAME` |
| Run code in a persistent kernel | `run_code` | `python` with `import vectorbtpro as vbt` |
| List and read skills | `list_skills`, `get_skill` | `vbt mcp list-skills`, `vbt mcp get-skill NAME` |

* `find_concepts`, `get_concept`, `search`, `find`, and `get_page` read knowledge assets downloaded
  with the user's GitHub token, and the first call may take a while to build an index. If they fail,
  rely on `resolve_refnames`, `get_attrs`, and `get_source`, which inspect the installed package and
  work offline. Report the failure instead of guessing.
* `search` takes `asset_names`, such as `"examples"` for working code or `"messages"` for community
  answers to an unusual warning. In Python, `vbt.quick_search` finds exact warnings and names with
  keyword search, without an embeddings provider.
* `run_code` keeps variables between calls. It is available only when the MCP server runs over
  stdio, not over HTTP. After editing a module that the kernel imported, pass `restart=True`. The
  CLI starts a new process on every call, so prefer scripts there.
* In plain Python, `vbt.phelp` prints a signature with its docs, `vbt.pdir` lists attributes,
  `vbt.pprint` shows the configuration of a VBT object, and `vbt.ptable` shows an array or record
  array as a table. `obj.deep_getattr("trades.expectancy")` resolves a dotted path of attributes,
  and `vbt.get_capabilities()` reports the installed indicators, data sources, and engines.

## Parameters and columns

Pandas aligns arithmetic by label, while comparisons can raise when labels differ. Use `.vbt` on the
left operand when combining arrays that need VBT broadcasting, especially indicator outputs with
parameter levels. Apply it at each nested operation that needs broadcasting, such as
`(a.vbt & b).vbt | c`. VBT then broadcasts both sides by position, like NumPy, and matches column
counts that NumPy cannot broadcast through a column level both sides share, such as `symbol`.
Columns are not aligned by label, so keep symbols in the same order everywhere.

A one-dimensional NumPy array broadcasts as a time series with one value per bar. Pass per-column
values as a one-row array, such as `np.array([[0.001, 0.002]])`, or a one-row DataFrame with a
non-datetime index, such as the default RangeIndex, and the columns in the same order as the input.
A datetime index aligns the row by date instead. A Series also broadcasts along rows unless its
broadcast axis is configured explicitly. Pandas inputs with different dates are joined on all dates
and filled with NaN, so resample data of other timeframes to one index first. To set an argument
only at chosen rows without building an array, pass `vbt.index_dict({0: 1 / 3})`, keyed by
positions, labels, or indexers such as `vbt.pointidx(every="W")`.

Run this program to see how parameters and columns interact:

```python
import vectorbtpro as vbt

data = vbt.GBMOHLCData.pull(["A", "B"], start="2024-01-01", periods=300, timeframe="1D", seed=42)
fast = vbt.MA.run(data.close, window=[5, 10], short_name="fast")
slow = vbt.MA.run(data.close, window=[20, 50], short_name="slow")
rsi = vbt.RSI.run(data.close)

above = fast.ma.vbt > slow.ma
assert above.shape[1] == 4
print(above.columns)

low_rsi = rsi.rsi.vbt < vbt.Param([50, 70], name="rsi_th")
fast_ma, slow_ma, low_rsi = vbt.pd_acc.x(fast.ma, slow.ma, low_rsi)
entries = fast_ma.vbt.crossed_above(slow_ma).vbt & low_rsi
exits = fast_ma.vbt.crossed_below(slow_ma)
assert entries.columns.equals(exits.columns)
assert entries.columns.names == ["fast_window", "slow_window", "rsi_th", "symbol"]
assert entries.shape[1] == 16
pf = vbt.PF.from_signals(data, entries=entries, exits=exits, price="nextopen")

print(pf.wrapper.columns)
print(pf.stats()[["Total Return [%]", "Total Trades"]])
print(pf.total_return.groupby("rsi_th").mean())
print(pf.xs("A", level="symbol", axis=1).total_return)
print(pf[(5, 20, 70, "B")].total_return)
```

* `fast.ma.vbt > slow.ma` pairs the columns by position, so it tests only the windows (5, 20) and
  (10, 50). This zipping is silent, so check the columns of every combined array.
* `vbt.pd_acc.x` (short for `cross`) builds the Cartesian product of the parameter columns of
  several arrays in one call and keeps the shared `symbol` level intact. It returns the arrays with
  identical columns, here 8 parameter combinations for each of 2 symbols. `fast.ma.vbt.x(slow.ma)`
  crosses just the two moving-average grids.
* Comparing with `vbt.Param` tests each scalar threshold as a new column level, such as `rsi_th`.
* `exits` also has the `rsi_th` level because the cross expanded all three arrays before the signals
  were computed.
* Select one column with the full tuple in level order, such as `pf[(5, 20, 70, "B")]` or
  `pf.stats(column=(5, 20, 70, "B"))`, and a level value with `xs(..., level=..., axis=1)`.
  Aggregate over levels with `groupby`.
* Indicators hide a parameter left at its default, so `vbt.RSI.run(data.close)` adds no level, while
  passing `window=14` explicitly adds `rsi_window`. When running a single parameter combination,
  pass `hide_params=True` to keep the columns as plain symbols.
* Indicator `run` methods zip parameter lists, broadcasting singleton lists to the longest list,
  even when wrapped in `vbt.Param`. Other lengths must match. Pass `param_product=True` to test
  every combination.
* Elsewhere, such as in `vbt.PF.from_signals` or functions decorated with `vbt.parameterized`,
  several `vbt.Param` arguments form a Cartesian product. Give them the same `level` to zip them,
  and use `condition` or `random_subset` to shrink a large grid.

### Column levels, grouping, and stacking

* Print `columns.names` before selecting or grouping. Change levels through the accessor:
  `df.vbt.rename_levels({"ma_window": "window"})`, `df.vbt.drop_levels("ma_wtype")`, and
  `df.vbt.select_levels(["ma_window", "symbol"])`. Removing levels can make distinct columns share a
  label, so check `columns.is_unique` afterwards.
* `xs(value, level=..., axis=1)` selects a level value on arrays and on VBT objects alike, and
  `df.vbt.xloc[vbt.colidx("A", level="symbol")].get()` does the same through smart indexing.
* Aggregate columns by level with `df.T.groupby(level="symbol").mean().T`, and a Series of metrics
  with `metric.groupby("symbol").mean()`.
* `group_by` accepts level names and `vbt.ExceptLevel(...)`. Simulations and metrics that use group
  lengths require adjacent columns per group. Grouping a parameter grid by its innermost `symbol`
  level can raise "group_by must form monolithic, sorted groups". Sort the signals first with
  `entries.sort_index(axis=1, level="symbol")`. Broadcasting still matches each column to its
  symbol's prices. APIs that use group maps can handle nonadjacent groups.
* Stack arrays as new columns under a level with
  `vbt.pd_acc.concat(a, b, keys=pd.Index([5, 10], name="window"))`, and repeat one array with
  `close.vbt.tile(3, keys=pd.Index([...], name="..."))`. Stack portfolios with
  `vbt.PF.column_stack`, as described in `vbt-analysis`.
* `vbt.PF.row_stack` joins consecutive periods, such as walk-forward test windows. Read
  `vbt-analysis` for how it treats each window's initial cash.
* `vbt.broadcast(a, b)` returns both arrays in their common shape, which shows how two arrays will
  be combined. Arrays whose parameter levels hold different values raise "Level ... contains values
  not in first index", and arrays whose symbols are in a different order warn.

## Settings, persistence, templates, and caching

* `vbt.settings` holds the defaults of every subsystem, such as
  `vbt.settings.portfolio["init_cash"]` or `vbt.settings.returns["year_freq"]`. Call-time defaults
  are resolved when used, so changes can also affect existing objects whose arguments were left
  unset. `vbt.settings.portfolio.reset()` restores that section's defaults. Prefer passing arguments
  explicitly and report any setting you changed.
* Nested option dictionaries are merged key by key with the defaults through `vbt.merge_dicts`, so a
  passed dict overrides only its keys. Pass `vbt.unsetkey` as a value to remove a default key, and
  wrap a dict in `vbt.atomic_dict` to replace the default whole.
* `vbt.set_seed(42)` seeds Python, NumPy, and Numba together. Give independent randomized tasks
  their own explicit seeds.
* Settings read on import, such as those of Numba, caching, and chunking, belong in a settings file
  named `vbt` with the extension `.cfg`, `.yml`, or `.toml` in the working directory, or at the path
  in `VBT_SETTINGS_PATH`, as shown in `/cookbook/configuration/`. `auto_import = false` under
  `[importing]` there reduces import work when accessors and plotting are not needed.
* `vbt.save(obj, "results.pickle")` and `vbt.load` keep any object, including dictionaries of
  results. Add a compression extension such as `.blosc2`, `.gzip`, or `.lzma` to compress, which
  `load` detects. `pf.save()` writes `Portfolio.pickle`, which `vbt.PF.load()` reads. Pickles may
  not load in another VBT version, and `/cookbook/persistence/` shows how to rebuild them with
  `vbt.RecInfo`.
* Templates defer a value until the function that receives it knows its context:
  `vbt.Rep("wrapper")` takes a value by name, `vbt.RepEval("wrapper.shape_2d")` evaluates an
  expression, `vbt.RepFunc(func)` calls a function with arguments resolved by name, and
  `vbt.Sub("$symbol.csv")` fills a string. Each function documents the names its context provides.
* Clear registry-managed caches with `vbt.flush()`, which also collects garbage, or
  `vbt.clear_cache(pf)` for one object. `vbt.print_cache_stats()` shows what is cached, and
  `with vbt.CachingDisabled():` turns caching off for a block. These controls do not clear Numba
  disk caches, data caches, or cached preparer properties. Mutating contained arrays does not
  invalidate cached results.

## Frequency and annualization

* Annualized metrics such as the Sharpe ratio divide the year frequency by the index frequency to
  get the number of bars per year. VBT infers the index frequency from a regular index by using
  `freq="auto"`, and raises or warns otherwise. Pass `freq`, such as `freq="1h"`, when the index has
  gaps.
* The year frequency defaults to 365 days, which fits markets that trade around the clock. For
  stocks it overstates annualized metrics, since daily bars give 365 bars per year instead of
  about 252. Choosing it is the user's responsibility. When the number of trading days or bars per
  year is known, set it explicitly, such as `year_freq="252 days"` for daily stock bars or
  `year_freq=pd.Timedelta(hours=6.5) * 252` for intraday bars during regular US trading hours.
  Otherwise, `year_freq="auto"` counts the bars per year in the index. Pass it to the portfolio or
  returns accessor, or set `vbt.settings.returns["year_freq"]`, and report the value used.
* Data instances localize and convert datetime indexes to UTC by default. Explicit arguments or
  provider metadata can override the zone, which determines clock times and daily bins. Read
  `vbt-data` before working with sessions or exchange time.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/documentation/fundamentals/`: broadcasting, flexible indexing, and the design behind them
* `/cookbook/data/` and `/cookbook/indexing/`: loading, selecting, and changing data
* `/cookbook/optimization/`: parameters, chunking, and memory for large grids
* `/cookbook/portfolio/`: metrics, including the year frequency and annualization
* `/cookbook/discovery/` and `/cookbook/compilation/`: inspecting objects and controlling Numba
* `/cookbook/configuration/`: copying and replacing objects, settings, and settings files
* `/cookbook/persistence/` and `/cookbook/caching/`: saving, compressing, and rebuilding objects,
  and controlling caches
