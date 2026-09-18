"""Yahoo Finance access through VectorBT Pro."""

import warnings

import pandas as pd
import vectorbtpro as vbt

from market_data.models import MarketDataConfig, OHLCV_COLUMNS


def download_yahoo_data(
    config: MarketDataConfig,
    completed_through: pd.Timestamp,
) -> tuple[pd.DataFrame, list[str]]:
    end_exclusive = (
        pd.Timestamp(completed_through) + pd.Timedelta(days=1)
    ).date().isoformat()
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        try:
            data = vbt.YFData.pull(
                config.symbol,
                start=config.requested_start,
                end=end_exclusive,
                timeframe=config.interval,
                tz=config.market_timezone,
                auto_adjust=config.adjusted,
                actions=False,
            )
        except Exception as exc:
            raise RuntimeError(f"Yahoo Finance download failed: {exc}") from exc
    if len(data.index) == 0:
        raise RuntimeError("Yahoo Finance returned no market data")
    frame = pd.concat(
        {column: data.get(column) for column in OHLCV_COLUMNS},
        axis=1,
    )
    return frame, [str(warning.message) for warning in caught_warnings]
