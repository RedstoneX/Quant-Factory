"""Exchange-calendar behavior."""

import pandas as pd

from market_data.calendars import latest_completed_session


def test_weekend_and_holiday_use_prior_session(market_config) -> None:
    weekend = pd.Timestamp("2025-01-11 12:00", tz=market_config.market_timezone)
    holiday = pd.Timestamp("2025-01-20 12:00", tz=market_config.market_timezone)
    assert latest_completed_session(market_config, weekend).date().isoformat() == "2025-01-10"
    assert latest_completed_session(market_config, holiday).date().isoformat() == "2025-01-17"


def test_early_close_completion(market_config) -> None:
    before = pd.Timestamp("2025-07-03 12:30", tz=market_config.market_timezone)
    after = pd.Timestamp("2025-07-03 13:30", tz=market_config.market_timezone)
    assert latest_completed_session(market_config, before).date().isoformat() == "2025-07-02"
    assert latest_completed_session(market_config, after).date().isoformat() == "2025-07-03"
