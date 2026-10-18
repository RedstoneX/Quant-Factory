"""Alpaca SIP provider tests with ``vbt.AlpacaData.fetch_symbol`` faked (no network, no credentials)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from market_data.catalog import DataLocations, calculate_sha256
from market_data.providers.alpaca import AlpacaCredentials
from market_data.providers.alpaca_sip import (
    AlpacaSipError,
    AlpacaSipProvider,
    AlpacaSipValidationError,
    SipDataset,
    credentials_from_environment,
    mark_sessions,
    validate_bars,
)

CREDENTIALS = AlpacaCredentials(key_id="test-key-id", secret_key="test-secret-value")


class ApiError(Exception):
    """Shaped like alpaca-py's APIError: a message plus an HTTP status."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class BarServer:
    """Stands in for ``vbt.AlpacaData``: serves stored bars in [start, end) as VectorBT does."""

    def __init__(self, bars: list[dict[str, Any]], page_size: int | None = None):
        self.bars = bars  # page_size is ignored: alpaca-py pages; kept for tests that import this
        self.calls: list[dict[str, Any]] = []
        self.queued: list[Exception] = []

    def fetch_symbol(self, symbol: str, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
        self.calls.append({"symbol": symbol, **kwargs})
        if self.queued:
            raise self.queued.pop(0)
        start, end = pd.Timestamp(kwargs["start"]), pd.Timestamp(kwargs["end"])
        hits = [bar for bar in self.bars if start <= pd.Timestamp(bar["t"]) < end]
        if not hits:
            return pd.DataFrame(), {}
        index = pd.DatetimeIndex([pd.Timestamp(bar["t"]) for bar in hits], name="Open time")
        columns = {"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v", "Trade count": "n", "VWAP": "vw"}
        return pd.DataFrame({name: [bar[key] for bar in hits] for name, key in columns.items()}, index=index), {}


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


def provider(tmp_path: Path, server: BarServer, now: str = "2026-10-14T12:00:00Z"):
    return AlpacaSipProvider(
        credentials=CREDENTIALS,
        locations=locations(tmp_path),
        now=lambda: pd.Timestamp(now),
        alpaca_data=server,
    )


def manifest_file(tmp_path: Path, symbol: str = "SPY") -> Path:
    return SipDataset(symbol).manifest_path(locations(tmp_path))


def stored_path(tmp_path: Path, symbol: str = "SPY") -> Path:
    manifest = json.loads(manifest_file(tmp_path, symbol).read_text())
    return tmp_path / "root" / manifest["canonical_relative_path"]


def test_split_adjustment_sip_feed_and_inclusive_end_are_requested(tmp_path):
    server = BarServer(DAY_ONE + DAY_TWO)
    frame = provider(tmp_path, server).fetch(
        "SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T20:30Z")
    )
    assert len(frame) == 5  # the bar stamped exactly at ``end`` is kept
    assert list(frame.columns) == [
        "timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap", "session"
    ]
    assert str(frame["timestamp"].dtype) == "datetime64[ns, UTC]"
    assert str(frame["trade_count"].dtype) == "Int64"
    assert len(server.calls) == 1
    call = server.calls[0]
    assert (call["symbol"], call["client_type"], call["timeframe"]) == ("SPY", "stocks", "1m")
    assert (call["feed"], call["adjustment"], call["sort"]) == ("sip", "split", "asc")
    assert call["end"] == pd.Timestamp("2026-10-13T20:31Z")
    assert call["client_config"] == {"api_key": "test-key-id", "secret_key": "test-secret-value"}


def test_sessions_marked_including_early_close_and_closed_days(tmp_path):
    raw = [
        bar("2026-10-12T12:00:00Z"),  # 08:00 ET pre-market
        bar("2026-10-12T13:30:00Z"),  # open
        bar("2026-10-12T19:59:00Z"),  # last regular minute
        bar("2026-10-12T20:00:00Z"),  # post-market
        bar("2025-11-28T18:30:00Z"),  # 13:30 ET after the 13:00 early close
        bar("2026-10-10T15:00:00Z"),  # Saturday
    ]
    frame = provider(tmp_path, BarServer(raw)).fetch(
        "SPY", pd.Timestamp("2025-01-01T00:00Z"), pd.Timestamp("2026-10-13T00:00Z")
    )
    assert frame["session"].tolist() == ["pre", "regular", "regular", "post", "post", "closed"]


