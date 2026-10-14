---
name: vbt-data
description: "Load, validate, store, update, and resample market data with VectorBT PRO. Use when preparing data for VBT, fixing gaps or time zones, adding a data source, or aligning multiple timeframes without look-ahead."
license: Proprietary
metadata:
  vbt-skill: "2026.10.5"
---

# Data with VBT

Read `vbt-basics` once for API discovery and shared conventions. Start with the inputs the user
already has. Use steps 1 and 2 for acquisition, steps 3 and 4 for preparation, and step 5 for
storage or recurring updates.

## 1. Pick a source and read its arguments

| Source | Class |
| --- | --- |
| Quick tests with stocks and crypto, lower quality | `vbt.YFData` |
| Crypto exchanges | `vbt.BinanceData`, or `vbt.CCXTData` with `exchange="..."` |
| Stocks with an API key | `vbt.AlpacaData`, `vbt.PolygonData` |
| Charts and indexes from TradingView | `vbt.TVData` |
| Local files and databases | `vbt.CSVData`, `vbt.HDFData`, `vbt.ParquetData`, `vbt.SQLData`, `vbt.DuckDBData`, `vbt.ArcticDBData` |
| Synthetic data for development | `vbt.GBMOHLCData`, `vbt.RandomOHLCData` |
| DataFrames you already have | `vbt.Data.from_data` |

* Read the arguments of a class with `vbt.phelp` on its `fetch_symbol` method before pulling.
  Synthetic classes show only `**kwargs` there, so read `vbt.SyntheticData.fetch_key` for the index
  and the class's `generate_symbol`, such as `vbt.GBMOHLCData.generate_symbol`, for the rest.
* The bar size is usually `timeframe`, such as `timeframe="1h"`. `start` and `end` accept dates and
  phrases such as `"1 month ago"`, and `end` is exclusive. Dates without a time zone are read in the
  zone of the source or of `tz`, so append `UTC` or pass aware timestamps to be exact.
* Provider classes forward arguments they do not know to the provider library or ignore them, so a
  misspelled argument can pass silently. Check the index after every pull.
* Symbols are written differently per source: `BTC-USD` for Yahoo Finance, `BTCUSDT` for Binance,
  `BTC/USDT` for CCXT, and `EXCHANGE:SYMBOL` for TradingView. Classes with a `list_` method list
  what they can fetch, such as `vbt.BinanceData.list_symbols("*USDT")`, `vbt.TVData.list_symbols`,
  and `vbt.CSVData.list_paths`.
* Know the limits of the source before choosing a range. Yahoo Finance serves intraday bars only for
  recent periods. Check the provider's current limits and the installed wrapper's adjustment
  settings before choosing the range. `vbt.TVData` takes no `start` or `end` and returns the latest
  `limit` bars, so select dates after pulling. Some exchanges return nothing when `start` precedes
  the listing, and `vbt.CCXTData` takes `find_earliest_date=True` to search for it.
* Follow the authorization guidance in `vbt-basics` for paid sources. Arguments passed to `pull`,
  including `client_config` with API keys, are stored in `data.fetch_kwargs` and saved with the
  instance. Read keys from environment variables, as described in `vbt-basics`, and set them once
  with `set_custom_settings`, such as `vbt.AlpacaData.set_custom_settings(client_config=dict(...))`.
  Pass a client built once with `resolve_client` as `client` to avoid authenticating per symbol.
* For a source without a class, subclass `vbt.Data` and implement the class method
  `fetch_symbol(cls, symbol, **kwargs)` to return a Series or DataFrame, optionally paired with
  metadata. For market bars, use standard feature names such as Open and Close and a time zone aware
  index. Call `pull` on the subclass to get a data instance. Implement `update_symbol` to support
  updates, as shown in `/documentation/data/management/`.

## 2. Pull and check alignment, time zones, and gaps

