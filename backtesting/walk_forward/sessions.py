"""Exchange-session alignment for row-sized walk-forward windows.

Windows are declared in rows. On intraday data every cut moves forward to the
first bar of the next exchange session, so no session straddles two partitions
(a futures session runs across midnight UTC, so calendar dates cannot be used).
Sessions come from the exchange calendar's schedule (pandas_market_calendars
``MarketCalendar.schedule``); bars are assigned to the latest session open at or
before them with ``pandas.Index.searchsorted``.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

_PAD = pd.Timedelta(days=7)


def boundary_label(value: Any, session_aligned: bool) -> str:
    """Date for daily bars (unchanged); full timestamp for session-aligned intraday bars."""
    if session_aligned:
        return pd.Timestamp(value).isoformat()
    return str(value.date()) if hasattr(value, "date") else str(value)


def alignment_for(data: pd.DataFrame, market_data: object) -> dict[str, str] | None:
    """Session alignment for bars shorter than a day; ``None`` keeps daily behaviour."""
    try:
        intraday = pd.Timedelta(str(getattr(market_data, "interval"))) < pd.Timedelta(days=1)
    except (TypeError, ValueError):
        intraday = False
    if not intraday or not isinstance(data.index, pd.DatetimeIndex):
        return None
    return {
        "exchange_calendar": str(getattr(market_data, "exchange_calendar")),
        "interval": str(getattr(market_data, "interval")),
    }


class SessionGrid:
    """Ordinal exchange sessions over a time span, from the calendar schedule."""

    def __init__(self, alignment: Mapping[str, str], first: pd.Timestamp, last: pd.Timestamp):
        first, last = _utc(first), _utc(last)
        schedule = mcal.get_calendar(alignment["exchange_calendar"]).schedule(
            start_date=(first - _PAD).date(), end_date=(last + _PAD).date()
        )
        if schedule.empty:
            raise ValueError("exchange calendar produced no sessions for walk-forward windows")
        self.opens = pd.DatetimeIndex(schedule["market_open"]).tz_convert("UTC")
        # A session owns every bar from its open to the next open (overnight and weekend bars
        # included), so one session's maximum bar count is the longest such span: the most rows
        # a cut can move forward, and so the most a session-aligned window can exceed its size.
        longest = max(
            self.opens.to_series().diff().max() if len(self.opens) > 1 else pd.Timedelta(0),
            (schedule["market_close"] - schedule["market_open"]).max(),
        )
        self.max_session_rows = max(1, math.ceil(longest / pd.Timedelta(alignment["interval"])))

    def session_of(self, values: Any) -> np.ndarray:
        stamps = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
        return self.opens.searchsorted(stamps, side="right") - 1

    def ordinal(self, label: str) -> int:
        return int(self.session_of([label])[0])


def _utc(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def grid_for_labels(alignment: Mapping[str, str] | None, labels: list[str]) -> SessionGrid | None:
    if alignment is None:
        return None
    if not isinstance(alignment, Mapping) or set(alignment) != {"exchange_calendar", "interval"}:
        raise ValueError("walk-forward session alignment is malformed")
    return SessionGrid(alignment, min(labels), max(labels))


def grid_for_window(window: object, first: Any, last: Any) -> SessionGrid | None:
    """Exchange sessions for a session-aligned (intraday) window; ``None`` for daily windows."""
    calendar = getattr(window, "session_calendar", None)
    if calendar is None:
        return None
    alignment = {"exchange_calendar": calendar, "interval": getattr(window, "session_interval")}
    return SessionGrid(alignment, first, last)


def size_within(actual: int, declared: int, grid: SessionGrid | None, open_ended: bool = False) -> bool:
    """Exact rows for daily data; ``[declared, declared + one session)`` when session-aligned.

    ``open_ended`` is for expanding train windows, whose end drifts with every earlier cut.
    """
    if grid is None:
        return actual == declared
    return declared <= actual and (open_ended or actual < declared + grid.max_session_rows)


def require_session_boundary(
    fold_id: str, before_end: Any, after_start: Any, grid: SessionGrid | None
) -> None:
    """Refuse a cut that leaves one exchange session on both sides of a boundary."""
    if grid is None:
        return
    before, after = grid.session_of([before_end, after_start])
    if not before < after:
        raise ValueError(f"{fold_id}: window boundary splits an exchange session")
