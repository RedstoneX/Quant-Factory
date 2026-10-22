"""Reusable integrity checks for daily OHLCV data."""

import pandas as pd

from market_data.calendars import get_exchange_calendar
from market_data.models import MarketDataConfig, OHLCV_COLUMNS


def normalize_daily_index(frame: pd.DataFrame, timezone: str) -> pd.DataFrame:
    frame = frame.copy()
    index = pd.DatetimeIndex(pd.to_datetime(frame.index, utc=True))
    frame.index = index.tz_convert(timezone).normalize()
    frame.index.name = "Date"
    return frame.sort_index()


def expected_session_gaps(
    frame: pd.DataFrame,
    config: MarketDataConfig,
    calendar=None,
) -> list[str]:
    if frame.empty:
        return []
    if calendar is None:
        calendar = get_exchange_calendar(config)
    expected = calendar.schedule(
        start_date=frame.index[0].date(),
        end_date=frame.index[-1].date(),
    ).index
    actual = frame.index.tz_localize(None).normalize()
    return [date.date().isoformat() for date in expected.difference(actual)]


def clean_and_validate_data(
    frame: pd.DataFrame,
    config: MarketDataConfig,
    completed_through: pd.Timestamp,
    current_date,
    calendar=None,
) -> tuple[pd.DataFrame, list[str]]:
    missing_columns = set(OHLCV_COLUMNS).difference(frame.columns)
    if missing_columns:
        raise RuntimeError(
            "Market data is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    frame = normalize_daily_index(frame.loc[:, list(OHLCV_COLUMNS)], config.market_timezone)
    duplicate_count = int(frame.index.duplicated(keep=False).sum())
    if duplicate_count:
        raise RuntimeError(f"Market data contains {duplicate_count} duplicate timestamps")
    if any(date > current_date for date in frame.index.date):
        raise RuntimeError("Market data contains future-dated rows")

    completed_date = pd.Timestamp(completed_through).date()
    requested_date = pd.Timestamp(config.requested_start).date()
    frame = frame.loc[
        (frame.index.date >= requested_date) & (frame.index.date <= completed_date)
    ]
    if frame.empty:
        raise RuntimeError("Market data is empty after completed-session filtering")

    missing_counts = frame.loc[:, list(OHLCV_COLUMNS)].isna().sum()
    if int(missing_counts.sum()) > 0:
        details = ", ".join(
            f"{column}={int(count)}"
            for column, count in missing_counts.items()
            if count
        )
        raise RuntimeError(f"Market data contains missing required OHLCV values: {details}")
    if frame.index[-1].date() > completed_date:
        raise RuntimeError("Market data includes an incomplete exchange session")

    if calendar is None:
        calendar = get_exchange_calendar(config)
    first_expected = calendar.schedule(
        start_date=config.requested_start,
        end_date=frame.index[0].date(),
    ).index[0]
    if frame.index[0].date() != first_expected.date():
        raise RuntimeError(
            "Market data does not reach the first expected exchange session on or after "
            f"{config.requested_start}"
        )

    gaps = expected_session_gaps(frame, config=config, calendar=calendar)
    if gaps:
        raise RuntimeError(
            "Market data has unexpected missing exchange sessions: " + ", ".join(gaps)
        )
    return frame, gaps
