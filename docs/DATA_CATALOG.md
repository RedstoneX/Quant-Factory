# Quant Factory Data Catalog

## Purpose

This file is the human-readable source of truth for market datasets available to Quant Factory.

Before downloading, inventorying, importing, or regenerating market data, agents must check:

1. this catalog;
2. `data/manifests/`;
3. the local data-location configuration.

Raw market-data files are not stored in GitHub. GitHub stores only catalog entries, manifests, provenance, schemas, hashes, validation results, and reproducible location rules.

## Canonical local data root

Example local root (`QF_DATA_ROOT`):

```text
/srv/quant-factory/data
```

The actual machine path is configured in the untracked file:

```text
config/data_locations.local.toml
```

Use `config/data_locations.example.toml` as the template.

## Canonical directory structure

```text
/srv/quant-factory/data/
├── futures/
│   ├── MES/
│   │   └── 5m/
│   ├── MNQ/
│   │   └── 5m/
│   └── M2K/
│       └── 5m/
├── equities/
│   └── MSFT/
│       └── 5m/
├── crypto/
│   ├── BTC/
│   └── SOL/
├── manifests/
└── quarantine/
```

Additional assets must follow:

```text
<asset-class>/<symbol>/<timeframe>/
```

Do not create one-off storage locations without updating this policy.

## Import policy

- Preserve original source archives and files.
- Copy validated datasets into the canonical local data root.
- Never move or delete originals during import.
- Compute SHA-256 for every imported file.
- Record provider, symbol, asset class, timeframe, schema, timezone, row count, earliest timestamp, latest timestamp, source path, canonical path, and validation status.
- Store machine-readable manifests under `data/manifests/` in GitHub.
- Store raw files outside GitHub.
- Put ambiguous, damaged, unsupported, or unverifiable files under the local `quarantine/` directory and record why.
- Do not treat a file as usable merely because its filename looks correct.

## Validation states

- `validated`: schema, timestamps, ordering, duplicates, nulls, symbol, timeframe, and provenance checks pass.
- `provisional`: readable and potentially useful, but one or more metadata facts remain unresolved.
- `quarantined`: not approved for experiments.
- `superseded`: retained for provenance but replaced by a preferred dataset.

## Controlled legacy import — 2026-07-07

The named audit Markdown files were not present under the documented Windows
source or inside the archive. Verification therefore used this repository's
audit-derived candidate list, `data/download_report.md`, the preserved archive,
and narrow inspection of the expected extracted paths. Six source datasets are
validated and nine ambiguous, derived, or redundant artifacts are quarantined.

| Asset class | Symbol | Timeframe | Expected provider | Expected legacy path | Status |
|---|---|---:|---|---|---|
| Futures | MES | 5m | Databento | `data/MES/5m/MES_5m_databento.parquet` | Validated |
| Futures | MES | 5m | Databento | `data/MES/5m/MES_5m_databento.csv` | Quarantined — redundant CSV |
| Futures | MNQ | 5m | Databento | `data/MNQ/5m/MNQ_5m_databento.parquet` | Validated |
| Futures | M2K | 5m | Databento | `data/M2K/5m/M2K_5m_databento.parquet` | Validated |
| Equity | MSFT | 5m | Databento | `data/MSFT/5m/MSFT_5m_databento.parquet` | Validated |
| Crypto | BTC/USD | 5m | Alpaca | `data/BTCUSD/5m/alpaca_btc_recent.parquet` | Validated with coverage restrictions |
| Crypto | SOL/USD | 5m | Alpaca | `data/SOLUSD/5m/alpaca_sol_recent.parquet` | Validated with coverage restrictions |
| Crypto | BTC/USDT | 5m | Unresolved | `data/BTCUSD/5m/BTCUSD_5m.parquet` | Quarantined |
| Crypto | BTC/USD features | 5m | Derived/unresolved | `data/features/btcusd_5m_features.parquet` | Quarantined |
| Crypto | BTC/USD test features | 5m | Derived/unresolved | `data/features/btcusd_test_5m_features.parquet` | Quarantined |
| Crypto | SOL/USD merged clean | 5m | Mixed/unresolved | `data/SOLUSD/5m/SOLUSD_clean.parquet` | Quarantined |
| Crypto | SOL/USD merged fixed | 5m | Mixed/unresolved | `data/SOLUSD/5m/SOLUSD_fixed.parquet` | Quarantined — OHLC failures |
| Crypto | SOL/USD merged repaired | 5m | Mixed/unresolved | `data/SOLUSD/5m/SOLUSD_repaired.parquet` | Quarantined |
| Crypto | SOL/USD gap fill | 5m | CCXT exchange unresolved | `data/SOLUSD/5m/ccxt_sol_gapfill.parquet` | Quarantined |
| Crypto | SOL/USD features | 5m | Mixed/derived | `data/features/solusd_5m_features.parquet` | Quarantined |

