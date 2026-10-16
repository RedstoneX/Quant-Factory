"""VectorBT price download/top-up path (``QF_PRICE_DOWNLOADER``), no network, no real credentials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from market_data.catalog import DataLocations
from market_data.providers.alpaca import AlpacaCredentials
from market_data.providers.alpaca_sip import AlpacaSipProvider, AlpacaSipValidationError, SipDataset
from market_data.vbt_prices import (
    VbtSipProvider,
    price_downloader,
    pull_or_update,
    sip_provider_class,
    sip_store_path,
)

SECRET = "never-in-the-saved-file"
CREDENTIALS = AlpacaCredentials(key_id="key-for-tests", secret_key=SECRET)
NOW = "2026-10-14T12:00:00Z"
COLUMNS = {"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v", "Trade count": "n", "VWAP": "vw"}


def bar(ts: str, price: float = 100.0) -> dict[str, Any]:
    return {"t": ts, "o": price, "h": price + 1, "l": price - 1, "c": price + 0.5, "v": 1000, "n": 7, "vw": price}


DAY_ONE = [bar("2026-10-12T12:00:00Z"), bar("2026-10-12T13:30:00Z", 101), bar("2026-10-12T19:59:00Z", 102)]
DAY_TWO = [bar("2026-10-13T13:30:00Z", 103), bar("2026-10-13T20:30:00Z", 104)]
LATER = "2026-10-16T12:00:00Z"
DAY_THREE = [bar("2026-10-14T13:30:00Z", 105), bar("2026-10-14T19:59:00Z", 106)]
DAY_FOUR = [bar("2026-10-15T13:30:00Z", 107)]


SERVED: list[dict[str, Any]] = []  # module level so saved/loaded instances see changes

try:
    import vectorbtpro as _vbt
except ImportError:  # the licensed tests below are skipped without VectorBT PRO
    _vbt = None

if _vbt is not None:

    class BarServer(_vbt.AlpacaData):
        """A real ``vbt.AlpacaData`` whose only change is serving ``SERVED`` in [start, end)."""

        @classmethod
        def fetch_symbol(cls, symbol: str, **kwargs: Any):
            start, end = (pd.Timestamp(kwargs[k]) for k in ("start", "end"))
            start, end = (t if t.tzinfo else t.tz_localize("UTC") for t in (start, end))
            hits = [b for b in SERVED if start <= pd.Timestamp(b["t"]) < end]
            index = pd.DatetimeIndex([pd.Timestamp(b["t"]) for b in hits])
            return pd.DataFrame({name: [b[key] for b in hits] for name, key in COLUMNS.items()}, index=index), {}


def bar_server(bars: list[dict[str, Any]]) -> type:
    pytest.importorskip("vectorbtpro")
    SERVED[:] = bars
    return BarServer


def serve(bars: list[dict[str, Any]]) -> None:
    SERVED[:] = bars


def locations(root: Path) -> DataLocations:
    return DataLocations(
        root=root / "root", manifests=root / "manifests", quarantine=root / "quarantine",
        backup_archive=None, extracted_root=None, verify_sha256_before_use=True,
    )


def stored(provider: AlpacaSipProvider, result) -> pd.DataFrame:
    return pd.read_parquet(result.path)


def make(cls: type, root: Path, server: type, now: str = NOW) -> AlpacaSipProvider:
    return cls(credentials=CREDENTIALS, locations=locations(root), now=lambda: pd.Timestamp(now), alpaca_data=server)


def test_setting_defaults_to_vbt_legacy_selectable_and_rejects_unknown_values():
    assert price_downloader({}) == "vbt"
    assert price_downloader({"QF_PRICE_DOWNLOADER": "LEGACY"}) == "legacy"
    assert sip_provider_class({}) is VbtSipProvider
    assert sip_provider_class({"QF_PRICE_DOWNLOADER": "legacy"}) is AlpacaSipProvider
    with pytest.raises(ValueError):
        price_downloader({"QF_PRICE_DOWNLOADER": "other"})


@pytest.mark.licensed_vectorbt
def test_vbt_top_up_stores_exactly_what_legacy_stores(tmp_path):
    server = bar_server(DAY_ONE)
    legacy = make(AlpacaSipProvider, tmp_path / "legacy", server)
    vbt_path = make(VbtSipProvider, tmp_path / "vbt", server)
    first = (legacy.top_up("SPY", since="2026-10-12"), vbt_path.top_up("SPY", since="2026-10-12"))
    assert [r.status for r in first] == ["full", "full"]
    pd.testing.assert_frame_equal(stored(legacy, first[0]), stored(vbt_path, first[1]))

    serve(DAY_ONE + DAY_TWO)
    second = (legacy.top_up("SPY", since="2026-10-12"), vbt_path.top_up("SPY", since="2026-10-12"))
    assert [r.status for r in second] == ["incremental", "incremental"]
    assert [r.new_rows for r in second] == [2, 2]
    pd.testing.assert_frame_equal(stored(legacy, second[0]), stored(vbt_path, second[1]))


@pytest.mark.licensed_vectorbt
def test_moved_last_bar_triggers_full_refetch(tmp_path):
    server = bar_server(DAY_ONE + DAY_TWO)
    provider = make(VbtSipProvider, tmp_path, server, now=LATER)
    provider.top_up("SPY", since="2026-10-12")
    serve([bar(b["t"], b["o"] / 2) for b in DAY_ONE + DAY_TWO + DAY_THREE])  # a 2:1 split
    result = provider.top_up("SPY", since="2026-10-12")
    assert result.status == "refetched_after_adjustment_change"
    assert stored(provider, result)["open"].tolist() == [50.0, 50.5, 51.0, 51.5, 52.0, 52.5, 53.0]


@pytest.mark.licensed_vectorbt
def test_saved_vbt_file_holds_no_api_keys(tmp_path):
    vbt = pytest.importorskip("vectorbtpro")
    provider = make(VbtSipProvider, tmp_path, bar_server(DAY_ONE))
    provider.top_up("SPY", since="2026-10-12")
    path = sip_store_path(locations(tmp_path), "SPY")
    assert SECRET.encode() not in path.read_bytes()
    assert "client_config" not in vbt.load(path).select_fetch_kwargs("SPY")


@pytest.mark.licensed_vectorbt
def test_pull_or_update_equals_a_fresh_full_pull(tmp_path):
    server = bar_server(DAY_ONE)
    path = tmp_path / "spy.pickle"
    kwargs = dict(start=pd.Timestamp("2026-10-12", tz="UTC"), timeframe="1m")
    assert pull_or_update(server, path, "SPY", end="2026-10-14", **kwargs).status == "full"
    serve(DAY_ONE + DAY_TWO)
    updated = pull_or_update(server, path, "SPY", end="2026-10-14", **kwargs)
    assert updated.status == "incremental"
    fresh = server.pull("SPY", end="2026-10-14", **kwargs)
    pd.testing.assert_frame_equal(updated.data.get(), fresh.get(), check_freq=False)
    assert pull_or_update(server, path, "SPY", end="2026-10-14", **kwargs).status == "current"


@pytest.mark.licensed_vectorbt
def test_first_vbt_run_over_legacy_store_is_a_full_rebuild_then_incremental(tmp_path):
    server = bar_server(DAY_ONE)
    old = make(AlpacaSipProvider, tmp_path, server).top_up("SPY", since="2026-10-12")
    corrected = [bar(b["t"], b["o"] + 5) if b is DAY_ONE[1] else b for b in DAY_ONE]
    serve(corrected + DAY_TWO[:1])  # the broker has since corrected one bar the legacy store holds
    provider = make(VbtSipProvider, tmp_path, server)
    first = provider.top_up("SPY", since="2026-10-12")
    assert first.status == "full_rebuild_vbt"
    assert old.path.exists() and first.path != old.path  # earlier slot kept as backup
    assert stored(provider, first)["open"].tolist() == [100.0, 106.0, 102.0, 103.0]

    serve(corrected + DAY_TWO)
    second = provider.top_up("SPY", since="2026-10-12")
    assert (second.status, second.new_rows) == ("incremental", 1)


@pytest.mark.licensed_vectorbt
def test_newest_session_is_refetched_so_vendor_gap_fills_and_corrections_land(tmp_path):
    middle = bar("2026-10-13T17:00:00Z", 110)
    server = bar_server(DAY_ONE + [DAY_TWO[0], DAY_TWO[1]])  # vendor missed 17:00 on day two
    provider = make(VbtSipProvider, tmp_path, server)
    first = provider.top_up("SPY", since="2026-10-12")
    notes = json.loads(SipDataset("SPY").manifest_path(locations(tmp_path)).read_text())["validation_notes"]
    assert "regular-session minutes missing" in notes[0]  # reported, not fatal

    fixed = [bar(DAY_TWO[0]["t"], 99), middle, DAY_TWO[1]]  # gap filled, first bar corrected
    serve(DAY_ONE + fixed)
    second = provider.top_up("SPY", since="2026-10-12")
    assert (second.status, second.new_rows) == ("incremental", 1)
    assert stored(provider, second)["open"].tolist() == [100.0, 101.0, 102.0, 99.0, 110.0, 104.0]
    assert provider.top_up("SPY", since="2026-10-12").status == "current"
    assert first.path.exists()


@pytest.mark.licensed_vectorbt
def test_changed_bar_two_sessions_back_is_still_rejected(tmp_path):
    server = bar_server(DAY_ONE + DAY_TWO)
    vbt_side = make(VbtSipProvider, tmp_path, server, now=LATER)
    vbt_side.top_up("SPY", since="2026-10-12")
    moved = [bar(b["t"], b["o"] + 3) if b is DAY_ONE[-1] else b for b in DAY_ONE]
    serve(moved + DAY_TWO + DAY_THREE)  # the legacy downloader stores a different day one
    legacy = make(AlpacaSipProvider, tmp_path, server, now=LATER).top_up("SPY", since="2026-10-12")
    assert legacy.status == "refetched_after_adjustment_change"

    serve(DAY_ONE + DAY_TWO + DAY_THREE + DAY_FOUR)  # VBT re-fetches only day three onward
    with pytest.raises(AlpacaSipValidationError, match="previously stored bars changed"):
        vbt_side.top_up("SPY", since="2026-10-12")
    assert pd.read_parquet(legacy.path)["open"].tolist()[2] == 105.0  # store unchanged