def test_default_source_is_vbt_alpaca_data_loaded_lazily(tmp_path, monkeypatch):
    server = BarServer(DAY_ONE)
    monkeypatch.setitem(sys.modules, "vectorbtpro", SimpleNamespace(AlpacaData=server))
    sip = AlpacaSipProvider(credentials=CREDENTIALS, locations=locations(tmp_path))
    frame = sip.fetch("SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T00:00Z"))
    assert (len(frame), len(server.calls)) == (3, 1)


def test_library_error_fails_without_leaking_credentials(tmp_path):
    server = BarServer([])
    server.queued = [ApiError('{"message":"forbidden"}', 403)]
    with pytest.raises(AlpacaSipError) as raised:
        provider(tmp_path, server).fetch("SPY", pd.Timestamp("2026-10-12T00:00Z"), pd.Timestamp("2026-10-13T00:00Z"))
    assert "HTTP 403" in str(raised.value)
    assert "test-secret-value" not in str(raised.value)
    assert len(server.calls) == 1


def test_full_then_incremental_then_idempotent(tmp_path):
    server = BarServer(list(DAY_ONE))
    first = provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    assert (first.status, first.row_count) == ("full", 3)
    assert server.calls[0]["start"] == pd.Timestamp("2016-01-01T05:00:00Z")
    assert server.calls[0]["end"] == pd.Timestamp("2026-10-12T22:40:00Z")  # 22:39 inclusive
    slot_a = stored_path(tmp_path)
    assert slot_a.name == "SPY_1m_alpaca_sip.a.parquet"
    assert manifest_file(tmp_path).parent == tmp_path / "root" / "manifests"
    slot_a_digest = calculate_sha256(slot_a)

    server.bars = DAY_ONE + DAY_TWO
    server.calls.clear()
    second = provider(tmp_path, server).top_up("SPY")
    assert (second.status, second.new_rows, second.row_count) == ("incremental", 2, 5)
    assert server.calls[0]["start"] == pd.Timestamp("2026-10-12T12:00:00Z")  # newest session re-fetched
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
    server = BarServer(DAY_ONE + DAY_TWO)
    provider(tmp_path, server).top_up("SPY")
    day_three = [bar("2026-10-14T13:30:00Z", 105)]
    halved = [bar(item["t"], item["o"] / 2) for item in DAY_ONE + DAY_TWO + day_three]
    server.bars = halved
    result = provider(tmp_path, server, now="2026-10-16T12:00:00Z").top_up("SPY")
    assert result.status == "refetched_after_adjustment_change"
    stored = pd.read_parquet(stored_path(tmp_path))
    assert stored["open"].tolist() == [item["o"] for item in halved]


def test_validation_failure_quarantines_and_keeps_old_file(tmp_path):
    server = BarServer(list(DAY_ONE))
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
    server = BarServer(list(DAY_ONE))
    provider(tmp_path, server, now="2026-10-12T23:00:00Z").top_up("SPY")
    manifest_before = manifest_file(tmp_path).read_text()
    stored_path(tmp_path).write_bytes(b"tampered")
    server.bars = DAY_ONE + DAY_TWO
    with pytest.raises(AlpacaSipError, match="does not match its manifest"):
        provider(tmp_path, server).top_up("SPY")
    assert manifest_file(tmp_path).read_text() == manifest_before


def test_symbol_listed_after_2016_records_true_first_bar(tmp_path):
    late = [bar("2021-06-01T13:30:00Z", 20), bar("2021-06-01T13:31:00Z", 21)]
    result = provider(tmp_path, BarServer(late)).top_up("RKLB")
    assert (result.status, result.row_count) == ("full", 2)
    manifest = json.loads(manifest_file(tmp_path, "RKLB").read_text())
    assert manifest["first_available_bar"] == "2021-06-01T13:30:00+00:00"
    assert manifest["earliest_timestamp"] == "2021-06-01T13:30:00+00:00"
    assert manifest["requested_coverage"]["start"].startswith("2016-01-01")
    assert manifest["history_starts_after_requested_start"] is True
    assert manifest["universe"]["group"] == "stocks"
    assert "Oct 2026" in manifest["universe"]["survivorship_bias"]


