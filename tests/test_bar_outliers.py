"""Suspect-bar flagging: highfrequency rmOutliersTrades advanced rule on synthetic one-minute bars."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import market_data
from market_data import load_market_data
from market_data.bar_outliers import flag_suspect_bars
from market_data.models import MarketDataConfig
from tests.test_alpaca_sip_provider import BarServer, bar, locations, manifest_file, provider

START = pd.Timestamp("2026-10-13T13:30:00Z")  # a Tuesday, regular-session open
DATASET_ID = "equities_SPY_1m_alpaca_sip"


def walk(count: int, seed: int = 7, start: pd.Timestamp = START, step: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0.0, step, count))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(start, periods=count, freq="min", tz="UTC"),
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
        }
    )


def test_one_bar_spike_that_reverts_is_the_only_flagged_bar():
    bars = walk(300)
    for column in ("high", "low", "close"):
        bars.loc[150, column] *= 1.05
    flags, counts = flag_suspect_bars(bars)
    assert flags[flags].index.tolist() == [150]
    assert counts == {"high": 1, "low": 1, "close": 1, "any": 1}


def test_level_shift_that_stays_is_not_flagged():
    bars = walk(300)
    for column in ("high", "low", "close"):
        bars.loc[150:, column] *= 1.05
    flags, counts = flag_suspect_bars(bars)
    assert counts["any"] == 0
    assert not flags.any()


def test_clean_random_walk_over_several_days_has_no_flags():
    days = [walk(390, seed=seed, start=START + pd.Timedelta(days=seed)) for seed in range(5)]
    flags, counts = flag_suspect_bars(pd.concat(days, ignore_index=True))
    assert counts == {"high": 0, "low": 0, "close": 0, "any": 0}
    assert len(flags) == 5 * 390


def test_flags_follow_the_rows_when_input_is_unsorted():
    bars = walk(300)
    bars.loc[40, "high"] *= 1.05
    shuffled = bars.sample(frac=1.0, random_state=3)
    flags, counts = flag_suspect_bars(shuffled)
    assert flags[flags].index.tolist() == [40]
    assert counts["high"] == 1 and counts["any"] == 1


def test_tiny_and_empty_inputs_do_not_fail():
    assert flag_suspect_bars(walk(0))[1]["any"] == 0
    assert flag_suspect_bars(walk(1))[1]["any"] == 0
    assert flag_suspect_bars(walk(7))[1]["any"] == 0


def sip_bars(spike_at: int | None = 60, count: int = 120) -> list[dict]:
    rng = np.random.default_rng(11)
    prices = 100.0 + np.cumsum(rng.normal(0.0, 0.01, count))
    bars = []
    for index, price in enumerate(prices):
        stamp = (START + pd.Timedelta(minutes=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
        bars.append(bar(stamp, float(price * (1.05 if index == spike_at else 1.0))))
    return bars


def config() -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="alpaca",
        provider_implementation=f"verified_local_catalog:{DATASET_ID}",
        interval="1m",
        requested_start=START.isoformat(),
        end_date_policy="fixed",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=Path("informational/only.parquet"),
    )


@pytest.fixture
def topped_up(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "load_data_locations", lambda: locations(tmp_path))
    server = BarServer(sip_bars(), page_size=1000)
    provider(tmp_path, server, now="2026-10-13T23:00:00Z").top_up("SPY")
    return tmp_path


def test_manifest_records_suspect_count_examples_and_method(topped_up):
    manifest = json.loads(manifest_file(topped_up).read_text())
    assert manifest["suspect_bar_count"] == 1
    assert [pd.Timestamp(item) for item in manifest["suspect_bar_examples"]] == [START + pd.Timedelta(minutes=60)]
    assert "rmOutliersTrades" in manifest["suspect_bar_method"]
    assert manifest["row_count"] == 120  # the stored file keeps the flagged bar


def test_loader_drops_the_flagged_bar_and_reports_the_count(topped_up):
    end = START + pd.Timedelta(minutes=119)
    result = load_market_data(config(), now=end, allow_download=False)
    assert len(result.data) == 119
    assert START + pd.Timedelta(minutes=60) not in result.data.index
    assert "1 suspect bar(s) dropped" in result.audit.adjustment_verification
    kept = market_data._load_verified_catalog_data(config(), now=end, drop_suspect_bars=False)
    assert len(kept.data) == 120
    assert "dropped" not in kept.audit.adjustment_verification


def cent_day(count: int = 390, price: float = 46.10, spike_at: int | None = None) -> pd.DataFrame:
    """A thin, flat day: most prints on one price, occasional 1-2 cent moves (cent tick, Rule 612)."""
    rng = np.random.default_rng(5)
    close = price + rng.choice([0.0, 0.0, 0.0, 0.0, 0.01, -0.01, 0.02], size=count)
    if spike_at is not None:
        close[spike_at] = price * 1.2  # XLE-style: a 16-20% print that reverts next bar
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(START, periods=count, freq="min", tz="UTC"),
            "high": close,
            "low": close,
            "close": close,
        }
    )


def test_flat_day_with_cent_moves_has_no_flags():
    flags, counts = flag_suspect_bars(cent_day())
    assert counts["any"] == 0 and not flags.any()


def test_big_spike_on_a_flat_day_is_still_flagged():
    flags, counts = flag_suspect_bars(cent_day(spike_at=200))
    assert flags[flags].index.tolist() == [200]
    assert counts["any"] == 1


def two_listing_bars() -> list[dict]:
    """Ticker reuse: a different security (~$5) in January, then silence, then ~$100 from March."""
    old = [bar(f"2026-01-0{day}T13:3{minute}:00Z", 5.0) for day in (5, 6, 7) for minute in (0, 1)]
    new = [bar(f"2026-03-02T13:3{minute}:00Z", 100.0) for minute in range(5)]
    return old + new


def test_bars_before_a_gap_of_more_than_ten_sessions_are_cut_and_recorded(tmp_path):
    server = BarServer(two_listing_bars(), page_size=1000)
    provider(tmp_path, server, now="2026-03-03T12:00:00Z").top_up("SPY")
    manifest = json.loads(manifest_file(topped := tmp_path).read_text())
    stored = pd.read_parquet(topped / "root" / manifest["canonical_relative_path"])
    assert len(stored) == 5 and (stored["close"] > 90).all()
    assert manifest["row_count"] == 5
    assert manifest["first_available_bar"] == "2026-03-02T13:30:00+00:00"
    cut = manifest["history_cut"]
    assert cut["discarded_from"] == "2026-01-05T13:30:00+00:00"
    assert cut["discarded_to"] == "2026-01-07T13:31:00+00:00"
    assert cut["discarded_rows"] == 6
    assert "12(k)" in cut["reason"]
    # a later incremental top-up keeps the kept start and the record of what was discarded
    server.bars = two_listing_bars() + [bar("2026-03-02T14:00:00Z", 101.0)]
    provider(tmp_path, server, now="2026-03-03T23:00:00Z").top_up("SPY")
    again = json.loads(manifest_file(tmp_path).read_text())
    assert again["row_count"] == 6 and again["history_cut"] == cut
    assert again["first_available_bar"] == manifest["first_available_bar"]


def test_a_gap_of_ten_sessions_or_fewer_is_not_cut(tmp_path):
    bars = [bar("2026-02-02T14:00:00Z", 100.0), bar("2026-02-17T14:00:00Z", 100.0)]  # 9 sessions between
    provider(tmp_path, BarServer(bars, page_size=1000), now="2026-02-18T12:00:00Z").top_up("SPY")
    manifest = json.loads(manifest_file(tmp_path).read_text())
    assert manifest["row_count"] == 2 and "history_cut" not in manifest
