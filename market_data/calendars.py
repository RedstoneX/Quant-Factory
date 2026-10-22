"""Exchange-aware completed-session calculations."""

import pandas as pd
import pandas_market_calendars as mcal

from market_data.models import MarketDataConfig


def get_exchange_calendar(config: MarketDataConfig):
    return mcal.get_calendar(config.exchange_calendar)


def resolve_now(config: MarketDataConfig, now: pd.Timestamp | None = None) -> pd.Timestamp:
    if now is None:
        return pd.Timestamp.now(tz=config.market_timezone)
    now = pd.Timestamp(now)
    if now.tzinfo is None:
        return now.tz_localize(config.market_timezone)
    return now.tz_convert(config.market_timezone)


def completed_session_schedule(
    config: MarketDataConfig,
    now: pd.Timestamp | None = None,
    calendar=None,
) -> pd.DataFrame:
    now = resolve_now(config, now)
    if calendar is None:
        calendar = get_exchange_calendar(config)
    schedule = calendar.schedule(
        start_date=config.requested_start,
        end_date=now.date(),
    )
    completed = schedule.loc[schedule["market_close"] <= now.tz_convert("UTC")]
    if completed.empty:
        raise RuntimeError("No completed exchange session exists in the requested range")
    return completed


def latest_completed_session(
    config: MarketDataConfig,
    now: pd.Timestamp | None = None,
    calendar=None,
) -> pd.Timestamp:
    return completed_session_schedule(config, now=now, calendar=calendar).index[-1]
