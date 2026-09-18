"""Deterministic tests for Alpaca historical-bar acquisition."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from market_data.catalog import DataLocations
from market_data.providers.alpaca import (
    ALPACA_DATA_HOST,
    AlpacaAcquisitionResult,
    AlpacaBarsRequest,
    AlpacaCredentials,
    AlpacaDataError,
    AlpacaHistoricalBarsProvider,
    expected_regular_minutes,
    recent_completed_sessions,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any],
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "params": dict(params),
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("unexpected Alpaca HTTP request")
        return self.responses.pop(0)


@pytest.fixture
def alpaca_locations(tmp_path: Path) -> DataLocations:
    return DataLocations(
        root=tmp_path / "root",
        manifests=tmp_path / "root" / "manifests",
        quarantine=tmp_path / "root" / "quarantine",
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )


@pytest.fixture
def alpaca_request() -> AlpacaBarsRequest:
    return AlpacaBarsRequest(completed_session_count=1)


def _provider(
    client: FakeClient,
    locations: DataLocations,
) -> AlpacaHistoricalBarsProvider:
    return AlpacaHistoricalBarsProvider(
        credentials=AlpacaCredentials("key", "secret"),
        locations=locations,
        client=client,
        max_retries=1,
        backoff_seconds=0,
    )


def _one_session_schedule(request: AlpacaBarsRequest) -> pd.DataFrame:
    return recent_completed_sessions(
        request,
        now=pd.Timestamp("2026-07-08 17:00", tz=request.market_timezone),
    )


def _schedule_at(request: AlpacaBarsRequest, now: str) -> pd.DataFrame:
    return recent_completed_sessions(
        request,
        now=pd.Timestamp(now, tz=request.market_timezone),
    )


def _bars_for_schedule(schedule: pd.DataFrame) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for i, timestamp in enumerate(expected_regular_minutes(schedule), start=1):
        value = 600.0 + i / 100
        bars.append(
            {
                "t": timestamp.isoformat().replace("+00:00", "Z"),
                "o": value,
                "h": value + 0.25,
                "l": value - 0.25,
                "c": value + 0.05,
                "v": 1000 + i,
                "n": 10 + i,
                "vw": value + 0.02,
            }
        )
    return bars


def _responses_for_schedule(schedule: pd.DataFrame) -> list[FakeResponse]:
    return [
        FakeResponse(200, {"bars": _bars_for_schedule(schedule.loc[[session]])})
        for session in schedule.index
    ]


def _acquire(
    provider: AlpacaHistoricalBarsProvider,
    request: AlpacaBarsRequest,
    repo_manifest_dir: Path,
) -> AlpacaAcquisitionResult:
    return provider.acquire_recent_sessions(
        request,
        now=pd.Timestamp("2026-07-08 17:00", tz=request.market_timezone),
        repo_manifest_dir=repo_manifest_dir,
    )


def _acquire_at(
    provider: AlpacaHistoricalBarsProvider,
    request: AlpacaBarsRequest,
    repo_manifest_dir: Path,
    now: str,
) -> AlpacaAcquisitionResult:
    return provider.acquire_recent_sessions(
        request,
        now=pd.Timestamp(now, tz=request.market_timezone),
        repo_manifest_dir=repo_manifest_dir,
    )


def test_explicit_feed_pagination_and_canonical_manifest(
    alpaca_locations: DataLocations,
    alpaca_request: AlpacaBarsRequest,
    tmp_path: Path,
) -> None:
    schedule = _one_session_schedule(alpaca_request)
    bars = _bars_for_schedule(schedule)
    client = FakeClient(
        [
            FakeResponse(200, {"bars": bars[:200], "next_page_token": "next"}),
            FakeResponse(200, {"bars": bars[200:]}),
        ]
    )
    result = _acquire(_provider(client, alpaca_locations), alpaca_request, tmp_path)

    assert len(client.calls) == 2
    assert client.calls[0]["url"] == f"{ALPACA_DATA_HOST}/v2/stocks/SPY/bars"
    assert client.calls[0]["params"]["feed"] == "iex"
    assert client.calls[0]["params"]["timeframe"] == "1Min"
    assert client.calls[1]["params"]["page_token"] == "next"
    assert result.parquet_path == (
        alpaca_locations.root / "equities/SPY/1m/SPY_1m_alpaca_iex.parquet"
    )
    assert result.manifest_path == tmp_path / "equities_SPY_1m_alpaca_iex.json"
    assert result.manifest["provider"] == "alpaca"
    assert result.manifest["feed"] == "iex"
    assert result.manifest["asset_type"] == "ETF"
    assert result.manifest["adjustment"] == "raw"
    assert result.manifest["status"] == "validated"
    assert result.manifest["row_count"] == 390
    assert result.manifest["full_stored_coverage"]["row_count"] == 390
    assert result.manifest["current_acquisition_coverage"]["row_count_after_download"] == 390
    assert result.manifest["cache_status"] == "created"
    assert result.manifest["missing_sessions"] == []
    assert result.manifest["missing_regular_session_bar_count"] == 0
    assert len(result.manifest["sha256"]) == 64


def test_retry_then_success(alpaca_locations: DataLocations, alpaca_request: AlpacaBarsRequest, tmp_path: Path) -> None:
    schedule = _one_session_schedule(alpaca_request)
    client = FakeClient(
        [
            FakeResponse(429, {"code": "42910000", "message": "rate limit"}),
            FakeResponse(200, {"bars": _bars_for_schedule(schedule)}),
        ]
    )
    result = _acquire(_provider(client, alpaca_locations), alpaca_request, tmp_path)
    assert len(client.calls) == 2
    assert result.manifest["row_count"] == 390


def test_non_retryable_error_is_clear(
    alpaca_locations: DataLocations,
    alpaca_request: AlpacaBarsRequest,
    tmp_path: Path,
) -> None:
    client = FakeClient([FakeResponse(401, {"code": "40110000", "message": "invalid"})])
    with pytest.raises(AlpacaDataError, match="HTTP 401"):
        _acquire(_provider(client, alpaca_locations), alpaca_request, tmp_path)


def test_duplicates_are_detected_and_not_written_twice(
    alpaca_locations: DataLocations,
    alpaca_request: AlpacaBarsRequest,
    tmp_path: Path,
) -> None:
    schedule = _one_session_schedule(alpaca_request)
    bars = _bars_for_schedule(schedule)
    duplicated = bars + [dict(bars[0])]
    client = FakeClient([FakeResponse(200, {"bars": duplicated})])
    result = _acquire(_provider(client, alpaca_locations), alpaca_request, tmp_path)

    assert result.frame["timestamp"].is_unique
    assert result.manifest["duplicate_timestamp_count"] == 2
    assert result.manifest["status"] == "provisional"


def test_missing_regular_bar_and_missing_session_are_reported(
    alpaca_locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = AlpacaBarsRequest(completed_session_count=2)
    schedule = recent_completed_sessions(
        request,
        now=pd.Timestamp("2026-07-08 17:00", tz=request.market_timezone),
    )
    first_session_only = schedule.head(1)
    bars = _bars_for_schedule(first_session_only)[:-1]
    client = FakeClient(
        [
            FakeResponse(200, {"bars": bars}),
            FakeResponse(200, {"bars": []}),
        ]
    )
    result = _acquire(_provider(client, alpaca_locations), request, tmp_path)

    assert result.manifest["status"] == "provisional"
    assert result.manifest["missing_sessions"] == [schedule.index[-1].date().isoformat()]
    assert result.manifest["missing_regular_session_bar_count"] == 391


def test_cache_reuse_skips_http_for_identical_requested_sessions(
    alpaca_locations: DataLocations,
    alpaca_request: AlpacaBarsRequest,
    tmp_path: Path,
) -> None:
    schedule = _one_session_schedule(alpaca_request)
    first_client = FakeClient([FakeResponse(200, {"bars": _bars_for_schedule(schedule)})])
    first = _acquire(_provider(first_client, alpaca_locations), alpaca_request, tmp_path)

    second_client = FakeClient([])
    second = _acquire(_provider(second_client, alpaca_locations), alpaca_request, tmp_path)

    assert first.cache_reused is False
    assert second.cache_reused is True
    assert second.manifest["cache_status"] == "full_reuse"
    assert second.manifest["cache_reused"] is True
    assert second.manifest["sha256"] == first.manifest["sha256"]
    assert second.frame.equals(first.frame)
    assert second_client.calls == []


def test_next_session_incremental_extension_preserves_older_history(
    alpaca_locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = AlpacaBarsRequest(completed_session_count=5)
    initial_schedule = _schedule_at(request, "2026-07-08 17:00")
    initial_client = FakeClient(_responses_for_schedule(initial_schedule))
    initial = _acquire_at(
        _provider(initial_client, alpaca_locations),
        request,
        tmp_path,
        "2026-07-08 17:00",
    )

    next_schedule = _schedule_at(request, "2026-07-09 17:00")
    new_session = next_schedule.tail(1)
    next_client = FakeClient([FakeResponse(200, {"bars": _bars_for_schedule(new_session)})])
    extended = _acquire_at(
        _provider(next_client, alpaca_locations),
        request,
        tmp_path,
        "2026-07-09 17:00",
    )

    assert len(initial_client.calls) == 5
    assert len(next_client.calls) == 1
    assert next_client.calls[0]["params"]["start"] == new_session["market_open"].iloc[0].isoformat().replace("+00:00", "Z")
    assert next_client.calls[0]["params"]["end"] == new_session["market_close"].iloc[0].isoformat().replace("+00:00", "Z")
    assert extended.manifest["already_present_sessions"] == [
        "2026-07-02",
        "2026-07-06",
        "2026-07-07",
        "2026-07-08",
    ]
    assert extended.manifest["newly_downloaded_sessions"] == ["2026-07-09"]
    assert extended.manifest["cache_status"] == "incremental_update"
    assert extended.manifest["row_count"] == 2340
    assert extended.manifest["full_stored_coverage"]["row_count"] == 2340
    assert extended.manifest["earliest_timestamp"] == initial.manifest["earliest_timestamp"]
    assert extended.frame["timestamp"].min() == initial.frame["timestamp"].min()
    assert set(initial.frame["timestamp"]).issubset(set(extended.frame["timestamp"]))


def test_overlap_deduplication_keeps_one_row_per_timestamp(
    alpaca_locations: DataLocations,
    tmp_path: Path,
) -> None:
    request = AlpacaBarsRequest(completed_session_count=1)
    schedule = _one_session_schedule(request)
    bars = _bars_for_schedule(schedule)
    partial = bars[:-1]
    initial = _acquire(
        _provider(FakeClient([FakeResponse(200, {"bars": partial})]), alpaca_locations),
        request,
        tmp_path,
    )
    assert initial.manifest["status"] == "provisional"

    overlap = [dict(bars[-2]), dict(bars[-1])]
    second = _acquire(
        _provider(FakeClient([FakeResponse(200, {"bars": overlap})]), alpaca_locations),
        request,
        tmp_path,
    )

    assert second.manifest["row_count"] == 390
    assert second.frame["timestamp"].is_unique
    assert second.manifest["duplicate_timestamp_count"] == 2
    assert second.manifest["missing_regular_session_bar_count"] == 0


def test_hash_mismatch_prevents_unsafe_reuse_or_overwrite(
    alpaca_locations: DataLocations,
    alpaca_request: AlpacaBarsRequest,
    tmp_path: Path,
) -> None:
    schedule = _one_session_schedule(alpaca_request)
    first_client = FakeClient([FakeResponse(200, {"bars": _bars_for_schedule(schedule)})])
    first = _acquire(_provider(first_client, alpaca_locations), alpaca_request, tmp_path)
    first.parquet_path.write_bytes(b"tampered")

    second_client = FakeClient([FakeResponse(200, {"bars": _bars_for_schedule(schedule)})])
    with pytest.raises(AlpacaDataError, match="SHA-256"):
        _acquire(_provider(second_client, alpaca_locations), alpaca_request, tmp_path)
    assert second_client.calls == []


def test_feed_is_part_of_dataset_identity() -> None:
    iex = AlpacaBarsRequest(feed="iex")
    sip = replace(
        AlpacaBarsRequest(feed="sip"),
        dataset_id="equities_SPY_1m_alpaca_sip",
        filename="SPY_1m_alpaca_sip.parquet",
    )
    assert "iex" in iex.dataset_id
    assert "iex" in iex.canonical_relative_path.name
    assert "sip" in sip.dataset_id
    assert "sip" in sip.canonical_relative_path.name
    assert iex.canonical_relative_path != sip.canonical_relative_path


def test_credentials_loader_accepts_shell_export_lines(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text(
        "export APCA_API_KEY_ID='id-value'\n"
        'export APCA_API_SECRET_KEY="secret-value"\n'
        "IGNORED=value\n",
        encoding="utf-8",
    )
    credentials = AlpacaCredentials.from_env_file(secrets)
    assert credentials.key_id == "id-value"
    assert credentials.secret_key == "secret-value"
