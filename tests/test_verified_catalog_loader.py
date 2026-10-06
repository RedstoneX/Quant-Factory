"""The existing loader accepts only a verified, fixed local catalog slice."""

import hashlib

from pathlib import Path

import pandas as pd
import pytest

import market_data
from market_data import MarketDataConfig, load_market_data
from market_data.catalog import DataLocations, DatasetManifest, DatasetUnavailableError


def _config() -> MarketDataConfig:
    return MarketDataConfig(
        symbol="MES",
        provider="Databento",
        provider_implementation="verified_local_catalog:futures_MES_5m_databento",
        interval="5m",
        requested_start="2026-02-13T14:30:00Z",
        end_date_policy="fixed 2026-02-13",
        adjusted=False,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=Path("futures/MES/5m/MES_5m_databento.parquet"),
    )


def test_verified_catalog_slice_is_read_only_and_bounded(tmp_path, monkeypatch) -> None:
    index = pd.DatetimeIndex(["2026-02-13T14:30:00Z", "2026-02-13T14:35:00Z"], name="ts_event")
    source = pd.DataFrame(
        {"open": [100.0, 101.0], "high": [101.0, 102.0], "low": [99.0, 100.0], "close": [100.5, 101.5], "volume": [10, 12]},
        index=index,
    )
    path = tmp_path / "MES.parquet"
    source.to_parquet(path)
    manifest = DatasetManifest(
        dataset_id="futures_MES_5m_databento",
        status="validated",
        asset_class="futures",
        symbol="MES",
        provider="Databento",
        timeframe="5m",
        format="parquet",
        canonical_relative_path=_config().cache_path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        size_bytes=path.stat().st_size,
        row_count=2,
        metadata={"earliest_timestamp": index[0].isoformat(), "latest_timestamp": index[-1].isoformat(), "imported_at_utc": "2026-02-14T00:00:00Z"},
    )
    locations = DataLocations(tmp_path, tmp_path, tmp_path, None, None, False)
    monkeypatch.setattr(market_data, "load_data_locations", lambda: locations)
    monkeypatch.setattr(market_data, "load_dataset_manifest", lambda dataset_id, manifest_dir: manifest)
    monkeypatch.setattr(market_data, "verify_dataset_file", lambda selected, local: path)

    result = load_market_data(_config(), now=index[-1], allow_download=False)

    assert result.audit.row_count == 2
    assert list(result.data.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert result.data.index.equals(index)
    with pytest.raises(DatasetUnavailableError, match="exceeds verified catalog coverage"):
        load_market_data(_config(), now=index[-1] + pd.Timedelta(minutes=5), allow_download=False)
