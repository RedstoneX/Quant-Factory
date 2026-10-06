"""Fixed SMA rule timing and exclusion checks."""

import numpy as np
import pandas as pd

from strategies.mes_sma_crossover_candidate import generate_candidate_signals


def _session(*, missing: bool = False, early: bool = False):
    start = pd.Timestamp("2026-10-06T13:30:00Z")
    closes = np.r_[np.full(30, 100.0), np.arange(101.0, 149.0)]
    index = pd.date_range(start, periods=78, freq="5min")
    data = pd.DataFrame({
        "Open": closes, "High": closes + 1, "Low": closes - 1,
        "Close": closes, "Volume": 1,
    }, index=index)
    if missing:
        data = data.drop(index[10])
    schedule = pd.DataFrame({
        "market_open": [start],
        "market_close": [start + pd.Timedelta(hours=4 if early else 6.5)],
    })
    return data, schedule


def test_first_eligible_cross_fills_next_bar_and_exits_at_1555():
    data, schedule = _session()
    signals = generate_candidate_signals(data, schedule=schedule)
    assert list(signals.entries[signals.entries].index) == [data.index[30]]
    assert list(signals.exits[signals.exits].index) == [data.index[76]]
    assert not signals.short_entries.any()


def test_incomplete_and_early_close_sessions_cannot_emit_signals():
    for options in ({"missing": True}, {"early": True}):
        data, schedule = _session(**options)
        signals = generate_candidate_signals(data, schedule=schedule)
        assert not signals.entries.any()
        assert not signals.short_entries.any()
