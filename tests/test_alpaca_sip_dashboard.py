"""Downloaded SIP data is usable by backtests and visible on the data-health page."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import market_data
from dashboard.health import inspect_catalog
from market_data import MarketDataConfig, load_market_data
from market_data.catalog import DatasetManifest, DatasetUnavailableError, read_verified_bytes
from tests.test_alpaca_sip_provider import DAY_ONE, DAY_TWO, BarServer, locations, provider, stored_path

DATASET_ID = "equities_SPY_1m_alpaca_sip"


def _config(adjusted: bool = True) -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="alpaca",
        provider_implementation=f"verified_local_catalog:{DATASET_ID}",
        interval="1m",
        requested_start="2026-10-12T13:30:00Z",
        end_date_policy="fixed",
        adjusted=adjusted,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=Path("informational/only.parquet"),
    )


def test_backtest_loader_follows_manifest_to_each_new_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "load_data_locations", lambda: locations(tmp_path))
    server = BarServer(DAY_ONE + DAY_TWO[:1], page_size=10)
    provider(tmp_path, server, now="2026-10-13T23:00:00Z").top_up("SPY")
    first = load_market_data(_config(), now=pd.Timestamp("2026-10-13T13:30:00Z"), allow_download=False)
    assert first.data["Open"].tolist() == [101.0, 102.0, 103.0]  # regular session only
    assert first.audit.prices_adjusted is True
    slot_a = stored_path(tmp_path)

    late = {**DAY_TWO[0], "t": "2026-10-13T14:00:00Z", "o": 105.0, "h": 106.0, "l": 104.0, "c": 105.5}
    server.bars = DAY_ONE + DAY_TWO[:1] + [late]
    provider(tmp_path, server).top_up("SPY")
    assert stored_path(tmp_path) != slot_a
    second = load_market_data(_config(), now=pd.Timestamp("2026-10-13T14:00:00Z"), allow_download=False)
    assert second.data["Open"].tolist() == [101.0, 102.0, 103.0, 105.0]
    assert second.audit.cache_path == str(stored_path(tmp_path))


def test_unadjusted_setup_is_refused_for_split_adjusted_library(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "load_data_locations", lambda: locations(tmp_path))
    provider(tmp_path, BarServer(list(DAY_ONE), page_size=10), now="2026-10-12T23:00:00Z").top_up("SPY")
    with pytest.raises(DatasetUnavailableError, match="identity"):
        load_market_data(_config(adjusted=False), now=pd.Timestamp("2026-10-12T19:59:00Z"), allow_download=False)


def test_read_verified_bytes_refuses_bytes_the_manifest_does_not_name(tmp_path):
    path = tmp_path / "x.parquet"
    path.write_bytes(b"new bytes")
    manifest = DatasetManifest(
        "x", "validated", "equity", "SPY", "alpaca", "1m", "parquet", Path("x.parquet"),
        "0" * 64, len(b"new bytes"), 1, {},
    )
    with pytest.raises(DatasetUnavailableError, match="do not match"):
        read_verified_bytes(manifest, path)


def test_data_health_lists_repo_and_downloaded_manifests(tmp_path):
    provider(tmp_path, BarServer(list(DAY_ONE), page_size=10), now="2026-10-12T23:00:00Z").top_up("SPY")
    repo = tmp_path / "manifests"
    repo.mkdir(exist_ok=True)
    config = tmp_path / "locations.toml"
    config.write_text(
        f'[data]\nroot = "{tmp_path / "root"}"\nmanifests = "{repo}"\n'
        f'quarantine = "{tmp_path / "quarantine"}"\n'
        "[policy]\nallow_raw_data_in_repository = false\n",
        encoding="utf-8",
    )
    committed = Path(__file__).resolve().parents[1] / "data" / "manifests" / "equities_SPY_1m_alpaca_iex.json"
    (repo / committed.name).write_text(committed.read_text())
    _, health, errors = inspect_catalog(config_path=config, manifest_dir=repo)
    by_id = {item.manifest.dataset_id: item for item in health}
    assert set(by_id) == {"equities_SPY_1m_alpaca_iex", DATASET_ID}
    assert by_id[DATASET_ID].availability == "Available locally"
    assert errors is None
