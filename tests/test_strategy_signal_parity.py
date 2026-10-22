"""Bit-for-bit parity of the vectorised strategy signals against the pre-change bar loops.

Each ``_reference_*`` function is the PRE-CHANGE REFERENCE: the Python loop that the strategy module carried before
the cleanup (commit ce1d613), copied verbatim and kept only here.  The fixtures feed the same synthetic five-minute
series, with a holiday gap, an early-close session, a missing bar and a NaN bar, to both the reference and the
live module, and every entry, exit, stop and take-profit array must be identical.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies import mes_five_bar_run_exhaustion, mes_sma_crossover_candidate, mes_vwap_orb_candidate, rule_spec_evaluation
from strategies.mes_opening_range_breakout import _schedule

FIVE = pd.Timedelta(minutes=5)
NY = "America/New_York"


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    """Five-minute MES-like bars, 2025-11-24 .. 2025-12-02: Thanksgiving gap and a 13:00 early close on 28 Nov."""
    schedule = _schedule(pd.DatetimeIndex([pd.Timestamp("2025-11-24", tz=NY), pd.Timestamp("2025-12-02", tz=NY)]))
    index = pd.DatetimeIndex([]).tz_localize("UTC")
    for _, row in schedule.iterrows():
        index = index.append(pd.date_range(row["market_open"], row["market_close"], freq=FIVE, inclusive="left").tz_convert("UTC"))
    rng = np.random.default_rng(7)
    n = len(index)
    close = 6000.0 + np.round(rng.normal(0, 3.0, n).cumsum() / 0.25) * 0.25
    open_ = np.r_[close[0], close[:-1]] + np.round(rng.normal(0, 1.0, n) / 0.25) * 0.25
    high = np.maximum(open_, close) + np.round(rng.uniform(0, 4.0, n) / 0.25) * 0.25
    low = np.minimum(open_, close) - np.round(rng.uniform(0, 4.0, n) / 0.25) * 0.25
    data = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": rng.integers(1, 500, n).astype(float)}, index=index)
    # A session with a missing bar and one with a NaN close exercise the skip paths (unchanged code).
    data = data.drop(pd.Timestamp("2025-11-25 11:00", tz=NY).tz_convert("UTC"))
    data.loc[pd.Timestamp("2025-11-26 12:00", tz=NY).tz_convert("UTC"), "Close"] = np.nan
    # 24 Nov: a long breakout at 09:50 whose next open gaps below the range (stop invalid), then a valid one at 10:00.
    at = lambda hhmm: pd.Timestamp(f"2025-11-24 {hhmm}", tz=NY).tz_convert("UTC")  # noqa: E731
    data.loc[at("09:50"), ["Open", "High", "Low", "Close"]] = [6000.0, 6130.0, 5999.0, 6129.0]
    data.loc[at("09:55"), ["Open", "High", "Low", "Close"]] = [5900.0, 5901.0, 5899.0, 5900.5]
    data.loc[at("10:00"), ["Open", "High", "Low", "Close"]] = [6120.0, 6131.0, 6119.0, 6130.0]
    data.loc[at("10:05"), "Open"] = 6130.0
    return data


def _sessions(frame: pd.DataFrame):
    schedule = _schedule(frame.index)
    for _, row in schedule.iterrows():
        session_open = pd.Timestamp(row["market_open"]).tz_convert("UTC")
        session_close = pd.Timestamp(row["market_close"]).tz_convert("UTC")
        expected = pd.date_range(session_open, session_close, freq=FIVE, inclusive="left")
        yield session_open, session_close, expected


def _full_session(frame: pd.DataFrame, session_open, session_close, expected) -> pd.DataFrame | None:
    if session_close - session_open != pd.Timedelta(hours=6, minutes=30) or not expected.isin(frame.index).all():
        return None
    day = frame.loc[expected]
    if not np.isfinite(day.to_numpy(dtype=float)).all() or (day["Volume"] <= 0).any() or (day[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None
    return day


# ----------------------------------------------------------------------------------------------------------------
# PRE-CHANGE REFERENCE: mes_sma_crossover_candidate inner loop (verbatim).
def _reference_sma_cross(day: pd.DataFrame, expected: pd.DatetimeIndex, session_close: pd.Timestamp):
    fast = day["Close"].rolling(10, min_periods=10).mean()
    slow = day["Close"].rolling(30, min_periods=30).mean()
    exit_signal = session_close - pd.Timedelta(minutes=10)
    for position in range(30, len(day) - 2):
        timestamp = expected[position]
        if timestamp >= exit_signal:
            break
        previous_fast, previous_slow = fast.iloc[position - 1], slow.iloc[position - 1]
        current_fast, current_slow = fast.iloc[position], slow.iloc[position]
        if previous_fast <= previous_slow and current_fast > current_slow:
            return timestamp, "long", exit_signal
        if previous_fast >= previous_slow and current_fast < current_slow:
            return timestamp, "short", exit_signal
    return None


def test_sma_crossover_matches_reference(frame: pd.DataFrame) -> None:
    result = mes_sma_crossover_candidate.generate_candidate_signals(frame)
    expected = {name: pd.Series(False, index=frame.index) for name in ("entries", "exits", "short_entries", "short_exits")}
    found = 0
    for session_open, session_close, bars in _sessions(frame):
        day = _full_session(frame, session_open, session_close, bars)
        if day is None:
            continue
        selected = _reference_sma_cross(day, bars, session_close)
        if selected is None:
            continue
        found += 1
        timestamp, direction, exit_signal = selected
        expected["entries" if direction == "long" else "short_entries"].at[timestamp] = True
        expected["exits" if direction == "long" else "short_exits"].at[exit_signal] = True
    assert found >= 2
    for name, series in expected.items():
        pd.testing.assert_series_equal(getattr(result, name), series, check_names=False)


# ----------------------------------------------------------------------------------------------------------------
# PRE-CHANGE REFERENCE: mes_five_bar_run_exhaustion inner loop (verbatim).
def _reference_run_exhaustion(day: pd.DataFrame, run_length: int, minimum_points: float):
    bodies = day["Close"].astype(float) - day["Open"].astype(float)
    completion_times = day.index + FIVE
    selected = None
    for position in range(run_length - 1, len(day)):
        completed_at = completion_times[position]
        local_completed_at = completed_at.tz_convert("America/New_York")
        if local_completed_at.time() < pd.Timestamp("10:00").time():
            continue
        if local_completed_at.time() > pd.Timestamp("14:00").time():
            break
        run = bodies.iloc[position - run_length + 1 : position + 1]
        if (run.abs() < minimum_points).any() or (run == 0).any():
            continue
        if (run > 0).all():
            selected = (day.index[position], "short")
        elif (run < 0).all():
            selected = (day.index[position], "long")
        if selected is not None:
            break
    return selected


@pytest.mark.parametrize("run_length,ticks", [(4, 1), (5, 2), (6, 1)])
def test_run_exhaustion_matches_reference(frame: pd.DataFrame, run_length: int, ticks: int) -> None:
    parameters = {"run_length": run_length, "minimum_ticks_per_bar": ticks}
    result = mes_five_bar_run_exhaustion.generate_signals(frame, parameters)
    expected = {name: pd.Series(False, index=frame.index) for name in ("entries", "exits", "short_entries", "short_exits")}
    found = 0
    for session_open, session_close, bars in _sessions(frame):
        day = _full_session(frame, session_open, session_close, bars)
        if day is None:
            continue
        selected = _reference_run_exhaustion(day, run_length, ticks * mes_five_bar_run_exhaustion.MES_TICK_SIZE)
        if selected is None:
            continue
        signal_time, direction = selected
        exit_signal_time = min(signal_time + 2 * FIVE, session_close - pd.Timedelta(minutes=15))
        if signal_time + FIVE not in frame.index or exit_signal_time not in frame.index:
            continue
        found += 1
        expected["entries" if direction == "long" else "short_entries"].at[signal_time] = True
        expected["exits" if direction == "long" else "short_exits"].at[exit_signal_time] = True
    assert found >= 1
    for name, series in expected.items():
        pd.testing.assert_series_equal(getattr(result, name), series, check_names=False)


# ----------------------------------------------------------------------------------------------------------------
# PRE-CHANGE REFERENCE: mes_vwap_orb_candidate inner ``iterrows`` loop (verbatim).
def _reference_vwap_orb(frame, index_set, candidates, vwap, range_high, range_low, breakout_points):
    issues = 0
    for timestamp, candle in candidates.iterrows():
        next_timestamp = timestamp + FIVE
        if next_timestamp not in index_set:
            continue
        height = float(candle["High"] - candle["Low"])
        body_ratio = abs(float(candle["Close"] - candle["Open"])) / height if height > 0 else 0.0
        if body_ratio < mes_vwap_orb_candidate.MINIMUM_BODY_RATIO:
            continue
        long_signal = float(candle["Close"]) >= range_high + breakout_points and float(candle["Close"]) > float(vwap.at[timestamp])
        short_signal = float(candle["Close"]) <= range_low - breakout_points and float(candle["Close"]) < float(vwap.at[timestamp])
        if not long_signal and not short_signal:
            continue
        direction = "long" if long_signal else "short"
        entry_price = float(frame.at[next_timestamp, "Open"])
        stop_price = range_low if direction == "long" else range_high
        risk = entry_price - stop_price if direction == "long" else stop_price - entry_price
        if risk <= 0 or entry_price <= 0:
            issues += 1
            continue
        return (timestamp, direction, entry_price, risk), issues
    return None, issues


def test_vwap_orb_matches_reference(frame: pd.DataFrame) -> None:
    bundle = mes_vwap_orb_candidate.generate_candidate_signals(frame)
    result = bundle.signals
    index = frame.index
    expected = {name: pd.Series(False, index=index) for name in ("entries", "exits", "short_entries", "short_exits")}
    stop_loss = pd.Series(np.nan, index=index)
    take_profit = pd.Series(np.nan, index=index)
    found = issue_count = 0
    breakout_points = mes_vwap_orb_candidate.BREAKOUT_BUFFER_TICKS * mes_vwap_orb_candidate.MES_TICK_SIZE
    for session_open, session_close, bars in _sessions(frame):
        if not bars.difference(index).empty or session_close - session_open < pd.Timedelta(hours=6, minutes=25):
            continue
        day = frame.loc[bars]
        if not np.isfinite(day.to_numpy(dtype=float)).all() or (day["Volume"] <= 0).any():
            continue
        range_index = pd.date_range(session_open, periods=3, freq=FIVE)
        range_high, range_low = float(day.loc[range_index, "High"].max()), float(day.loc[range_index, "Low"].min())
        typical = (day["High"] + day["Low"] + day["Close"]) / 3.0
        vwap = (typical * day["Volume"]).cumsum() / day["Volume"].cumsum()
        exit_signal_time = session_close - pd.Timedelta(minutes=10)
        candidates = day.loc[(day.index >= session_open + pd.Timedelta(minutes=15)) & (day.index < exit_signal_time)]
        selected, issues = _reference_vwap_orb(frame, set(index), candidates, vwap, range_high, range_low, breakout_points)
        issue_count += issues
        if selected is None:
            continue
        found += 1
        timestamp, direction, entry_price, risk = selected
        expected["entries" if direction == "long" else "short_entries"].at[timestamp] = True
        expected["exits" if direction == "long" else "short_exits"].at[exit_signal_time] = True
        stop_loss.at[timestamp] = risk / entry_price
        take_profit.at[timestamp] = mes_vwap_orb_candidate.TARGET_R_MULTIPLE * (risk / entry_price)
    assert found >= 1 and issue_count >= 1
    for name, series in expected.items():
        pd.testing.assert_series_equal(getattr(result, name), series, check_names=False)
    pd.testing.assert_series_equal(result.stop_loss, stop_loss, check_names=False)
    pd.testing.assert_series_equal(result.take_profit, take_profit, check_names=False)
    assert sum(issue.reason.startswith("next-bar entry") for issue in bundle.issues) == issue_count


# ----------------------------------------------------------------------------------------------------------------
# PRE-CHANGE REFERENCE: rule_spec_evaluation.shift_bars and Evaluator.same_sign_run (verbatim).
def _reference_shift_bars(values: np.ndarray, bars: int) -> np.ndarray:
    result = np.full(values.shape, np.nan)
    if bars < values.shape[0]:
        result[bars:] = values[: values.shape[0] - bars]
    return result


def _reference_same_sign_run(values: np.ndarray) -> np.ndarray:
    signs = np.sign(values)
    signs[~np.isfinite(signs)] = 0.0
    runs = np.zeros(values.shape)
    for row in range(values.shape[0]):
        current = signs[row]
        started = (current != 0).astype(float)
        if row == 0:
            runs[row] = started
            continue
        continuing = (current != 0) & (current == signs[row - 1])
        runs[row] = np.where(continuing, runs[row - 1] + 1.0, started)
    return runs


def test_rule_spec_helpers_match_reference() -> None:
    rng = np.random.default_rng(3)
    values = rng.choice([-2.0, -1.0, 0.0, 1.0, 2.0, np.nan], size=(78, 6))
    values[-1, :] = values[0, :]  # a run must not continue from the end of one session into the next
    np.testing.assert_array_equal(rule_spec_evaluation.RuleEvaluator.same_sign_run(values), _reference_same_sign_run(values))
    for bars in (0, 1, 7, 77, 78, 100):
        np.testing.assert_array_equal(rule_spec_evaluation.shift_bars(values, bars), _reference_shift_bars(values, bars))
