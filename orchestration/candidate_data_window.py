"""End a saved candidate's data window on a fully closed exchange session."""

from __future__ import annotations

import pandas as pd

from market_data.calendars import get_exchange_calendar
from market_data.models import MarketDataConfig


def session_closed_data_end(
    config: MarketDataConfig, data_as_of: str | None
) -> pd.Timestamp | None:
    """Return the load boundary for a saved ``data_as_of``.

    Configurations saved before stock dataset ends were snapped to a session close
    can carry a mid-session ``data_as_of``. Session metrics correctly refuse a
    partially observed final session, so the window ends instead on the last bar of
    the last session that closed by then (pandas_market_calendars ``schedule``
    ``market_close``, so early closes are honoured). A ``data_as_of`` that falls
    outside every session, or at/after its close, is returned unchanged, so those
    configurations load exactly the same bars. The saved value itself never changes.
    """
    if data_as_of is None:
        return None
    end = pd.Timestamp(data_as_of)
    try:
        interval = pd.Timedelta(config.interval)
    except (TypeError, ValueError):
        return end
    if end.tzinfo is None or interval <= pd.Timedelta(0) or interval >= pd.Timedelta(days=1):
        return end
    # Bars are labelled by their open; the loader keeps bars at or before ``end``.
    observed_through = end + interval
    # A session labelled the next day can open the evening before (overnight futures).
    schedule = get_exchange_calendar(config).schedule(
        start_date=(end - pd.Timedelta(days=10)).date(),
        end_date=(end + pd.Timedelta(days=1)).date(),
    )
    partial = schedule.loc[
        (schedule["market_open"] <= end) & (schedule["market_close"] > observed_through)
    ]
    if partial.empty:
        return end
    completed = schedule.loc[schedule["market_close"] <= partial["market_open"].iloc[0]]
    if completed.empty:
        raise ValueError(f"no exchange session closed before data_as_of {data_as_of}")
    return (completed["market_close"].iloc[-1] - interval).tz_convert(end.tz)