### `futures_MES_5m_databento`

- Status: validated
- Asset class: futures
- Symbol: MES
- Provider: Databento
- Timeframe: 5m (modal timestamp delta 300 seconds)
- Canonical local path: `futures/MES/5m/MES_5m_databento.parquet`
- Source archive: `quant_factory_FULL_BACKUP_20260217.tar.gz`
- Original source path: `data/MES/5m/MES_5m_databento.parquet`
- Format: Parquet; 8,153,127 bytes
- SHA-256: `fe6bfe4ea3328660e70c2291fc76ea8039249dfb2d5bb35a6390bd8fc7bf4dd1`
- Rows/range/timezone: 476,042; 2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC
- Columns: `open`, `high`, `low`, `close` (double); `volume` (uint64); `ts_event` (UTC timestamp)
- Validation notes: ordered; 0 duplicate timestamps; 0 nulls; 0 OHLC violations
- Manifest: `data/manifests/futures_MES_5m_databento.json`
- Approved uses: intraday and opening-range research after explicit session review
- Contract series: confirmed Databento `MES.c.0`, `stype_in="continuous"`,
  calendar/front-expiry rank zero, original unadjusted prices. Supported
  `ohlcv-1m` was aggregated to UTC left-labeled five-minute bars using first,
  max, min, last, and summed-volume rules. Six roll windows matched 17,334 of
  17,334 sampled OHLCV bars exactly.
- Restrictions: calendar-roll gaps are unadjusted and must not be treated as
  market returns; session rules remain explicit.

### `futures_MNQ_5m_databento`

- Status: validated
- Asset class: futures
- Symbol/provider/timeframe: MNQ; Databento; 5m
- Canonical local path: `futures/MNQ/5m/MNQ_5m_databento.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/MNQ/5m/MNQ_5m_databento.parquet`
- Format/size/SHA-256: Parquet; 9,482,052 bytes; `e3094d83e5e88fe40927183b8c30c37ad4f53283e684caaffc53b5d6d0ca0eff`
- Rows/range/timezone: 475,797; 2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC
- Columns: `open`, `high`, `low`, `close` (double); `volume` (uint64); `ts_event` (UTC timestamp)
- Validation notes: ordered; 0 duplicates; 0 nulls; 0 OHLC violations; modal interval 5m
- Manifest: `data/manifests/futures_MNQ_5m_databento.json`
- Approved uses/restrictions: intraday/ORB after explicit session and roll-method review

### `futures_MES_5m_databento_csv`

