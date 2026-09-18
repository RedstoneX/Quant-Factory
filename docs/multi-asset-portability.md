# Multi-Asset Strategy Portability and Session Model

> **Historical portability snapshot:** mechanisms and evidence below are
> retained for context. Current dataset status is in [DATA_CATALOG](DATA_CATALOG.md)
> and current scope/status is in [MILESTONES](MILESTONES.md).

## Commitment

Quant Factory will test one approved strategy across multiple compatible instruments and asset classes through configuration, not by rewriting the strategy for every market.

Committed target asset classes:

- US equities and ETFs
- CME futures
- Cryptocurrency
- Foreign exchange

Representative instruments include SPY, MSFT, MES, MNQ, BTC, SOL, USD/CAD, GBP/USD, and EUR/USD.

Architecture support does not mean the required data provider, historical dataset, session convention, or broker integration is already operational. Operational status must always be reported separately from architectural capability.

## Separation of responsibilities

A portable experiment separates:

```text
Strategy logic
+ Instrument
+ Asset class
+ Data provider
+ Timeframe
+ Session definition
+ Execution assumptions
+ Cost model
```

Strategy logic owns the trading hypothesis and signal rules. It must not hard-code one symbol, exchange, provider, timezone, market open, fee schedule, contract multiplier, tick size, currency, or broker unless that restriction is genuinely part of the approved hypothesis.

Instrument, session, timeframe, execution, and cost behavior belong to explicit experiment configuration.

## Instrument profile

Each instrument profile will record, where applicable:

- symbol and display name;
- asset class;
- venue or exchange;
- base and quote currency;
- timezone and trading calendar;
- tick size or price precision;
- contract multiplier and point value;
- continuous or session-based market status;
- supported intervals;
- data provider and provider-specific symbol;
- adjusted-price requirement;
- execution profile;
- session profile.

Asset classes include `equity`, `etf`, `futures`, `crypto`, and `fx`. Validation is conditional because not every field applies to every asset class.

## Session profile

Every session-based experiment uses an explicit approved session profile. A profile records:

- session ID and name;
- timezone;
- session anchor;
- start and end;
- trading-day boundary;
- regular-hours or extended-hours designation;
- overnight handling;
- holiday or calendar reference;
- continuous-market status;
- rationale.

The symbol alone never determines the session silently.

### Equities and ETFs

US equity examples use an exchange calendar and an explicit choice between regular and extended hours. A typical regular session is 09:30 to 16:00 America/New_York, including exchange holidays and half-days.

### CME futures

A futures experiment explicitly selects the intended session, such as Globex or a US regular-trading-hours anchor. Quant Factory will not assume one universal futures open.

### Cryptocurrency

Crypto trades continuously. A session-based strategy therefore requires an approved synthetic anchor such as 00:00 UTC, 09:30 America/New_York, or another documented regional boundary. The anchor is part of the hypothesis.

### Foreign exchange

FX trades nearly continuously during the trading week. A session-based strategy requires an explicit Asia, London, New York, rollover, or other approved session definition, including timezone and daylight-saving handling.

## Timeframe profile

Timeframe is experiment configuration, not duplicated strategy logic. A timeframe profile records:

- interval and bar duration;
- timezone;
- provider-native or resampled status;
- resampling origin and offset;
- incomplete-bar policy;
- required source resolution.

An experiment fails before simulation when the available source resolution cannot represent the requested timeframe or session window accurately.

## Execution and cost profile

Execution assumptions are selected by instrument or experiment. Profiles record:

- commissions or fees;
- slippage and spread assumptions;
- order timing and fill convention;
- minimum tick;
- contract multiplier or point value;
- position sizing and leverage;
- shorting availability;
- market-access limitations;
- liquidity assumptions.

Final production values are added only when the relevant provider or broker milestone is active.

## Approved experiment matrix

The experiment layer will represent:

```text
One approved strategy
× approved instruments
× approved timeframes
× approved session profiles
× approved parameter plan
× approved execution profiles
```

Before execution, Quant Factory will expose:

- instrument count;
- timeframe count;
- session count;
- execution-profile count;
- experiment-variant count;
- parameter-grid count;
- total planned simulations where meaningful;
- unsupported combinations and warnings.

Session anchors and other structural market definitions are not silently treated as ordinary numeric parameters.

## Market portability matrix

| Asset class | Examples | Architecture commitment | Current data status | Session requirement |
|---|---|---|---|---|
| Equities/ETFs | SPY, MSFT | Supported target | Yahoo daily currently; Alpaca planned | Exchange calendar and explicit RTH/extended-hours choice |
| CME futures | MES, MNQ | Supported target | Databento pending | Explicit Globex or approved RTH session |
| Crypto | BTC, SOL | Supported target | CCXT or exchange API pending | Explicit synthetic session anchor for session-based strategies |
| FX | USD/CAD, GBP/USD, EUR/USD | Supported target | Provider not yet implemented | Explicit Asia, London, New York, rollover, or other approved session |

## Validation requirements

The future typed implementation will reject at minimum:

- unknown asset classes;
- missing timezone or provider symbol;
- futures missing required contract metadata;
- FX or crypto missing base and quote currencies;
- continuous markets used by a session-based strategy without an explicit anchor;
- invalid or ambiguous session times;
- timeframe finer than available source data;
- unsupported strategy interval or asset class;
- missing execution profile;
- incompatible adjusted-price requirements;
- silent provider-symbol substitution;
- duplicate experiment combinations;
- unapproved experiment-matrix entries.

## Dashboard commitment

The advanced dashboard will provide approved controls for strategy, instruments, asset classes, timeframes, sessions, parameter values, and execution profiles. It will display variant counts, parameter-grid size, warnings, unsupported combinations, provider dependencies, and approval status before a run begins.

These controls are planned but not yet implemented.

## Current status

Currently operational:

- SPY daily RSI mean reversion;
- Yahoo Finance daily adjusted equity data;
- reusable experiment, validation, screening, out-of-sample, walk-forward, robustness, Monte Carlo, and minimal dashboard foundations.

Not yet operational:

- intraday multi-market data acquisition;
- CME futures data;
- crypto data;
- FX data;
- typed multi-asset/session profiles;
- experiment-matrix execution;
- multi-market dashboard controls.
