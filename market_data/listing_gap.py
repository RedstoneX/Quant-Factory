"""Detect ticker reuse in a symbol's stored bars and cut off the earlier security.

Alpaca keys bars by symbol, not by security, so a delisted security's history can sit in front
of a different one that later took the same ticker. The SEC may suspend trading in a security
for at most 10 trading days (Securities Exchange Act of 1934, section 12(k)); a longer silence
in the bars therefore marks a different listing, and only bars after the last such gap are kept.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

MARKET_TIMEZONE = "America/New_York"
EXCHANGE_CALENDAR = "NYSE"

MAX_SUSPENSION_SESSIONS = 10


def cut_at_last_listing_gap(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any] | None]:
    """Keep only bars after the LAST gap of more than 10 NYSE sessions; describe what was cut."""
    if len(frame) < 2:
        return frame, None
    days = frame["timestamp"].dt.tz_convert(MARKET_TIMEZONE).dt.normalize().dt.tz_localize(None).to_numpy()
    changes = np.flatnonzero(days[1:] != days[:-1]) + 1  # first row of each new date
    previous_day, next_day = days[changes - 1], days[changes]
    candidates = changes[(next_day - previous_day) >= np.timedelta64(MAX_SUSPENSION_SESSIONS + 4, "D")]
    if not len(candidates):
        return frame, None
    calendar = mcal.get_calendar(EXCHANGE_CALENDAR)
    cut_row = None
    for row in candidates[::-1]:
        between = calendar.valid_days(
            start_date=pd.Timestamp(days[row - 1]) + pd.Timedelta(days=1),
            end_date=pd.Timestamp(days[row]) - pd.Timedelta(days=1),
        )
        if len(between) > MAX_SUSPENSION_SESSIONS:
            cut_row = int(row)
            break
    if cut_row is None:
        return frame, None
    cut = {
        "discarded_from": frame["timestamp"].iloc[0].isoformat(),
        "discarded_to": frame["timestamp"].iloc[cut_row - 1].isoformat(),
        "discarded_rows": cut_row,
        "reason": f"no bars for more than {MAX_SUSPENSION_SESSIONS} NYSE sessions "
        f"({len(between)} between {frame['timestamp'].iloc[cut_row - 1].date()} and "
        f"{frame['timestamp'].iloc[cut_row].date()}); a trading suspension lasts at most 10 trading "
        "days (Exchange Act 12(k)), so the earlier bars are either a different security that used the "
        "same ticker or the same company before it left and later rejoined the exchanges",
    }
    return frame.iloc[cut_row:].reset_index(drop=True), cut
