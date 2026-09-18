# Data Sources and Acquisition Policy

## Intended provider roles

| Asset class | Preferred provider |
|---|---|
| Daily US equity research | Yahoo Finance initially |
| US equities historical and recent data | Alpaca |
| US listed-options historical data | Alpaca initially |
| CME futures historical data | Databento |
| Cryptocurrency spot and derivatives | CCXT or exchange-specific APIs |

Alpaca is intended for equities and listed-options data. CCXT is for
cryptocurrency exchanges and crypto derivatives, not general US equity or
listed-options data. Databento is the preferred CME futures provider. Provider
choice remains milestone-specific and must be validated before production use.
Data from different providers must not be merged silently.

## Current provider

| Field | Value |
|---|---|
| Provider | Yahoo Finance |
| Implementation | `vectorbtpro.YFData` |
| Current use | Daily SPY research |
| Adjustment | Explicit `auto_adjust=True` |
| Default historical start | `2016-01-01` |
| End policy | Latest fully completed exchange session returned by the provider |

## Planned Databento use

Databento is the preferred provider for future CME futures research. Initial
intended datasets are:

- MES 5-minute history
- MNQ 5-minute history
- M2K 5-minute history
- potentially MYM 5-minute history when acquired or verified

Known preferred conventions are:

```text
Dataset: GLBX.MDP3
Schema: ohlcv-5m
Use: historical data only during the research phase
```

This plan does not claim that these datasets have been downloaded or verified.

## Planned Alpaca use

Alpaca is the preferred provider for US equities historical and recent data and
the initial provider for US listed-options historical data. Coverage,
adjustment behavior, licensing, authentication, and implementation APIs must be
verified during the relevant provider milestone before production use.

### SPYM operational equity contract

Milestone 21A initially selected Alpaca IEX, but Milestone 21B evidence showed
that feed was too sparse for the SPYM fixture. The approved SPYM historical
source is now Databento `EQUS.MINI` with schema `ohlcv-1m`. Entitlement and cost
inspection confirmed SPYM availability from 2025-10-31 onward, with an
estimated bounded acquisition cost below USD $1. The canonical source
resolution is one minute.

SPYM is the current ticker for the same fund formerly traded as SPLG. State
Street made the ticker and fund-name change effective before the market opened
on 2025-10-31. The bounded SPYM dataset therefore starts on 2025-10-31 and ends
at the latest fully completed NYSE session. SPLG history is not silently spliced
into SPYM history; any predecessor history requires its own manifest, checksum,
symbol mapping and explicit lineage.

The contract uses the NYSE calendar, regular-session minute starts only
(`market_open <= timestamp < market_close`), and UTC storage. Prices remain raw
unless Databento metadata proves a different explicit adjustment treatment.
Splits, cash dividends and other corporate actions are recorded and reviewed
separately; adjusted and raw data are never mixed silently.

Acquisition may refresh only after the existing Parquet file matches its
manifest SHA-256. A cache without a manifest, a checksum mismatch or an
identity mismatch is never overwritten or reused. No synthetic or forward-filled
bars are generated. The manifest reports observed Databento bars versus possible
regular-session NYSE minutes. Missing exchange sessions, duplicate timestamps,
null/non-finite or non-positive price data, negative volume, OHLC violations,
out-of-session bars, missing SPYM symbology evidence, and checksum failures make
the dataset unsuitable. Until Milestone 21B creates and validates that manifest,
the dashboard reports the dataset unavailable and fail-closed.

Primary references: State Street's [official ticker-change notice](https://www.ssga.com/us/en/intermediary/library-content/products/fund-docs/etfs/us/information-schedules/ap-notice/notice-to-aps-ticker-fund-name-and-benchmark-index-name-changes-10-31-25.pdf),
Alpaca's [historical-data guide](https://alpaca.markets/learn/fetch-historical-data),
and Alpaca's [market-data feed FAQ](https://docs.alpaca.markets/us/docs/market-data-faq).

### SCHX/SCHB forward-test instrument verification

Milestone 21E selected SCHX as the future broad-market whole-share paper and
micro-live execution fixture. SCHB remains a close comparison and portability
reference. The selection does not approve strategy profitability research,
paper orders or live orders.

Both candidates are Schwab ETFs listed on NYSE Arca with 0.030% expense ratios,
November 2009 inception, post-split prices near USD $29, and 0.03% 30-day
median bid/ask spread evidence. Schwab identifies SCHX as the Schwab U.S.
Large-Cap ETF tracking the Dow Jones U.S. Large-Cap Total Stock Market Index;
it reported USD 72.26B in net assets, 754 holdings, 22,352,588 same-day shares
traded on 2026-07-14, and a 3-for-1 split effective October 10, 2024 with
post-split trading beginning October 11, 2024. Schwab identifies SCHB as the
Schwab U.S. Broad Market ETF tracking the Dow Jones U.S. Broad Stock Market
Index; it reported USD 43.31B in net assets, 2,356 holdings, 7,209,159 same-day
shares traded on 2026-07-14, and the same 3-for-1 split treatment.

