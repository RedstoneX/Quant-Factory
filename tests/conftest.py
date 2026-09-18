"""Deterministic fixtures for market-data tests."""

import pandas as pd
import pytest

from market_data.calendars import get_exchange_calendar
from market_data.models import MarketDataConfig


@pytest.fixture
def market_config(tmp_path) -> MarketDataConfig:
    return MarketDataConfig(
        symbol="SPY",
        provider="Yahoo Finance",
        provider_implementation="vectorbtpro.YFData.pull",
        interval="1 day",
        requested_start="2016-01-01",
        end_date_policy="Latest completed NYSE session available from provider",
        adjusted=True,
        exchange_calendar="NYSE",
        market_timezone="America/New_York",
        cache_path=tmp_path / "spy.csv",
        legacy_cache_paths=(tmp_path / "legacy.csv",),
    )


@pytest.fixture
def market_frame_factory(market_config):
    def make(start: str, end: str) -> pd.DataFrame:
        sessions = get_exchange_calendar(market_config).schedule(
            start_date=start,
            end_date=end,
        ).index
        index = sessions.tz_localize(market_config.market_timezone)
        values = pd.Series(range(100, 100 + len(index)), index=index, dtype=float)
        return pd.DataFrame(
            {
                "Open": values,
                "High": values + 1,
                "Low": values - 1,
                "Close": values,
                "Volume": 1_000,
            },
            index=index,
        )

    return make
