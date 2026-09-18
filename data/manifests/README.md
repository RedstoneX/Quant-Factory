# Dataset Manifests

This directory stores machine-readable metadata for local market-data files.

Raw market data must never be committed here.

Each imported dataset gets one JSON manifest named:

```text
<asset_class>_<symbol>_<timeframe>_<provider>.json
```

Example:

```text
futures_MES_5m_databento.json
```

## Required fields

```json
{
  "dataset_id": "futures_MES_5m_databento",
  "status": "validated",
  "asset_class": "futures",
  "symbol": "MES",
  "provider": "Databento",
  "timeframe": "5m",
  "format": "parquet",
  "canonical_relative_path": "futures/MES/5m/MES_5m_databento.parquet",
  "source_archive": "quant_factory_FULL_BACKUP_20260217.tar.gz",
  "original_source_path": "data/MES/5m/MES_5m_databento.parquet",
  "sha256": "",
  "size_bytes": 0,
  "row_count": 0,
  "earliest_timestamp": "",
  "latest_timestamp": "",
  "timezone": "",
  "columns": [],
  "duplicate_timestamp_count": 0,
  "null_counts": {},
  "monotonic_increasing": false,
  "validation_notes": [],
  "approved_uses": [],
  "restrictions": [],
  "imported_at_utc": "",
  "validated_by": ""
}
```

## Rules

- `canonical_relative_path` is relative to the configured local data root.
- Do not place machine-specific absolute paths in committed manifests.
- Use SHA-256 to verify that the local file matches the cataloged dataset.
- A manifest with `status` other than `validated` must not be used silently in an experiment.
- Update `docs/DATA_CATALOG.md` whenever a manifest is added, replaced, quarantined, or superseded.
