"""Plain-English warning when stored Alpaca 1-minute price sets have gone stale.

Reads the manifests the nightly top-up writes (read-only; one-off downloads elsewhere are not topped up) and compares each
set's latest bar with the most recent completed NYSE session (pandas_market_calendars,
as used by the stock campaign code).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal

from market_data.catalog import DEFAULT_CONFIG_PATH, load_data_locations


def _last_completed_session(now: pd.Timestamp) -> pd.Timestamp:
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=(now - pd.Timedelta(days=14)).date(), end_date=now.date()
    )
    closes = schedule.loc[schedule["market_close"] <= now]
    return pd.Timestamp(closes.index[-1]).normalize()


def _day(value: pd.Timestamp) -> str:
    return f"{value:%a} {value.day} {value:%b}"


def stale_price_banner_text(manifest_dirs: list[Path], now: pd.Timestamp | None = None) -> str | None:
    """Warning text, or None when every Alpaca 1-minute set reaches the latest completed session."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now).tz_convert("UTC")
    expected = _last_completed_session(now)
    ends: list[pd.Timestamp] = []
    for folder in manifest_dirs:
        for path in sorted(Path(folder).glob("*.json")) if Path(folder).is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("provider") != "alpaca" or data.get("timeframe") != "1m":
                    continue
                latest = pd.Timestamp(data["latest_timestamp"])
            except (OSError, ValueError, KeyError):
                continue
            latest = latest.tz_localize("UTC") if latest.tzinfo is None else latest.tz_convert("UTC")
            ends.append(latest.tz_convert("America/New_York").tz_localize(None).normalize())
    stale = [end for end in ends if end < expected]
    if not stale:
        return None
    return (
        f"Price data is out of date: {len(stale)} of {len(ends)} stocks end on {_day(max(stale))}"
        f" or earlier; the latest trading day was {_day(expected)}."
    )


def load_stale_price_banner(config_path: Path = DEFAULT_CONFIG_PATH) -> str | None:
    try:
        locations = load_data_locations(config_path)
        return stale_price_banner_text([locations.downloaded_manifest_dir])  # the folder the nightly top-up writes
    except (OSError, ValueError) as exc:  # unreadable config must show, not hide, the warning
        return f"Could not check whether price data is up to date: {exc}"