MarketWatch current quote evidence reported 65-day average volume of 13.45M
shares for SCHX and 9.09M shares for SCHB on 2026-07-14. This favors SCHX
operationally while leaving SCHB sufficiently liquid for comparison.

Databento account metadata confirmed `EQUS.MINI` has usable data from
2023-03-28 through 2026-07-14 and supports `trades`, `tbbo`, `mbp-1`, `bbo-1s`,
`bbo-1m`, `ohlcv-1s`, `ohlcv-1m`, `ohlcv-1h`, `ohlcv-1d` and `definition`.
The `ohlcv-1m` fields include `ts_event`, `open`, `high`, `low`, `close` and
`volume`. Publisher metadata identifies venue `EQUS`, "Databento US Equities
Mini", rather than a single-exchange IEX-style feed.

Databento symbology resolved SCHX to instrument id `14318` and SCHB to
instrument id `14296` for 2023-03-28 through 2026-07-13 with no partial or
missing mappings. Estimated `ohlcv-1m` costs for that usable range were
USD $0.100031912327 for SCHX, USD $0.082242786884 for SCHB and
USD $0.182274699211 for both symbols together. Milestone 21E did not download a
full SCHX or SCHB historical research dataset.

Primary references: Schwab Asset Management's official [SCHX](https://www.schwabassetmanagement.com/products/schx)
and [SCHB](https://www.schwabassetmanagement.com/products/schb) fund pages,
MarketWatch current quote pages for [SCHX](https://www.marketwatch.com/investing/fund/schx)
and [SCHB](https://www.marketwatch.com/investing/fund/schb), and Databento
Historical API metadata and cost estimates captured during Milestone 21E.

## Planned cryptocurrency use

CCXT or exchange-specific APIs are planned for cryptocurrency spot and
derivatives data. Each dataset must identify its exchange, market type, symbol,
quote currency, and provider. CCXT is not a source for general US equity or
listed-options data.

## Existing legacy datasets

Legacy or previously downloaded files may include:

- `MES_5m_databento.parquet`
- `MNQ_5m_databento.parquet`
- `M2K_5m_databento.parquet`
- `MSFT_5m_databento.parquet`
- `BTCUSD_5m.parquet`
- `SOLUSD_clean.parquet`
- `alpaca_btc_recent.parquet`
- `alpaca_sol_recent.parquet`
- `ccxt_sol_gapfill.parquet`

These are data assets, not trusted backtest results. They remain quarantined
until independently validated, must not be committed, and their original files
must remain unchanged. Import requires provenance, file hashes, timezone
validation, duplicate checks, OHLC and volume validation, and manifest records.
Old strategy code and claimed results associated with a legacy archive are not
automatically trusted.

## Dataset identity rules

- Provider, venue, symbol, quote currency, interval, adjustment status, and contract methodology are part of dataset identity.
- Never merge BTC/USD with BTC/USDT or SOL/USD with SOL/USDT.
- Never merge crypto venues without explicit normalization and reconciliation.
- Never silently combine adjusted and unadjusted equities.
- Never silently combine continuous futures with individual contracts.
- Futures roll methodology must be explicit.
- Every dataset must retain provenance.
- Data from different providers must not be merged silently.

## Storage policy

Planned layout:

```text
data/
    cache/
    quarantine/
    raw/
    validated/
    manifests/
```

Downloaded and imported market data remains Git-ignored. Small schemas,
manifests, validation summaries, and configurations may be tracked when they
contain no proprietary data or secrets. Parquet is preferred for validated
intraday history. CSV is reserved for small human-readable exports rather than
primary large-dataset storage.

## Acquisition order

1. Continue Yahoo SPY daily validation.
2. Inventory and validate existing quarantined datasets.
3. Add Alpaca acquisition for US equities and listed-options during dedicated milestones.
4. Add Databento acquisition for MES and MNQ 5-minute history.
5. Add M2K and MYM where data is available.
6. Add carefully separated crypto datasets through CCXT or exchange-specific APIs.
7. Add live or recent broker feeds only after the historical research pipeline is stable.

## Provider acceptance criteria

Every provider integration records:

- provider and implementation;
- dataset or feed name;
- symbol and venue;
- interval and timezone;
- adjustment status;
- requested and actual date ranges;
- row count, missing values, duplicates, and unexpected gaps;
- warnings;
- cache or file path;
- acquisition time;
- checksum or fingerprint where appropriate;
- known license or usage restrictions.