- Status: quarantined
- Asset class/symbol/provider/timeframe: futures; MES; Databento; 5m
- Canonical local path: `quarantine/futures/MES/5m/MES_5m_databento.csv`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/MES/5m/MES_5m_databento.csv`
- Format/size/SHA-256: CSV; 28,791,514 bytes; `0da11307b100782ef81d4e811ab09ce3704a8794ff96000c60be77b60af7a4b7`
- Rows/range/timezone: 476,042; 2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC
- Columns: `ts_event`, `open`, `high`, `low`, `close`, `volume`
- Validation notes: ordered; 0 duplicates/nulls/OHLC violations; redundant with canonical Parquet
- Manifest: `data/manifests/futures_MES_5m_databento_csv.json`
- Approved uses: none
- Restrictions: quarantined to prevent duplicate ingestion; use `futures_MES_5m_databento`

### `futures_M2K_5m_databento`

- Status: validated
- Asset class: futures
- Symbol/provider/timeframe: M2K; Databento; 5m
- Canonical local path: `futures/M2K/5m/M2K_5m_databento.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/M2K/5m/M2K_5m_databento.parquet`
- Format/size/SHA-256: Parquet; 7,824,937 bytes; `5336099c3f72fe7a9a7a5aafbf0e17ed4b9dbf6474dd1191bb721043edffeb88`
- Rows/range/timezone: 470,146; 2019-05-05 22:00 UTC through 2026-02-13 21:55 UTC
- Columns: `open`, `high`, `low`, `close` (double); `volume` (uint64); `ts_event` (UTC timestamp)
- Validation notes: ordered; 0 duplicates; 0 nulls; 0 OHLC violations; modal interval 5m
- Manifest: `data/manifests/futures_M2K_5m_databento.json`
- Approved uses/restrictions: intraday/ORB after explicit session and roll-method review

### `equities_MSFT_5m_databento`

- Status: validated
- Asset class: equity
- Symbol/provider/timeframe: MSFT; Databento; 5m
- Canonical local path: `equities/MSFT/5m/MSFT_5m_databento.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/MSFT/5m/MSFT_5m_databento.parquet`
- Format/size/SHA-256: Parquet; 6,336,532 bytes; `9f94d54726580e35df187744b1734adb80c5d6043e8f2eb9211ecf52319828e1`
- Rows/range/timezone: 299,194; 2019-05-01 08:35 UTC through 2026-02-13 23:55 UTC
- Columns: `open`, `high`, `low`, `close` (double); `volume` (uint64); `ts_event` (UTC timestamp)
- Validation notes: ordered; 0 duplicates; 0 nulls; 0 OHLC violations; modal interval 5m
- Manifest: `data/manifests/equities_MSFT_5m_databento.json`
- Approved uses: intraday/ORB after explicit NYSE session filtering
- Restrictions: adjusted-price status unresolved; extended-hours bars are present

### `equities_SPYM_1m_databento_equs_mini`

- Status: validated
- Asset class: equity; asset type: ETF
- Symbol/provider/dataset/schema/timeframe: SPYM; Databento; `EQUS.MINI`; `ohlcv-1m`; 1m
- Canonical local path: `equities/SPYM/1m/SPYM_1m_databento_equs_mini.parquet`
- Source archive/original: none; Databento Historical API `/timeseries.get_range`
- Format/size/SHA-256: Parquet; 944,659 bytes; `0fac9de8cb97568c7ee5ae00532277d960c316989ccd65296c394f0dfa44a5ab`
- Requested coverage: completed NYSE regular sessions from 2025-10-31 through 2026-07-13
- Rows/range/timezone: 53,528; 2025-10-31 13:30 UTC through 2026-07-13 19:59 UTC; UTC timestamps
- Session policy: regular trading hours only; timestamps are included when `market_open <= timestamp < market_close`
- Adjustment setting: raw
- Columns: UTC `timestamp`; double `open`, `high`, `low`, `close`, `volume`
- Coverage notes: 53,528 observed bars across 67,110 possible regular-session minutes; 13,582 absent minutes; 0 missing sessions; no synthetic or forward-filled bars
- Validation notes: ordered; 0 duplicate timestamps; 0 nulls; 0 OHLC violations; 0 negative-volume rows; SPYM symbology resolved for 2025-10-31 through 2026-07-13
- Databento cost: estimated/recorded acquisition cost USD 0.035834848881
- Manifest: `data/manifests/equities_SPYM_1m_databento_equs_mini.json`
- Approved uses: Milestone 21 operational SPYM equity data fixture after explicit Databento entitlement, cost and ticker-history review
- Restrictions: Databento `EQUS.MINI` only; do not substitute another feed silently; SPYM history only; do not splice SPLG bars into this dataset

### `equities_SPY_1m_alpaca_iex`

- Status: validated
- Asset class: equity; asset type: ETF
- Symbol/provider/feed/timeframe: SPY; Alpaca; IEX; 1m
- Canonical local path: `equities/SPY/1m/SPY_1m_alpaca_iex.parquet`
- Source archive/original: none; Alpaca HTTPS endpoint `/v2/stocks/SPY/bars`
- Format/size/SHA-256: Parquet; 79,585 bytes; `96cef375b2e7c3b29c9566cfc5016391a11f762ef744246a286b345f57fa79d3`
- Requested coverage: five most recent fully completed NYSE sessions at acquisition time — 2026-07-01, 2026-07-02, 2026-07-06, 2026-07-07, and 2026-07-08
- Rows/range/timezone: 1,950; 2026-07-01 13:30 UTC through 2026-07-08 19:59 UTC; UTC timestamps
- Session policy: regular trading hours only; timestamps are included when `market_open <= timestamp < market_close`
- Adjustment setting: raw
- Columns: UTC `timestamp`; double `open`, `high`, `low`, `close`, `volume`, `vwap`; nullable integer `trade_count`
- Validation notes: ordered; 0 duplicate timestamps; 0 nulls; 0 OHLC violations; 0 missing sessions; 0 missing regular-session bars
- Manifest: `data/manifests/equities_SPY_1m_alpaca_iex.json`
- Approved uses: controlled SPY one-minute IEX research after explicit feed review
- Restrictions: IEX feed only; do not treat as SIP consolidated tape; regular trading hours only; raw adjustment setting

### `crypto_BTC_5m_alpaca`

- Status: validated
- Asset class/symbol/provider/timeframe: crypto; BTC/USD; Alpaca; 5m
- Canonical local path: `crypto/BTC/5m/alpaca_btc_recent.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/BTCUSD/5m/alpaca_btc_recent.parquet`
- Format/size/SHA-256: Parquet; 10,760,613 bytes; `346c88d763f0d429ebe75f129e243f675e04ccb0eac30e8c4b46c83bce370000`
- Rows/range/timezone: 235,654; 2022-07-01 00:00 UTC through 2026-02-12 22:35 UTC
- Columns: UTC `timestamp`; double OHLCV and `vwap`; int64 `trade_count`
- Validation notes: ordered; 0 duplicates/nulls/OHLC violations; modal interval 5m
- Manifest: `data/manifests/crypto_BTC_5m_alpaca.json`
- Approved uses: gap-aware crypto research; ORB only with an approved synthetic anchor
- Restrictions: source report records 306 gaps over 15 minutes and 48% zero-volume bars

### `crypto_SOL_5m_alpaca`

- Status: validated
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; Alpaca; 5m
- Canonical local path: `crypto/SOL/5m/alpaca_sol_recent.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/SOLUSD/5m/alpaca_sol_recent.parquet`
- Format/size/SHA-256: Parquet; 10,981,345 bytes; `95298bc87f4eb186f4c6f34178a745e6906789ce7f155d3e0e9c8605a692642a`
- Rows/range/timezone: 246,274; 2021-01-01 06:05 UTC through 2026-02-11 11:05 UTC
- Columns: UTC `timestamp`; double OHLCV and `vwap`; int64 `trade_count`
- Validation notes: ordered; 0 duplicates/nulls/OHLC violations; modal interval 5m
- Manifest: `data/manifests/crypto_SOL_5m_alpaca.json`
- Approved uses: segmented gap-aware research; ORB only with an approved synthetic anchor
- Restrictions: source report records a 418-day gap and 31% zero-volume bars

### `crypto_BTCUSDT_5m_unknown`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; BTC/USDT; unresolved; 5m
- Canonical local path: `quarantine/crypto/BTC/5m/BTCUSD_5m.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/BTCUSD/5m/BTCUSD_5m.parquet`
- Format/size/SHA-256: Parquet; 10,956,474 bytes; `1aba46d1d0d0a2ccbf559fdccd9b924a37df1962d3535933a1bd922e5a58bb1b`
- Rows/range/timezone: 209,088; 2020-07-27 to 2022-07-27; unresolved naive timestamps
- Columns: `unix`, `datetime`, `symbol`, OHLC, BTC/USDT volumes, `tradecount`
- Validation notes: ordered; 0 duplicates/nulls/OHLC violations; contents identify BTC/USDT
- Manifest: `data/manifests/crypto_BTCUSDT_5m_unknown.json`
- Approved uses: none
- Restrictions: provider, timezone, and provenance must be verified

### `crypto_BTC_5m_alpaca_features`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; BTC/USD; derived from Alpaca; 5m
- Canonical local path: `quarantine/crypto/BTC/5m/btcusd_5m_features.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/features/btcusd_5m_features.parquet`
- Format/size/SHA-256: Parquet; 25,086,151 bytes; `ff842c326ef3e65ecefa315acfc7bab6a9bfa1c8f89fcd973e7ac24e091b329d`
- Rows/range/timezone: 235,654; 2022-07-01 to 2026-02-12; UTC
- Columns: OHLCV/trades/VWAP plus z-score, ATR, median ATR, and returns features
- Validation notes: ordered; 0 duplicates/OHLC violations; expected warm-up nulls; feature lineage unresolved
- Manifest: `data/manifests/crypto_BTC_5m_alpaca_features.json`
- Approved uses: none
- Restrictions: reproduce and approve features from the validated raw source

### `crypto_BTC_5m_alpaca_features_test`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; BTC/USD; derived from Alpaca; 5m
- Canonical local path: `quarantine/crypto/BTC/5m/btcusd_test_5m_features.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/features/btcusd_test_5m_features.parquet`
- Format/size/SHA-256: Parquet; 1,145,835 bytes; `d4d7d804a96a8227e86b78b9601e5660e741498817e551724dbbac94557e7e85`
- Rows/range/timezone: 10,000; 2025-12-13 to 2026-02-12; UTC
- Columns: OHLCV/trades/VWAP plus z-score, ATR, median ATR, and returns features
- Validation notes: readable ordered test subset; 0 duplicates/OHLC violations; subset provenance unresolved
- Manifest: `data/manifests/crypto_BTC_5m_alpaca_features_test.json`
- Approved uses: none
- Restrictions: not an approved canonical market dataset

### `crypto_SOL_5m_merged_clean`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; mixed Alpaca/CCXT; 5m
- Canonical local path: `quarantine/crypto/SOL/5m/SOLUSD_clean.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/SOLUSD/5m/SOLUSD_clean.parquet`
- Format/size/SHA-256: Parquet; 14,007,431 bytes; `525b824f84b9c0afbb989ea0edde23ea7b83d732f2b66b389a6f292e56039a90`
- Rows/range/timezone: 366,877; 2021-01-01 to 2026-02-11; unresolved naive timestamps
- Columns: OHLCV, `trade_count`, `vwap`, `timestamp`
- Validation notes: ordered; 0 duplicates/OHLC violations; 123,264 null trade-count/VWAP rows
- Manifest: `data/manifests/crypto_SOL_5m_merged_clean.json`
- Approved uses: none
- Restrictions: merge lineage, source precedence, and timezone unresolved

### `crypto_SOL_5m_merged_fixed`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; mixed Alpaca/CCXT; 5m
- Canonical local path: `quarantine/crypto/SOL/5m/SOLUSD_fixed.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/SOLUSD/5m/SOLUSD_fixed.parquet`
- Format/size/SHA-256: Parquet; 12,231,648 bytes; `05531a97c218010239bf8eb71c4f97b64b46e09685379ead9cb8847b9297bc9d`
- Rows/range/timezone: 366,877; 2021-01-01 to 2026-02-11; unresolved naive timestamps
- Columns: OHLCV, `trade_count`, `vwap`, `timestamp`
- Validation notes: ordered; 0 duplicates; 21,863 OHLC consistency violations
- Manifest: `data/manifests/crypto_SOL_5m_merged_fixed.json`
- Approved uses: none
- Restrictions: OHLC failures prohibit research use

### `crypto_SOL_5m_merged_repaired`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; mixed Alpaca/CCXT; 5m
- Canonical local path: `quarantine/crypto/SOL/5m/SOLUSD_repaired.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/SOLUSD/5m/SOLUSD_repaired.parquet`
- Format/size/SHA-256: Parquet; 12,285,655 bytes; `47a0162e4702fd8868eb02821c660c96200e5c86cefe7daaaa8615df959faa08`
- Rows/range/timezone: 366,877; 2021-01-01 to 2026-02-11; unresolved naive timestamps
- Columns: OHLCV, `trade_count`, `vwap`, `timestamp`
- Validation notes: ordered; 0 duplicates/OHLC violations; 123,311 null trade-count/VWAP rows
- Manifest: `data/manifests/crypto_SOL_5m_merged_repaired.json`
- Approved uses: none
- Restrictions: repair rules, merge lineage, source precedence, and timezone unresolved

### `crypto_SOL_5m_ccxt_gapfill`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; CCXT exchange unresolved; 5m
- Canonical local path: `quarantine/crypto/SOL/5m/ccxt_sol_gapfill.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/SOLUSD/5m/ccxt_sol_gapfill.parquet`
- Format/size/SHA-256: Parquet; 2,788,404 bytes; `c66952ec248e0dfc679a99528fb5897da17562360aa9f6be22174986c67a8a15`
- Rows/range/timezone: 123,264; 2023-07-01 to 2024-08-31; UTC
- Columns: UTC `timestamp` and double OHLCV
- Validation notes: complete 5m sequence; ordered; 0 duplicates/nulls/OHLC violations
- Manifest: `data/manifests/crypto_SOL_5m_ccxt_gapfill.json`
- Approved uses: none
- Restrictions: exchange/market identity unresolved; cross-provider merging is not approved

### `crypto_SOL_5m_features`

- Status: quarantined
- Asset class/symbol/provider/timeframe: crypto; SOL/USD; mixed/derived; 5m
- Canonical local path: `quarantine/crypto/SOL/5m/solusd_5m_features.parquet`
- Source archive/original: `quant_factory_FULL_BACKUP_20260217.tar.gz`; `data/features/solusd_5m_features.parquet`
- Format/size/SHA-256: Parquet; 35,373,030 bytes; `b3bca16aaa6024725969e609a333209c1d9319e02ede73d80ded84526422efde`
- Rows/range/timezone: 366,877; 2021-01-01 to 2026-02-11; UTC
- Columns: OHLCV/trades/VWAP plus z-score, ATR, median ATR, and returns features
- Validation notes: ordered; 0 duplicates/OHLC violations; source-specific and warm-up nulls
- Manifest: `data/manifests/crypto_SOL_5m_features.json`
- Approved uses: none
- Restrictions: merge/repair and feature-generation lineage unresolved

## Catalog entry format

After local verification, add one section per dataset using this format:

```markdown
### `<dataset_id>`

- Status:
- Asset class:
- Symbol:
- Provider:
- Timeframe:
- Canonical local path:
- Source archive:
- Original source path:
- Format:
- SHA-256:
- Row count:
- Earliest timestamp:
- Latest timestamp:
- Timezone:
- Columns:
- Validation notes:
- Manifest:
- Approved uses:
- Restrictions:
```

## Agent rule

The existence of a catalog entry does not imply that data is present on every machine. Agents must resolve the configured local root and verify the file hash before use.
