"""Vectorised session-close metrics must equal the frozen per-column original exactly."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments.metrics import (
    _portfolio_asset_series,
    _portfolio_value_series,
    extract_sweep_metrics,
    session_close_metrics,
)
from backtesting.experiments.chunking import setting_portfolio
from backtesting.experiments.models import ExecutionConfig, ExperimentConfig, MetricPolicy
from backtesting.vectorbt_runtime import require_vectorbtpro
from market_data import MarketDataConfig
from market_data.calendars import get_exchange_calendar

INTERVAL = pd.Timedelta("30min")
N_COLS = 12
MARKET = MarketDataConfig(
    symbol="SPY",
    provider="test",
    provider_implementation="test",
    interval="30min",
    requested_start="2023-11-20",
    end_date_policy="test",
    adjusted=True,
    exchange_calendar="NYSE",
    market_timezone="America/New_York",
    cache_path=Path("unused.csv"),
)


# ---- frozen copy of the pre-vectorisation implementation (do not edit) ----
def _frozen_session_close_metrics(
    portfolio: Any,
    data: pd.DataFrame,
    config: ExperimentConfig,
) -> tuple[float, float, float]:
    """Calculate return and Sharpe from exact completed session closes."""
    policy = config.metric_policy
    if policy is None or policy.sampling != "exchange_session_close":
        raise RuntimeError("exchange-session metric policy is required")
    value = _portfolio_value_series(portfolio)
    if not data.index.equals(value.index):
        raise RuntimeError("portfolio values must align exactly with source data")
    schedule = get_exchange_calendar(config.market_data).schedule(
        start_date=value.index[0].date(),
        end_date=value.index[-1].date(),
    )
    try:
        interval = pd.Timedelta(config.market_data.interval)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("session metrics require a fixed source interval") from exc
    # Bars are labelled by their open, so the last bar is observed through its end.
    observed_through = value.index[-1] + interval
    completed = schedule.loc[schedule["market_close"] <= observed_through]
    partial = schedule.loc[
        (schedule["market_open"] <= value.index[-1])
        & (schedule["market_close"] > observed_through)
    ]
    if not partial.empty:
        raise RuntimeError("session metrics cannot include a partially observed final session")
    if len(completed) < 2:
        raise RuntimeError("session metrics require at least two completed sessions")
    session_values: list[float] = []
    session_labels: list[object] = []
    assets = _portfolio_asset_series(portfolio)
    for session_label, row in completed.iterrows():
        market_open = pd.Timestamp(row["market_open"]).tz_convert(value.index.tz)
        market_close = pd.Timestamp(row["market_close"]).tz_convert(value.index.tz)
        closing_bar = market_close - interval
        try:
            closing_value = value.loc[closing_bar]
        except KeyError as exc:
            observed = value.loc[(value.index >= market_open) & (value.index < market_close)]
            if observed.empty:
                before = value.index[value.index < market_open]
                after = value.index[value.index >= market_close]
                if (
                    assets is not None
                    and assets.index.equals(value.index)
                    and len(before)
                    and len(after)
                    and float(assets.loc[before[-1]]) == 0.0
                    and float(assets.loc[after[0]]) == 0.0
                ):
                    # A wholly absent exchange session bracketed by verified
                    # flat exposure has the same exact cash equity as the last
                    # observation before it. Retain the zero-return session in
                    # the annualization sample instead of shrinking the sample.
                    closing_value = value.loc[before[-1]]
                else:
                    raise RuntimeError(
                        f"source data is missing the closing bar for exchange session {session_label}"
                    ) from exc
            elif assets is None or not assets.index.equals(value.index):
                raise RuntimeError(
                    f"source data is missing the closing bar for exchange session {session_label}"
                ) from exc
            else:
                last_observed = observed.index[-1]
                if last_observed >= closing_bar or float(assets.loc[last_observed]) != 0.0:
                    raise RuntimeError(
                        f"source data is missing the closing bar for exchange session {session_label}"
                    ) from exc
                # With zero asset exposure, portfolio equity is cash and cannot vary
                # with the missing market-price observation before the session close.
                closing_value = observed.iloc[-1]
        session_labels.append(session_label)
        session_values.append(float(closing_value))
    equity = pd.Series(session_values, index=session_labels, dtype=float)
    previous = pd.Series(
        [config.execution.initial_cash, *equity.iloc[:-1].tolist()],
        index=equity.index,
        dtype=float,
    )
    returns = equity / previous - 1.0
    periods = float(policy.periods_per_year)
    final_ratio = float(equity.iloc[-1]) / config.execution.initial_cash
    annualized_return = final_ratio ** (periods / len(equity)) - 1.0
    period_risk_free = (1.0 + float(policy.risk_free_rate)) ** (1.0 / periods) - 1.0
    excess = returns - period_risk_free
    volatility = float(excess.std(ddof=1))
    if not math.isfinite(volatility):
        raise RuntimeError("session-return sample standard deviation must be finite")
    sharpe = (
        float("nan")
        if volatility == 0.0
        else float(excess.mean()) / volatility * math.sqrt(periods)
    )
    if not math.isfinite(annualized_return):
        raise RuntimeError("session annualized return must be finite")
    return final_ratio - 1.0, annualized_return, sharpe


def _frozen_sweep(portfolio, count, data, config):
    return [
        _frozen_session_close_metrics(setting_portfolio(portfolio, i), data, config)
        for i in range(count)
    ]


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="vectorized_metrics",
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
            sampling="exchange_session_close", periods_per_year=252.0, risk_free_rate=0.03,
            basis="test", source="test",
        ),
    )


def _bar_index(start: str, end: str) -> pd.DatetimeIndex:
    schedule = get_exchange_calendar(MARKET).schedule(start, end)
    parts = [
        pd.date_range(row.market_open, row.market_close - INTERVAL, freq=INTERVAL)
        for row in schedule.itertuples()
    ]
    return parts[0].append(parts[1:]).tz_convert("America/New_York")


def _portfolio(index, flat=True, seed=0):
    """A real engine portfolio with N_COLS random-walk columns.

    flat=False holds every bar; flat=True makes one round trip per session (enter on the
    second bar, exit at noon) so equity moves while every session close is flat.
    """
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.002, size=(len(index), N_COLS))
    close = pd.DataFrame(100.0 * np.exp(steps.cumsum(axis=0)), index=index)
    vbt = require_vectorbtpro()
    if not flat:
        return vbt.Portfolio.from_holding(close, init_cash=100_000.0)
    minute = index.hour * 60 + index.minute
    entries = pd.Series(minute == 10 * 60, index=index)
    exits = pd.Series(minute == 12 * 60, index=index)
    return vbt.Portfolio.from_signals(close, entries=entries, exits=exits, init_cash=100_000.0)


def _assert_identical(portfolio, index):
    config = _config()
    data = pd.DataFrame({"close": 1.0}, index=index)
    expected = _frozen_sweep(portfolio, N_COLS, data, config)
    got = [session_close_metrics(setting_portfolio(portfolio, i), data, config) for i in range(N_COLS)]
    # The statistics now come from VectorBT PRO; its summation order differs
    # from the frozen copy only at the last floating-point digits.
    assert all(all(_same(a, b) for a, b in zip(g, e)) for g, e in zip(got, expected))
    # whole-frame path used by sweeps
    rows = extract_sweep_metrics(portfolio, N_COLS, data=data, config=config)
    for row, e in zip(rows, expected):
        for key, ev in zip(("total_return", "annualized_return", "sharpe_ratio"), e):
            assert _same(row[key], ev)


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15) or (math.isnan(a) and math.isnan(b))


# 2023-11-20..30 has Thanksgiving (closed) and the 24th half-day (13:00 close).
@pytest.mark.licensed_vectorbt
def test_multi_column_with_half_day_matches_frozen():
    index = _bar_index("2023-11-20", "2023-11-30")
    schedule = get_exchange_calendar(MARKET).schedule("2023-11-24", "2023-11-24")
    assert (schedule["market_close"] - schedule["market_open"]).iloc[0] < pd.Timedelta(hours=6)
    _assert_identical(_portfolio(index, flat=False), index)


@pytest.mark.licensed_vectorbt
def test_missing_closing_bar_and_absent_session_flat_matches_frozen():
    index = _bar_index("2023-11-20", "2023-11-30")
    day = index.normalize()
    drop_close = index[day == pd.Timestamp("2023-11-21", tz=index.tz)][-1]
    absent = day == pd.Timestamp("2023-11-27", tz=index.tz)
    index = index[~absent & (index != drop_close)]
    _assert_identical(_portfolio(index, flat=True, seed=1), index)


@pytest.mark.licensed_vectorbt
def test_missing_closing_bar_with_exposure_raises_same_error():
    index = _bar_index("2023-11-20", "2023-11-30")
    drop_close = index[index.normalize() == pd.Timestamp("2023-11-21", tz=index.tz)][-1]
    index = index[index != drop_close]
    portfolio = _portfolio(index, flat=False, seed=2)
    config = _config()
    data = pd.DataFrame({"close": 1.0}, index=index)
    with pytest.raises(RuntimeError) as old:
        _frozen_session_close_metrics(setting_portfolio(portfolio, 0), data, config)
    with pytest.raises(RuntimeError) as new:
        session_close_metrics(setting_portfolio(portfolio, 0), data, config)
    assert str(old.value) == str(new.value)


@pytest.mark.licensed_vectorbt
def test_flat_column_mix_in_one_frame_matches_frozen():
    index = _bar_index("2023-11-20", "2023-11-30")
    drop_close = index[index.normalize() == pd.Timestamp("2023-11-22", tz=index.tz)][-1]
    index = index[index != drop_close]
    portfolio = _portfolio(index, flat=True, seed=3)
    _assert_identical(portfolio, index)
