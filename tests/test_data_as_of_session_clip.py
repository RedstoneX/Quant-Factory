"""A saved mid-session data_as_of loads only fully closed exchange sessions."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments.metrics import session_close_metrics
from backtesting.experiments.models import ExecutionConfig, ExperimentConfig, MetricPolicy
from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data import MarketDataConfig
from market_data.calendars import get_exchange_calendar
from orchestration.candidate_data_window import session_closed_data_end

MARKET = MarketDataConfig(
    symbol="SPY",
    provider="test",
    provider_implementation="test",
    interval="1m",
    requested_start="2025-11-24",
    end_date_policy="test",
    adjusted=True,
    exchange_calendar="NYSE",
    market_timezone="America/New_York",
    cache_path=Path("unused.csv"),
)
INTERVAL = pd.Timedelta(MARKET.interval)


def _bars(start: str, end: str) -> pd.DatetimeIndex:
    """SPY-like 1-minute regular-hours bars, labelled by their open."""
    schedule = get_exchange_calendar(MARKET).schedule(start, end)
    parts = [
        pd.date_range(row.market_open, row.market_close - INTERVAL, freq=INTERVAL)
        for row in schedule.itertuples()
    ]
    return parts[0].append(parts[1:])


def _window(index: pd.DatetimeIndex, data_as_of: str) -> pd.DatetimeIndex:
    """The loader keeps bars at or before its end boundary."""
    return index[index <= session_closed_data_end(MARKET, data_as_of)]


def _metrics(index: pd.DatetimeIndex) -> tuple[float, float, float]:
    """Session metrics of a real engine portfolio that is flat at every session close."""
    rng = np.random.default_rng(0)
    close = pd.Series(100.0 * np.exp(rng.normal(0.0, 1e-4, len(index)).cumsum()), index=index)
    local = index.tz_convert(MARKET.market_timezone)
    minute = local.hour * 60 + local.minute
    portfolio = require_vectorbtpro().Portfolio.from_signals(
        close,
        entries=pd.Series(minute == 9 * 60 + 31, index=index),
        exits=pd.Series(minute == 12 * 60, index=index),
        init_cash=100_000.0,
    )
    config = ExperimentConfig(
        experiment_id="session_clip",
        strategy_id="rsi_mean_reversion",
        parameter_combinations=({"window": 7, "entry_threshold": 25, "exit_threshold": 60},),
        market_data=MARKET,
        execution=ExecutionConfig.next_bar_open(
            initial_cash=100_000.0, fees=0.0, slippage=0.0, direction="longonly",
            accumulate=False, leverage=1.0,
        ),
        ranking_columns=("total_return",),
        ranking_ascending=(False,),
        output_path=Path("unused.csv"),
        metric_policy=MetricPolicy(
            sampling="exchange_session_close", periods_per_year=252.0, risk_free_rate=0.0,
            basis="test", source="test",
        ),
    )
    return session_close_metrics(portfolio, pd.DataFrame(index=index), config)


def test_mid_session_data_as_of_ends_on_previous_session_close():
    # 24-26 Nov 2025; 18:20Z is 1:20 PM ET inside the third session.
    end = session_closed_data_end(MARKET, "2025-11-26T18:20:00+00:00")
    assert end == pd.Timestamp("2025-11-25T20:59:00+00:00")


@pytest.mark.parametrize(
    "data_as_of",
    [
        "2025-11-26T20:59:00+00:00",  # last bar of the session: fully observed
        "2025-11-26T21:00:00+00:00",  # exactly at the close
        "2025-11-26T23:30:00+00:00",  # after the close
        "2025-11-29T15:00:00+00:00",  # weekend, between sessions
    ],
)
def test_data_as_of_at_or_after_a_close_is_unchanged(data_as_of):
    assert session_closed_data_end(MARKET, data_as_of) == pd.Timestamp(data_as_of)


def test_early_close_day_uses_the_calendar_close():
    # 28 Nov 2025 closes at 1 PM ET (18:00Z), not 4 PM.
    assert session_closed_data_end(MARKET, "2025-11-28T18:05:00+00:00") == pd.Timestamp(
        "2025-11-28T18:05:00+00:00"
    )
    assert session_closed_data_end(MARKET, "2025-11-28T17:30:00+00:00") == pd.Timestamp(
        "2025-11-26T20:59:00+00:00"
    )


def test_absent_data_as_of_stays_absent():
    assert session_closed_data_end(MARKET, None) is None


@pytest.mark.licensed_vectorbt
def test_clipped_mid_session_window_passes_session_metrics():
    index = _bars("2025-11-24", "2025-11-26")
    mid_session = "2025-11-26T18:20:00+00:00"
    with pytest.raises(RuntimeError, match="partially observed final session"):
        _metrics(index[index <= pd.Timestamp(mid_session)])
    clipped = _window(index, mid_session)
    assert clipped[-1] == pd.Timestamp("2025-11-25T20:59:00+00:00")
    assert all(np.isfinite(_metrics(clipped)))


@pytest.mark.licensed_vectorbt
def test_early_close_window_passes_session_metrics():
    index = _bars("2025-11-25", "2025-11-28")
    after_close = _window(index, "2025-11-28T18:05:00+00:00")
    assert after_close.equals(index)
    assert all(np.isfinite(_metrics(after_close)))
    mid_early = _window(index, "2025-11-28T17:30:00+00:00")
    assert mid_early[-1] == pd.Timestamp("2025-11-26T20:59:00+00:00")
    assert all(np.isfinite(_metrics(mid_early)))