`pull` takes one symbol or a list, fetches each one, and aligns them into one instance. Features
such as `data.close` are Series for a scalar symbol or DataFrames for a symbol list.

* Pass different arguments per symbol with `vbt.symbol_dict`, such as
  `exchange=vbt.symbol_dict(SPX="SP", NDX="NASDAQ")`. A scalar `seed` gives each synthetic symbol
  its own seed. Pass `split_seed=False` to give every symbol the same random draws, for example to
  compare volatility scenarios.
* Symbols with different dates are aligned to the union of their indexes, with missing values and a
  warning. Pass `missing_index="drop"` to keep only shared rows. Symbols with different features
  raise an error, so pass `missing_columns="nan"` or `"drop"`.
* Pass `skip_on_error=True` to skip symbols that fail instead of stopping the pull. Symbols that
  fail or return no rows are then missing from `data.symbols` with only a warning, so compare it
  with the requested list.
* Fetching is serial. `execute_kwargs=dict(engine="threadpool", chunk_len=3)` fetches in parallel,
  in batches of three with the default `distribute="tasks"`, and `execute_kwargs=dict(delay=0.5)`
  waits after each symbol. Providers ban clients that exceed their rate limits.
* VBT's bar-alignment methods assume timestamps label bar opens. Check that convention when loading
  files or custom data. The close of a daily bar labeled 00:00 is known only at the end of that day.
* Rows with duplicate timestamps are dropped, keeping the last one. A long table with a symbol
  column must be split into one DataFrame per symbol and passed to `vbt.Data.from_data` as a
  dictionary keyed by symbol.
* Datetime indexes default to UTC localization and conversion unless explicit arguments or provider
  metadata specify another zone. For exchange time and daylight saving time, follow the section on
  time zones below.
* Conflicting localization zones reported by sources, such as a US stock and a coin on Yahoo
  Finance, raise "Returned objects have different timezones". Conflicting conversion zones warn and
  fall back to UTC. Pass `tz="UTC"` or another zone to `pull`, then use `data.realign` to merge the
  indexes by actual time. `vbt.Data.merge` takes `tz_localize` and `tz_convert` to resolve the same
  conflict between instances.
* Gaps in time, such as exchange downtime, need no filling, since VBT works on irregular indexes.
  List them with `data.wrapper.get_resampler("1h").index_difference(reverse=True)`. Resampling turns
  them into rows of missing values. Pass `freq` to simulations when the index has gaps, as described
  in `vbt-basics`.
* After pulling, print `data.symbols`, `data.features`, `data.wrapper.freq`, the first and last
  timestamps, and `data.stats()`, which counts missing values per symbol.

## 3. Prepare features

* Extract arrays with `data.get("Close")` or `data.close`, select symbols or features with
  `data.select`, and add a computed feature with `data.add_feature("SMA", sma_df)`. Every method
  returns a new instance. Never change `data.data` in place, and build a new instance with
  `vbt.Data.from_data` instead.
* Select one feature and a scalar symbol for a Series: `data.get("Close", symbols="A")`. Use a
  symbol list for a DataFrame: `data.get("Close", symbols=["A"])`. With multiple features and
  symbols, `get` returns a tuple of frames by default. A list of features alone does not guarantee a
  DataFrame.
* `data.loc`, `data.iloc`, and `data[...]` select rows and features across all symbols. They do not
  select symbols, which is the job of `data.select`.
* Clean rows across all symbols with `data.dropna()`, or with `data.transform(func)` for any
  function over the concatenated DataFrame. Pass `per_symbol=True` to apply it to each symbol. The
  function must return the same columns for every symbol.
* Decide what missing prices mean before filling them. Forward filling invents flat bars and changes
  indicator windows. Keep missing rows, drop them, or let the indicator skip them according to the
  intended calculation, as described in `vbt-indicators`.
