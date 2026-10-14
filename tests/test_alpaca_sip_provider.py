"""Alpaca SIP provider tests against a scripted HTTP layer (no network, no credentials)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from market_data.catalog import DataLocations, calculate_sha256
from market_data.providers.alpaca import AlpacaCredentials
from market_data.providers.alpaca_sip import (
    AlpacaSipError,
    AlpacaSipProvider,
    AlpacaSipValidationError,
    RequestThrottle,
    SipDataset,
    bars_to_frame,
    credentials_from_environment,
    mark_sessions,
)

CREDENTIALS = AlpacaCredentials(key_id="test-key-id", secret_key="test-secret-value")


class Reply:
    def __init__(self, status_code: int, payload: Any = None, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers or {}
        self.text = ""

    def json(self) -> Any:
        return self.payload


class BarServer:
    """Serves stored bars filtered by start/end, paginated with small pages."""

    def __init__(self, bars: list[dict[str, Any]], page_size: int = 2):
        self.bars = bars
        self.page_size = page_size
        self.calls: list[dict[str, Any]] = []
        self.queued: list[Reply] = []

    def get(self, url: str, *, headers: dict[str, str], params: dict[str, Any], timeout: float) -> Reply:
        self.calls.append({"url": url, "headers": dict(headers), "params": dict(params)})
        if self.queued:
            return self.queued.pop(0)
        start, end = pd.Timestamp(params["start"]), pd.Timestamp(params["end"])
        hits = [bar for bar in self.bars if start <= pd.Timestamp(bar["t"]) <= end]
        offset = int(params.get("page_token") or 0)
        page = hits[offset : offset + self.page_size]
        more = offset + self.page_size < len(hits)
        return Reply(200, {"bars": page, "next_page_token": str(offset + self.page_size) if more else None})


def bar(ts: str, price: float = 100.0, **overrides: Any) -> dict[str, Any]:
    values = {"t": ts, "o": price, "h": price + 1, "l": price - 1, "c": price + 0.5, "v": 1000, "n": 7, "vw": price}
    values.update(overrides)
    return values


DAY_ONE = [bar("2026-10-12T12:00:00Z"), bar("2026-10-12T13:30:00Z", 101), bar("2026-10-12T19:59:00Z", 102)]
DAY_TWO = [bar("2026-10-13T13:30:00Z", 103), bar("2026-10-13T20:30:00Z", 104)]


def locations(tmp_path: Path) -> DataLocations:
    return DataLocations(
        root=tmp_path / "root",
        manifests=tmp_path / "manifests",
        quarantine=tmp_path / "quarantine",
        backup_archive=None,
        extracted_root=None,
        verify_sha256_before_use=True,
    )


def provider(tmp_path: Path, server: BarServer, now: str = "2026-10-14T12:00:00Z", sleeps: list | None = None):
    record = sleeps if sleeps is not None else []
    return AlpacaSipProvider(
        credentials=CREDENTIALS,
        locations=locations(tmp_path),
        client=server,
        throttle=RequestThrottle(1000, sleep=record.append),
        sleep=record.append,
        now=lambda: pd.Timestamp(now),
    )


def manifest_file(tmp_path: Path, symbol: str = "SPY") -> Path:
    return SipDataset(symbol).manifest_path(locations(tmp_path))


def stored_path(tmp_path: Path, symbol: str = "SPY") -> Path:
    manifest = json.loads(manifest_file(tmp_path, symbol).read_text())
    return tmp_path / "root" / manifest["canonical_relative_path"]


def test_pagination_split_adjustment_and_sip_feed_are_requested(tmp_path):
    server = BarServer(DAY_ONE + DAY_TWO, page_size=2)
    frame = provider(tmp_path, server).fetch(
        "SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-14T00:00Z")
    )
    assert len(frame) == 5
    assert len(server.calls) == 3
    assert "page_token" not in server.calls[0]["params"]
    assert [call["params"].get("page_token") for call in server.calls[1:]] == ["2", "4"]
    params = server.calls[0]["params"]
    assert params["adjustment"] == "split"
    assert params["feed"] == "sip"
    assert params["timeframe"] == "1Min"
    assert params["limit"] == 10_000
    assert server.calls[0]["url"].endswith("/v2/stocks/SPY/bars")
    assert server.calls[0]["headers"]["APCA-API-KEY-ID"] == "test-key-id"


def test_sessions_marked_including_early_close_and_closed_days():
    raw = [
        bar("2026-10-12T12:00:00Z"),  # 08:00 ET pre-market
        bar("2026-10-12T13:30:00Z"),  # open
        bar("2026-10-12T19:59:00Z"),  # last regular minute
        bar("2026-10-12T20:00:00Z"),  # post-market
        bar("2025-11-28T18:30:00Z"),  # 13:30 ET after the 13:00 early close
        bar("2026-10-10T15:00:00Z"),  # Saturday
    ]
    sessions = mark_sessions(bars_to_frame(raw))["session"].tolist()
    assert sessions == ["pre", "regular", "regular", "post", "post", "closed"]


def test_throttle_sleeps_when_window_is_full():
    clock = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    throttle = RequestThrottle(3, clock=lambda: clock[0], sleep=sleep)
    for _ in range(3):
        throttle.wait()
        clock[0] += 1.0
    assert sleeps == []
    throttle.wait()
    assert sleeps == [57.0]


def test_retries_429_and_5xx_then_succeeds(tmp_path):
    server = BarServer([])
    server.queued = [Reply(429, {"message": "too many"}, {"Retry-After": "2"}), Reply(503, {}), Reply(200, {"bars": [bar("2026-10-12T13:30:00Z")]})]
    sleeps: list[float] = []
    frame = provider(tmp_path, server, sleeps=sleeps).fetch(
        "SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T00:00Z")
    )
    assert len(frame) == 1
    assert len(server.calls) == 3
    assert sleeps == [2.0, 2.0]


def test_non_retryable_error_fails_without_leaking_credentials(tmp_path):
    server = BarServer([])
    server.queued = [Reply(403, {"message": "forbidden"})]
    with pytest.raises(AlpacaSipError) as raised:
        provider(tmp_path, server).fetch("SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T00:00Z"))
    assert "HTTP 403" in str(raised.value)
    assert "test-secret-value" not in str(raised.value)
    assert len(server.calls) == 1


def test_retries_exhausted_raise(tmp_path):
    server = BarServer([])
    server.queued = [Reply(500, {})] * 6
    with pytest.raises(AlpacaSipError, match="HTTP 500"):
        provider(tmp_path, server).fetch("SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T00:00Z"))
    assert len(server.calls) == 6


def test_full_then_incremental_then_idempotent(tmp_path):
    server = BarServer(list(DAY_ONE), page_size=10)
    first = provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    assert (first.status, first.row_count) == ("full", 3)
    assert server.calls[0]["params"]["start"] == "2016-01-01T05:00:00Z"
    assert server.calls[0]["params"]["end"] == "2026-10-12T22:39:00Z"
    slot_a = stored_path(tmp_path)
    assert slot_a.name == "SPY_1m_alpaca_sip.a.parquet"
    assert manifest_file(tmp_path).parent == tmp_path / "root" / "manifests"
    slot_a_digest = calculate_sha256(slot_a)

    server.bars = DAY_ONE + DAY_TWO
    server.calls.clear()
    second = provider(tmp_path, server).top_up("SPY")
    assert (second.status, second.new_rows, second.row_count) == ("incremental", 2, 5)
    assert server.calls[0]["params"]["start"] == "2026-10-12T19:59:00Z"
    assert stored_path(tmp_path).name == "SPY_1m_alpaca_sip.b.parquet"
    assert calculate_sha256(slot_a) == slot_a_digest  # committed slot never rewritten
    stored = pd.read_parquet(stored_path(tmp_path))
    assert stored["session"].tolist() == ["pre", "regular", "regular", "regular", "post"]
    manifest = json.loads((manifest_file(tmp_path)).read_text())
    assert manifest["sha256"] == calculate_sha256(stored_path(tmp_path))
    assert manifest["row_count"] == 5
    assert manifest["last_top_up"]["mode"] == "incremental"
    assert "survivorship bias" in manifest["universe"]["survivorship_bias"]
    assert manifest["adjustment"] == "split"

    digest = calculate_sha256(stored_path(tmp_path))
    third = provider(tmp_path, server).top_up("SPY")
    assert (third.status, third.new_rows) == ("current", 0)
    assert calculate_sha256(stored_path(tmp_path)) == digest


def test_split_since_last_run_refetches_whole_history(tmp_path):
    server = BarServer(list(DAY_ONE), page_size=10)
    provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    halved = [bar(item["t"], item["o"] / 2) for item in DAY_ONE + DAY_TWO]
    server.bars = halved
    result = provider(tmp_path, server).top_up("SPY")
    assert result.status == "refetched_after_adjustment_change"
    stored = pd.read_parquet(stored_path(tmp_path))
    assert stored["open"].tolist() == [item["o"] for item in halved]


def test_validation_failure_quarantines_and_keeps_old_file(tmp_path):
    server = BarServer(list(DAY_ONE), page_size=10)
    provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    digest = calculate_sha256(stored_path(tmp_path))
    manifest_path = manifest_file(tmp_path)
    manifest_before = manifest_path.read_text()
    server.bars = DAY_ONE + [bar("2026-10-13T13:30:00Z", 103, h=90.0)]
    with pytest.raises(AlpacaSipValidationError, match="high/low"):
        provider(tmp_path, server).top_up("SPY")
    assert calculate_sha256(stored_path(tmp_path)) == digest
    assert manifest_path.read_text() == manifest_before
    quarantined = sorted((tmp_path / "quarantine" / "alpaca_sip").iterdir())
    assert [path.suffix for path in quarantined] == [".json", ".parquet"]
    assert "high/low" in json.loads(quarantined[0].read_text())["problems"][0]
    assert not list(stored_path(tmp_path).parent.glob("*.tmp"))


def test_missing_credentials_fail_plainly():
    with pytest.raises(AlpacaSipError, match="QF_ALPACA_API_KEY and QF_ALPACA_SECRET_KEY"):
        credentials_from_environment({})
    with pytest.raises(AlpacaSipError, match="QF_ALPACA_SECRET_KEY"):
        credentials_from_environment({"QF_ALPACA_API_KEY": "abc", "QF_ALPACA_SECRET_KEY": " "})
    assert credentials_from_environment(
        {"QF_ALPACA_API_KEY": "abc", "QF_ALPACA_SECRET_KEY": "def"}
    ) == AlpacaCredentials(key_id="abc", secret_key="def")


def test_symbol_outside_universe_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not in the Alpaca SIP universe"):
        provider(tmp_path, BarServer([])).top_up("ZZZZ")


def test_committed_file_not_matching_manifest_fails_closed(tmp_path):
    server = BarServer(list(DAY_ONE), page_size=10)
    provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    manifest_before = manifest_file(tmp_path).read_text()
    stored_path(tmp_path).write_bytes(b"tampered")
    server.bars = DAY_ONE + DAY_TWO
    with pytest.raises(AlpacaSipError, match="does not match its manifest"):
        provider(tmp_path, server).top_up("SPY")
    assert manifest_file(tmp_path).read_text() == manifest_before


def test_symbol_listed_after_2016_records_true_first_bar(tmp_path):
    late = [bar("2021-06-01T13:30:00Z", 20), bar("2021-06-01T13:31:00Z", 21)]
    result = provider(tmp_path, BarServer(late, page_size=10)).top_up("SOFI")
    assert (result.status, result.row_count) == ("full", 2)
    manifest = json.loads(manifest_file(tmp_path, "SOFI").read_text())
    assert manifest["first_available_bar"] == "2021-06-01T13:30:00+00:00"
    assert manifest["earliest_timestamp"] == "2021-06-01T13:30:00+00:00"
    assert manifest["requested_coverage"]["start"].startswith("2016-01-01")
    assert manifest["history_starts_after_requested_start"] is True
    assert manifest["universe"]["group"] == "affordable_high_volume"
    assert "Oct 2026" in manifest["universe"]["survivorship_bias"]
