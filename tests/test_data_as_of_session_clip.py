"""A saved mid-session data_as_of loads only fully closed exchange sessions."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments.metrics import session_close_metrics
from market_data.calendars import get_exchange_calendar
from orchestration.candidate_data_window import session_closed_data_end

MARKET = SimpleNamespace(exchange_calendar="NYSE", interval="1m")
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
    rng = np.random.default_rng(0)
    value = pd.Series(100_000.0 * np.exp(rng.normal(0.0, 1e-4, len(index)).cumsum()), index=index)
    config = SimpleNamespace(
        metric_policy=SimpleNamespace(
            sampling="exchange_session_close", periods_per_year=252.0, risk_free_rate=0.0
        ),
        market_data=MARKET,
        execution=SimpleNamespace(initial_cash=100_000.0),
    )
    portfolio = SimpleNamespace(value=value, assets=pd.Series(0.0, index=index))
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