def test_newest_session_refetched_gap_filled_correction_taken_earlier_bars_kept(tmp_path):
    day_three = [bar("2026-10-14T13:30:00Z", 105), bar("2026-10-14T19:59:00Z", 106)]
    server = BarServer(DAY_ONE + [day_three[0]])  # vendor missed 19:59 on day three
    first = provider(tmp_path, server, now="2026-10-16T12:00:00Z").top_up("SPY")
    assert "regular-session minutes missing" in json.loads(manifest_file(tmp_path).read_text())["validation_notes"][0]

    changed_older = [bar(item["t"], item["o"] + 9) if item is DAY_ONE[1] else item for item in DAY_ONE]
    server.bars = changed_older + [bar(day_three[0]["t"], 99), day_three[1]]
    server.calls.clear()
    result = provider(tmp_path, server, now="2026-10-16T12:00:00Z").top_up("SPY")
    assert (result.status, result.new_rows) == ("incremental", 1)
    assert server.calls[0]["start"] == pd.Timestamp("2026-10-12T19:59:00Z")  # last bar before the session
    stored = pd.read_parquet(stored_path(tmp_path))
    assert stored["open"].tolist() == [100.0, 101.0, 102.0, 99.0, 106.0]  # older bar not re-taken
    assert first.path.exists()
    assert provider(tmp_path, server, now="2026-10-16T12:00:00Z").top_up("SPY").status == "current"


def test_prefix_guard_rejects_a_changed_bar_two_sessions_back(tmp_path):
    server = BarServer(DAY_ONE + DAY_TWO)
    provider(tmp_path, server).top_up("SPY")
    previous = pd.read_parquet(stored_path(tmp_path))
    candidate = previous.copy()
    candidate.loc[1, "close"] += 0.25  # day one, two sessions before a day-three top-up
    problems = validate_bars(candidate, end=pd.Timestamp("2026-10-16T12:00:00Z"), previous=previous.iloc[:3])
    assert problems == ["previously stored bars changed during an incremental top-up"]
    notes: list[str] = []
    assert validate_bars(previous, end=pd.Timestamp("2026-10-16T12:00:00Z"), previous=previous.iloc[:3], notes=notes) == []
    assert "regular-session minutes missing" in notes[0]  # day two's gaps reported, not fatal


def _minute_bars(day: str, count: int, spike_at: int | None = None) -> list[dict[str, Any]]:
    start = pd.Timestamp(f"{day}T13:30:00Z")
    bars = [bar((start + pd.Timedelta(minutes=i)).isoformat(), 100 + (i % 7) * 0.01) for i in range(count)]
    if spike_at is not None:
        bars[spike_at].update(h=160.0, c=159.0)
    return bars


def _manifest_digest(tmp_path: Path) -> str:
    manifest = json.loads(manifest_file(tmp_path).read_text())
    for key in ("acquisition_timestamp", "imported_at_utc"):
        manifest.pop(key)
    manifest["last_top_up"].pop("at_utc")
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


# Recorded from the pre-fix code (main 92bb970, pandas 2.3.3, pyarrow 24.0.0) on this exact input:
# the memory fixes must leave every written byte and manifest field unchanged.
PRE_FIX_OUTPUT = [
    ("full", "efa1519a8e97e8073c7eb77bdf8010d3bb82c282d211a1b203d47c5f0b9d0c63", "73edb01ddc57281c4ff5ff364b5e2616ab7bd80d8e7524c012c5a2f7ff6db21c"),
    ("incremental", "aaf5744cb6480ddf6337986070e6937c68959428f03b859edb7d8aa8046d306a", "e803f6cc6da601df789d1ce4c48659f98d6548d2fd448838a949eee7b6675812"),
    ("current", "aaf5744cb6480ddf6337986070e6937c68959428f03b859edb7d8aa8046d306a", "e803f6cc6da601df789d1ce4c48659f98d6548d2fd448838a949eee7b6675812"),
]


def test_written_parquet_and_manifest_identical_to_pre_fix_code(tmp_path):
    day_one, day_two = _minute_bars("2026-10-12", 120, spike_at=60), _minute_bars("2026-10-13", 90, spike_at=30)
    server = BarServer(day_one[:100])
    runs = [("2026-10-12T23:00:00Z", day_one[:100]), ("2026-10-14T12:00:00Z", day_one + day_two),
            ("2026-10-14T12:00:00Z", day_one + day_two)]
    seen = []
    for now, bars in runs:
        server.bars = bars
        result = provider(tmp_path, server, now=now).top_up("SPY")
        seen.append((result.status, calculate_sha256(stored_path(tmp_path)), _manifest_digest(tmp_path)))
    assert json.loads(manifest_file(tmp_path).read_text())["suspect_bar_count"] == 2
    assert seen == PRE_FIX_OUTPUT
