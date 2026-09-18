# Data Source Candidates

This file records potential Quant Factory market-data sources that have not yet been validated for production use.

## Crypto

### CryptoDataDownload

- URL: https://www.cryptodatadownload.com
- Intended use: historical cryptocurrency market data
- Status: candidate; not yet validated

## Foreign exchange

### FX-1-Min

- Source: GitHub repository named `FX-1-Min`
- Intended use: one-minute foreign-exchange data
- Status: candidate; not yet validated

## Required validation before adoption

For each candidate source, verify:

- symbol and venue coverage;
- available date range and update frequency;
- timestamp and timezone conventions;
- missing bars, duplicate rows, and outliers;
- schema consistency and reproducibility;
- licensing, redistribution, and commercial-use restrictions;
- suitability for Quant Factory provenance tracking.
