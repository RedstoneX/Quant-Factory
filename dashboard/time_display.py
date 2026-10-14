"""Eastern-time presentation helpers; persisted timestamps remain unchanged."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd


EASTERN = ZoneInfo("America/New_York")


def eastern_datetime(value: str | datetime) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(EASTERN)


def eastern_plot_timestamp(value: str | datetime) -> str:
    """Return Eastern wall time without an offset so browsers cannot reconvert it."""
    return eastern_datetime(value).replace(tzinfo=None).isoformat()


def eastern_session(value: str | datetime) -> str:
    return eastern_datetime(value).date().isoformat()


def eastern_label(value: str | datetime, fmt: str = "%b %d, %Y · %I:%M %p %Z") -> str:
    return eastern_datetime(value).strftime(fmt)


def eastern_naive_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Eastern wall-clock chart index: pandas tz_convert, then drop the offset so browsers cannot reconvert it."""
    return index.tz_convert(EASTERN).tz_localize(None)
