"""Old hand-written metric formulas versus the VectorBT PRO returns accessor on fixed data.

Each test names the production site that used to hand-compute the number, states the
old formula inline, and shows the library value agrees to floating-point precision, so
no threshold verdict (Monte Carlo, regime, walk-forward) flips from the replacement.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from backtesting.monte_carlo.metrics import (
    annualized_return,
    cumulative_return,
    equity_path,
    maximum_drawdown,
    path_metrics,
    path_sharpe,
    returns_accessor,
)

pytestmark = pytest.mark.licensed_vectorbt

ANN = 252.0
RETURNS = np.array([0.01, -0.02, 0.015, 0.0, -0.005, 0.03, -0.04, 0.02, 0.01, -0.01])
PATHS = np.vstack(
    [
        RETURNS,
        np.roll(RETURNS, 3),
        np.array([0.05, -0.3, 0.1, 0.1, 0.1, -0.2, 0.0, 0.02, 0.02, 0.02]),
        np.zeros(10),
    ]
)
TOL = dict(rel=1e-12, abs=1e-12)


def old_equity(values):
    return np.cumprod(1.0 + values)


def old_max_drawdown(values):
    equity = old_equity(values)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    return float(np.min(equity / peaks - 1.0))


def old_sharpe(values, ann=None):
    std = values.std(ddof=1)
    if std == 0:
        return float("nan")
    return float(values.mean() / std * (math.sqrt(ann) if ann else 1.0))


def test_monte_carlo_single_path_metrics_match_old_formulas():
    # backtesting/monte_carlo/metrics.py: equity_path / cumulative_return / maximum_drawdown / path_sharpe
    assert equity_path(RETURNS) == pytest.approx(old_equity(RETURNS), **TOL)
    assert cumulative_return(RETURNS) == pytest.approx(float(old_equity(RETURNS)[-1] - 1.0), **TOL)
    assert maximum_drawdown(RETURNS) == pytest.approx(old_max_drawdown(RETURNS), **TOL)
    assert path_sharpe(RETURNS, ANN) == pytest.approx(old_sharpe(RETURNS, ANN), **TOL)
    assert path_sharpe(RETURNS, None) == pytest.approx(old_sharpe(RETURNS), **TOL)
    assert math.isnan(path_sharpe(np.zeros(10), ANN))


@pytest.mark.parametrize("ann", [None, ANN])
def test_monte_carlo_path_metrics_match_old_formulas(ann):
    # backtesting/monte_carlo/metrics.py path_metrics (paths x bars) and runner annualized_return
    terminals, drawdowns, sharpes = path_metrics(PATHS, ann)
    for row, t, d, s in zip(PATHS, terminals, drawdowns, sharpes):
        assert t == pytest.approx(float(old_equity(row)[-1] - 1.0), **TOL)
        assert d == pytest.approx(old_max_drawdown(row), **TOL)
        assert s == pytest.approx(old_sharpe(row, ann), nan_ok=True, **TOL)
    if ann:
        old_annualized = np.power(1.0 + terminals, ann / PATHS.shape[1]) - 1.0
        assert annualized_return(PATHS, ann) == pytest.approx(old_annualized, **TOL)


def test_monte_carlo_threshold_verdicts_do_not_flip():
    # backtesting/monte_carlo/runner.py loss / drawdown-breach / lower-percentile checks
    terminals, drawdowns, _ = path_metrics(PATHS, ANN)
    old_terminals = np.array([old_equity(r)[-1] - 1.0 for r in PATHS])
    old_drawdowns = np.array([old_max_drawdown(r) for r in PATHS])
    for threshold in (0.0, 0.25, 0.5):
        assert (float(np.mean(terminals < 0)) <= threshold) == (float(np.mean(old_terminals < 0)) <= threshold)
    for limit in (0.05, 0.1, 0.3):
        assert (float(np.mean(drawdowns <= -limit)) <= 0.5) == (float(np.mean(old_drawdowns <= -limit)) <= 0.5)
    for pct in (5.0, 25.0):
        assert np.percentile(terminals, pct) == pytest.approx(np.percentile(old_terminals, pct), **TOL)


def test_regime_volatility_and_sharpe_match_old_formulas():
    # backtesting/robustness/regimes.py: rolling SMA, realised vol, per-regime Sharpe
    import vectorbtpro  # noqa: F401  registers the .vbt accessor

    index = pd.date_range("2024-01-01", periods=10, freq="D")
    close = pd.Series(100.0 * np.cumprod(1.0 + RETURNS), index=index)
    window = 4
    old_sma = close.rolling(window, min_periods=window).mean()
    new_sma = close.vbt.rolling_mean(window, minp=window)
    pd.testing.assert_series_equal(new_sma, old_sma, check_names=False, rtol=1e-12, atol=1e-12)
    period_returns = close.pct_change(fill_method=None)
    old_vol = period_returns.rolling(window, min_periods=window).std(ddof=1) * math.sqrt(ANN)
    new_vol = returns_accessor(period_returns.to_numpy(dtype=float), ANN).rolling_annualized_volatility(window, minp=window)
    np.testing.assert_allclose(new_vol.to_numpy(dtype=float), old_vol.to_numpy(dtype=float), rtol=1e-12, atol=1e-12)
    values = RETURNS[:5]
    assert path_sharpe(values, ANN) == pytest.approx(old_sharpe(values, ANN), **TOL)
    for minimum_sharpe in (-1.0, 0.0, 1.0):
        assert (path_sharpe(values, ANN) >= minimum_sharpe) == (old_sharpe(values, ANN) >= minimum_sharpe)


def test_walk_forward_fold_aggregate_matches_old_formulas():
    # backtesting/walk_forward/runner.py _aggregate: endpoint equity, compounded, max drawdown, un-annualised Sharpe
    fold_returns = pd.Series([0.04, -0.02, 0.03, -0.05, 0.01], dtype=float)
    old_equity_series = (1.0 + fold_returns).cumprod()
    old_dd = float((old_equity_series / old_equity_series.cummax().clip(lower=1.0) - 1.0).min())
    old_sharpe_value = float(fold_returns.mean() / fold_returns.std(ddof=1))
    accessor = returns_accessor(fold_returns.to_numpy(dtype=float))
    np.testing.assert_allclose(accessor.cumulative(start_value=1.0).to_numpy(), old_equity_series.to_numpy(), rtol=1e-12)
    assert float(accessor.total()) == pytest.approx(float(old_equity_series.iloc[-1] - 1.0), **TOL)
    assert float(accessor.max_drawdown()) == pytest.approx(old_dd, **TOL)
    assert float(accessor.sharpe_ratio()) == pytest.approx(old_sharpe_value, **TOL)
