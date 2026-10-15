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


def eastern_label(value: str | datetime, fmt: str | None = None) -> str:
    """Human label such as "Oct 14, 2026 · 9:40 PM ET"; EDT/EST is applied by zoneinfo."""
    local = eastern_datetime(value)
    if fmt is not None:
        return local.strftime(fmt.replace("%Z", "ET"))
    return f"{local:%b} {local.day}, {local.year} · {local.hour % 12 or 12}:{local:%M %p} ET"


def eastern_time_label(value: str | datetime) -> str:
    """Clock-only label such as "9:40:05 PM ET"."""
    local = eastern_datetime(value)
    return f"{local.hour % 12 or 12}:{local:%M:%S %p} ET"


def eastern_range_label(value: object) -> str | None:
    """Eastern "start – end" label for an ISO "start..end" range with times; None when not such a range."""
    if isinstance(value, str) and "T" in value:
        for separator in ("..", "/"):
            if separator in value:
                try:
                    return " – ".join(eastern_label(part.strip()) for part in value.split(separator, 1))
                except ValueError:
                    return None
    return None


def eastern_naive_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Eastern wall-clock chart index: pandas tz_convert, then drop the offset so browsers cannot reconvert it."""
    return index.tz_convert(EASTERN).tz_localize(None)