* Join instances with `vbt.Data.merge`, for example the same symbol from two providers. Later
  instances replace overlapping rows of earlier ones, so a batch from an external feed can revise
  the last stored bar. Keep remote and local data in separate instances and merge them when needed.
* Wrap DataFrames with `vbt.Data.from_data`, passing a dictionary keyed by symbol wrapped in
  `vbt.symbol_dict`, or by feature wrapped in `vbt.feature_dict`. A DataFrame with symbols as
  columns needs `columns_are_symbols=True`, which creates a feature-oriented instance where `select`
  and indexing act on the swapped keys. Add `invert_data=True` for the usual layout.
* Keep the most granular timeframe you need and resample it up. Higher timeframes cannot be turned
  into lower ones.

### Stock universes and corporate actions

For a historical stock strategy, establish which symbols were eligible at each date. Today's
constituents omit former members and delisted stocks. Keep a dated membership mask alongside the
price data and use it when forming entry signals or allocation candidates. Define what happens to an
open position when membership ends, including the price available to close it. Missing prices alone
do not specify that execution policy.

Check the provider's price and volume adjustment settings before mixing data or comparing results.
VBT never adjusts prices itself. `vbt.YFData` returns prices adjusted for splits and dividends by
default, and `auto_adjust=False` keeps raw prices with the adjusted close as a separate feature.
`vbt.AlpacaData.fetch_symbol` exposes `adjustment`, while `vbt.PolygonData.fetch_symbol` exposes
`adjusted` for splits. Roll and back-adjust continuous futures before loading them, so that roll
gaps do not appear as price moves. Keep the chosen convention consistent across OHLC, volume, and
any explicit cash-dividend accounting. Verify a known corporate-action date against the source
instead of treating a price jump as an indicator bug.

Keep raw fetched data separate from eligibility and cleaning rules so updates can reapply those
rules. The data object's `delisted` flags skip fetching marked keys during updates. They are not a
historical membership calendar. Initial capital, shared cash, and exits belong to the simulation
policy in `vbt-backtesting`, even when an asset is inactive for part of the dataset.

## 4. Combine timeframes without look-ahead

* Resample a whole instance with `data.resample("1d")`. Open, high, low, close, volume, trade count,
  and VWAP are aggregated automatically. Other features raise an error unless `data.feature_config`
  has a `resample_func` for them. Data read from files lacks the configuration of its provider, and
  `data = data.use_feature_config_of(vbt.BinanceData)` copies it.
* Bring higher-timeframe values back to the original index with `realign_closing` for anything known
  only at the end of a bar, such as the close, high, low, or an indicator computed from them. Use
  `realign_opening` only for values known at the start of a bar, such as the open.
* Plain `reindex`, `ffill`, and `join` align labels without knowing when a bar's value became
  available. Applied directly to open-labeled higher-timeframe closes, they leak future values. Use
  closing alignment, or explicitly align by availability timestamps.
* Resample only to a timeframe that is a whole multiple of the source bar, or the call warns that
  some bars span two target bars. Resample from the finest data instead.
* Bins follow the clock. Intraday stock bars resampled to 4 hours create bins outside the session,
  and daily stock bars resampled to `"1D"` gain weekend rows of missing values. Drop extended hours
  before resampling, or pass a custom index or `vbt.Resampler` built from session bounds.
* Realigned masks come back as floats with NaN before the first known value, and NaN cast to bool is
  `True`. Fill them with `False` before `astype(bool)`. To place a higher-timeframe signal once
  instead of repeating it, pass `ffill=False` to `realign_closing`.
* Convert indexes with different datetime resolutions, such as milliseconds and nanoseconds, to the
  same resolution before realigning between them.
* TA-Lib indicators take `timeframe` and handle the resampling and alignment themselves, as
  described in `vbt-indicators`.

This program resamples hourly data to days, computes a daily moving average, aligns it back to
hours, and compares it with a leaky alignment. On the first hour of a day, the leaky version already
shows the moving average that includes that day's close:

```python
import vectorbtpro as vbt


def daily_sma_on_hours(h1_data, window):
    d1_data = h1_data.resample("1d")
    d1_sma = d1_data.close.vbt.rolling_mean(window)
    return d1_sma.vbt.realign_closing(h1_data.index)


h1_data = vbt.GBMOHLCData.pull(
    ["A", "B"],
    start="2024-01-01",
    periods=24 * 60,
    timeframe="1h",
    seed=42,
)
print(h1_data.resample("1d").get(symbols="A").head(3))

h1_sma = daily_sma_on_hours(h1_data, 5)
print(h1_sma.iloc[[119, 120, 143]])

leaky_sma = h1_data.resample("1d").close.vbt.rolling_mean(5).reindex(h1_data.index).ffill()
print(leaky_sma.iloc[[119, 120, 143]])
assert h1_sma.iloc[:119].isna().all().all()
assert h1_sma.iloc[119].notna().all()
assert leaky_sma.iloc[96].notna().all()

half = h1_data.iloc[: 24 * 30 + 12]
half_sma = daily_sma_on_hours(half, 5)
assert h1_sma.loc[half.index].equals(half_sma)
print("Alignment check passed")
```

The last check repeats the calculation on data cut in the middle of a day and verifies that the
shared rows are identical. Test several cut points, including incomplete higher-timeframe bars, when
validating a multi-timeframe feature.

## 5. Store the data and update it

* `data.save(path)` and `vbt.load(path)` keep the whole instance, including the arguments used to
  fetch it. Use them by default. Pickles may not load in another VBT version.
* `to_csv`, `to_hdf`, `to_parquet`, `to_sql`, and `to_duckdb` write plain tables and drop that
  metadata. Read them back with `vbt.CSVData.pull` and the other local classes, or with
  `vbt.Data.from_csv` and similar methods. Calling them on a provider class, such as
  `vbt.BinanceData.from_csv(path, fetch_kwargs=dict(timeframe="1h"))`, makes the data updatable from
  the provider again.
* `vbt.DuckDBData.pull` opens the database read-only by default, so several processes can read it.
  Pass `query=vbt.key_dict({symbol: sql, ...})` with `index_col` to read each symbol from a shared
  table or Parquet files. `data.to_parquet(partition_by="day")` partitions by date, and
  `vbt.ParquetData.pull(..., filters=[("group", "==", "2024-01-02")])` reads one partition.
* `pull(..., cache=True)` keeps each symbol in a local database and returns it when the same
  arguments are requested again. `refresh_cache=True` fetches it anew.
* `data.update()` asks the provider for updates and returns a new instance, so assign it:
  `data = data.update()`. It needs the fetch arguments, so it works on instances that were pulled or
  loaded with `vbt.load`, and on local classes it reads new rows from the file instead.
* `update` reuses every fetch argument, including `end`. A fixed `end` caps the update, while a
  relative one, such as `"1 minute ago"`, is evaluated again. Pass `end` to `update` to override it.
* Many providers fetch from the last stored timestamp again to replace a possibly incomplete bar.
  Check the provider's `update_symbol` for its overlap policy, and allow revisions to stored rows.
  Pass `concat=False` to get only the fetched rows. Renaming symbols usually breaks updating, so
  rename only copies used for analysis.
* For collection on a schedule, `vbt.DataUpdater` keeps the instance in memory and
  `vbt.CSVDataSaver` appends each update to files, both through `update_every`. `HDFDataSaver`,
  `SQLDataSaver`, `DuckDBDataSaver`, and `ArcticDBDataSaver` append to the other stores. Pass
  `init_save=True` on the first run of a saver. Appended files contain repeated timestamps, which
  `vbt.CSVData.pull` drops on reading.

