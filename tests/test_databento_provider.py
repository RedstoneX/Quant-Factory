"""Deterministic tests for Databento OHLCV acquisition."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from market_data.catalog import DataLocations
from market_data.providers.databento import (
    DatabentoDataError,
    DatabentoOhlcvProvider,
    DatabentoOhlcvRequest,
    completed_sessions_from_start,
    expected_regular_minutes,
)


class FakeStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def to_df(self, **_: Any) -> pd.DataFrame:
        return self.frame


class FakeMetadata:
    def __init__(self, cost: float) -> None:
        self.cost = cost
        self.cost_calls: list[dict[str, Any]] = []

    def get_cost(self, **kwargs: Any) -> float:
        self.cost_calls.append(dict(kwargs))
        return self.cost


class FakeSymbology:
    def __init__(self, recognized: bool = True) -> None:
        self.recognized = recognized
        self.calls: list[dict[str, Any]] = []

    def resolve(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        if not self.recognized:
            return {
                "result": {},
                "symbols": ["SPYM"],
                "partial": [],
                "not_found": ["SPYM"],
                "status": 0,
            }
        return {
            "result": {
                "SPYM": [{"d0": "2025-10-31", "d1": "2026-07-09", "s": "19482"}]
            },
            "symbols": ["SPYM"],
            "partial": [],
            "not_found": [],
            "status": 0,
        }


class FakeTimeseries:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.calls: list[dict[str, Any]] = []

    def get_range(self, **kwargs: Any) -> FakeStore:
        self.calls.append(dict(kwargs))
        return FakeStore(self.frame)


class FakeDatabentoClient:
    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        cost: float = 0.05,
        recognized: bool = True,
    ) -> None:
        self.metadata = FakeMetadata(cost)
        self.symbology = FakeSymbology(recognized)
        self.timeseries = FakeTimeseries(frame)


@pytest.fixture
def locations(tmp_path: Path) -> DataLocations:
    return DataLocations(
        root=tmp_path / "root",
        manifests=tmp_path / "root" / "manifests",
        quarantine=tmp_path / "root" / "quarantine",
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )


def _request() -> DatabentoOhlcvRequest:
    return DatabentoOhlcvRequest(
        symbol="SPYM",
        dataset="EQUS.MINI",
        schema="ohlcv-1m",
        stype_in="raw_symbol",
        asset_class="equity",
        asset_type="ETF",
        timeframe="1m",
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        session_policy="regular_trading_hours_only",
        adjustment="raw",
        coverage_start="2026-07-08",
        coverage_end_policy="latest_fully_completed_nyse_session",
        dataset_id="equities_SPYM_1m_databento_equs_mini",
        filename="SPYM_1m_databento_equs_mini.parquet",
        fund_name="State Street SPDR Portfolio S&P 500 ETF",
        ticker_history={
            "former_symbol": "SPLG",
            "current_symbol": "SPYM",
            "effective_date": "2025-10-31",
        },
        corporate_action_policy="Preserve raw provider bars.",
        cache_policy="Checksum-gated refresh.",
        approved_uses=("SPYM fixture",),
        restrictions=("EQUS.MINI only",),
    )


def _frame_for_schedule(schedule: pd.DataFrame, *, drop_last: bool = False) -> pd.DataFrame:
    timestamps = expected_regular_minutes(schedule)
    if drop_last:
        timestamps = timestamps[:-1]
    rows = []
    for index, timestamp in enumerate(timestamps, start=1):
        price = 70.0 + index / 100
        rows.append(
            {
                "ts_event": timestamp,
                "open": price,
                "high": price + 0.2,
                "low": price - 0.2,
                "close": price + 0.05,
                "volume": 1000 + index,
                "symbol": "SPYM",
            }
        )
    return pd.DataFrame(rows).set_index("ts_event")


def _schedule(request: DatabentoOhlcvRequest) -> pd.DataFrame:
    return completed_sessions_from_start(
        request,
        now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
    )


def test_databento_acquisition_writes_valid_manifest(
    locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = _request()
    schedule = _schedule(request)
    client = FakeDatabentoClient(_frame_for_schedule(schedule))
    result = DatabentoOhlcvProvider(client=client, locations=locations).acquire_from_start(
        request,
        now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
        repo_manifest_dir=tmp_path,
    )

    assert client.metadata.cost_calls[0]["dataset"] == "EQUS.MINI"
    assert client.timeseries.calls[0]["schema"] == "ohlcv-1m"
    assert result.manifest["status"] == "validated"
    assert result.manifest["provider"] == "databento"
    assert result.manifest["dataset"] == "EQUS.MINI"
    assert result.manifest["schema"] == "ohlcv-1m"
    assert result.manifest["row_count"] == 780
    assert result.manifest["missing_session_count"] == 0
    assert result.manifest["duplicate_timestamp_count"] == 0
    assert result.manifest["negative_volume_count"] == 0
    assert result.manifest["synthetic_bar_count"] == 0
    assert result.manifest["symbol_resolution"]["result"]["SPYM"]
    assert len(result.manifest["sha256"]) == 64
    assert result.parquet_path.is_file()


def test_databento_cost_gate_prevents_download(
    locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = _request()
    schedule = _schedule(request)
    client = FakeDatabentoClient(_frame_for_schedule(schedule), cost=2.0)
    with pytest.raises(DatabentoDataError, match="Estimated Databento cost"):
        DatabentoOhlcvProvider(client=client, locations=locations).acquire_from_start(
            request,
            now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
            repo_manifest_dir=tmp_path,
        )
    assert client.timeseries.calls == []


def test_databento_symbol_resolution_is_required(
    locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = _request()
    schedule = _schedule(request)
    client = FakeDatabentoClient(_frame_for_schedule(schedule), recognized=False)
    result = DatabentoOhlcvProvider(client=client, locations=locations).acquire_from_start(
        request,
        now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
        repo_manifest_dir=tmp_path,
    )
    assert result.manifest["status"] == "provisional"


def test_databento_cache_reuse_requires_checksum(
    locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = _request()
    schedule = _schedule(request)
    first_client = FakeDatabentoClient(_frame_for_schedule(schedule))
    first = DatabentoOhlcvProvider(
        client=first_client,
        locations=locations,
    ).acquire_from_start(
        request,
        now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
        repo_manifest_dir=tmp_path,
    )

    second_client = FakeDatabentoClient(_frame_for_schedule(schedule))
    second = DatabentoOhlcvProvider(
        client=second_client,
        locations=locations,
    ).acquire_from_start(
        request,
        now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
        repo_manifest_dir=tmp_path,
    )
    assert second.cache_reused is True
    assert second_client.timeseries.calls == []

    first.parquet_path.write_bytes(b"tampered")
    with pytest.raises(DatabentoDataError, match="SHA-256"):
        DatabentoOhlcvProvider(
            client=FakeDatabentoClient(_frame_for_schedule(schedule)),
            locations=locations,
        ).acquire_from_start(
            request,
            now=pd.Timestamp("2026-07-09 17:00", tz=request.market_timezone),
            repo_manifest_dir=tmp_path,
        )
