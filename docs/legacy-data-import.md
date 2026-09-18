# Controlled Legacy Market-Data Import

## Status

Approved supporting task for Milestone 15.

This task creates the reusable local market-data library required by current and future strategy research. It does not implement or backtest a strategy.

## Objective

Import all useful market datasets already identified in the legacy Quant Factory backup into the canonical local data root, validate them, and produce durable manifests and catalog entries.

## Known prior work

A previous Codex audit already inspected the legacy backup. Do not repeat a broad inventory.

Known audit artifacts:

- `Quant_Factory_Legacy_Backup_Audit_2026-07-02.md`
- `CODEX_Controlled_Legacy_Data_Import_Prompt.md`
- `quant_factory_FULL_BACKUP_20260217.tar.gz`

Known expected candidates:

- `data/MES/5m/MES_5m_databento.parquet`
- `data/MNQ/5m/MNQ_5m_databento.parquet`
- `data/M2K/5m/M2K_5m_databento.parquet`
- `data/MSFT/5m/MSFT_5m_databento.parquet`
- BTC datasets identified by the audit
- SOL datasets identified by the audit
- `data/download_report.md`

Use the prior audit and prompt if found. Search narrowly for these named artifacts and expected paths. Do not perform a new filesystem-wide data inventory.

## Canonical storage

Default root:

```text
/srv/quant-factory/data
```

Directory rule:

```text
<asset-class>/<symbol>/<timeframe>/
```

Examples:

```text
futures/MES/5m/
futures/MNQ/5m/
futures/M2K/5m/
equities/MSFT/5m/
crypto/BTC/<timeframe>/
crypto/SOL/<timeframe>/
```

## Safety rules

- Preserve all originals.
- Copy files; never move or delete source files or archives.
- Never modify the legacy archive.
- Never commit raw market data.
- Never infer provider, symbol, timeframe, timezone, or date range solely from a filename.
- Quarantine unreadable, inconsistent, ambiguous, or unsupported datasets.
- Do not download replacement data during this task.
- Do not implement or run ORB or any other strategy.

## Validation requirements

For every candidate:

- verify readable format;
- calculate SHA-256;
- record file size;
- inspect schema and data types;
- identify timestamp field or index;
- record row count;
- record earliest and latest timestamp;
- determine timezone or mark it unresolved;
- verify chronological ordering;
- count duplicate timestamps;
- record null counts;
- inspect OHLC consistency where applicable;
- verify apparent bar interval from timestamps rather than filename alone;
- record provenance and original path;
- assign `validated`, `provisional`, or `quarantined` status;
- list approved uses and restrictions.

## Repository outputs

For every imported dataset:

1. Add a JSON manifest under `data/manifests/`.
2. Update `docs/DATA_CATALOG.md` with factual metadata.
3. Do not include machine-specific absolute paths in committed manifests.
4. Use paths relative to the configured local data root.

## Local configuration

Create the untracked file:

```text
config/data_locations.local.toml
```

Use `config/data_locations.example.toml` as its basis and record the actual source archive/extracted root used for this import.

## Completion criteria

- The canonical local root exists.
- Every known candidate from the prior audit is either imported or explicitly accounted for.
- Original files remain unchanged.
- Imported files have SHA-256 manifests.
- Catalog and manifests agree.
- MES 5-minute data is either validated and locatable or clearly blocked with a factual reason.
- Raw data is not tracked by Git.
- Relevant tests pass.
- Full test suite passes before commit.
- One commit is pushed to `main` with the factual import records and any required loader/test changes.