For incremental simulations, `data.update(return_meta=True)` returns the new object under `data` and
index labels under `appended`, `revised`, and `removed`. Check bar completeness using the provider's
convention. Process new completed bars in order and choose how to handle revisions. Continue with
`vbt-backtesting` for indicator history and portfolio state, or read the complete loop in
`/tutorials/from-python-to-rust/live/#live-data`.

## Time zones and daylight saving time

* `vbt.settings.data["tz_localize"]` and `["tz_convert"]` both default to `"utc"` for datetime
  indexes. Explicit arguments and provider metadata can override them. Pass `tz="America/New_York"`
  to `pull`, or `tz_convert=...` to `vbt.Data.from_data`, to keep exchange time, or
  `tz_convert=False` to keep the zone of the source. Pass `tz_localize=...` for naive timestamps in
  exchange time, which then stay in that zone.
* Use IANA names such as `"America/New_York"`, which follow daylight saving time. `"EST"` stays at
  UTC-5 all year, offsets such as `"+0500"` are fixed, and names that Pandas cannot parse, such as
  `"ET"`, become fixed offsets with a warning. Check a name with `vbt.timezone(...)`, and build
  timestamps, timedeltas, and offsets as shown in `/cookbook/datetime/`.
* Clock times are read in the zone of the index. Session filters such as
  `close.vbt.xloc["09:30":"16:00"].get()`, `between_time`, and `vbt.dt_nb.hour_nb` in Numba select
  the regular US session only in New York time. In UTC, the session moves by an hour twice a year.
* Resampling to days and weeks bins by midnight in the zone of the index. Convert to the zone of the
  exchange or the trading day before resampling, otherwise UTC days split sessions that cross
  midnight UTC.
* Naive local timestamps are ambiguous around the changes. A repeated hour in autumn raises
  `AmbiguousTimeError` and a skipped hour in spring raises `NonExistentTimeError`. Prefer UTC or
  timestamps with offsets from the source, or localize the index first with Pandas `tz_localize` and
  its `ambiguous` and `nonexistent` arguments.
* Plots show timestamps in the zone of the index, as described in `vbt-plotting`.

## Pitfalls

* `vbt.BinanceData` needs the `python-binance` package, not the unrelated `binance` package.
  `klines_type="futures"` pulls USD-margined futures, and `client_config=dict(tld="us")` connects to
  Binance.US.
* Yahoo Finance is free but lower in quality, rate-limits requests, and may miss bars or label
  hourly bars at half past the hour. Use it for tests and the provider you trade with for results,
  since prices differ between providers.
* The last bar of a resampled series is incomplete when the data ends inside it. Drop it before
  computing features that are compared with complete bars.
* Weekly resampling starts weeks on Monday. Pass an anchored rule such as `"W-SUN"` for weeks that
  start on Sunday.
* VBT reads `"M"` as month start, while Pandas reads it as month end. Convert a rule with
  `vbt.offset` before passing it to a Pandas method.
* For files labeled by close time, convert labels to the corresponding bar opens before using VBT
  bar alignment. Use the source's actual bar bounds, especially for calendar or session bars.
* Indicators on partial higher-timeframe bars, which change within the bar as in TradingView, are
  not built in. Realigned values change only when a higher bar closes.

## Documentation

Read these pages with `get_page` when the task goes beyond this skill:

* `/cookbook/data/`: listing, pulling, caching, saving, loading, updating, and changing data
* `/documentation/data/remote/` and `/documentation/data/local/`: arguments of each provider and
  file format, clients, chunked reading, and updating stored files
* `/documentation/data/management/`: alignment, custom classes, updating, merging, and resampling
* `/documentation/data/scheduling/`: collecting data on a schedule with updaters and savers
* `/tutorials/mtf-analysis/alignment/`: why and how values are realigned between timeframes
* `/tutorials/mtf-analysis/aggregation/`: custom resampling indexes, bounds, and session bars
* `/cookbook/datetime/`: timestamps, time zones, timedeltas, and date offsets
