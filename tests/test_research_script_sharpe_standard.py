"""The two standalone research scripts report the pipeline's standard VectorBT Sharpe."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import backtesting.run_mes_overnight_gap_reversal as mes
import backtesting.run_spym_intraday_momentum as spym


def _pipeline_sharpe(equity: pd.Series, initial_cash: float) -> float:
    """The `sharpe_ratio` the pipeline records (backtesting/experiments/metrics.py)."""
    import vectorbtpro as vbt

    returns = vbt.ReturnsAccessor.from_value(
        equity.reset_index(drop=True),
        init_value=initial_cash,
        freq="1D",
        year_freq=pd.Timedelta(days=252),
        defaults=dict(risk_free=0.0, ddof=1),
    )
    return float(returns.sharpe_ratio())


def _hand_sharpe(returns: pd.Series) -> float:
    """The formula both scripts used before switching to VectorBT."""
    return float(returns.mean() / returns.std(ddof=1) * 252**0.5)


def _pnl(sessions: int = 300) -> pd.Series:
    rng = np.random.default_rng(7)
    index = pd.bdate_range("2023-01-03", periods=sessions)
    return pd.Series(rng.normal(3.0, 40.0, sessions), index=index)


def test_mes_sharpe_matches_pipeline_standard_and_old_formula() -> None:
    pnl = _pnl()
    trades = tuple(SimpleNamespace(net_pnl=value) for value in pnl)
    bundle = SimpleNamespace(daily_net_pnl=pnl, completed_trades=trades)

    equity, returns, metrics = mes.schedule_complete_metrics(bundle)

    assert metrics["sharpe_ratio"] == pytest.approx(_pipeline_sharpe(equity, mes.INITIAL_CASH), rel=1e-12)
    assert metrics["sharpe_ratio"] == pytest.approx(_hand_sharpe(returns), rel=1e-12)


def _spym_inputs(pnl: pd.Series):
    value = spym.INITIAL_CASH + pnl.cumsum()
    value.index = pnl.index.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    trades = SimpleNamespace(count=lambda: len(pnl), win_rate=0.5)
    sessions = tuple(SimpleNamespace(session_date=day.date()) for day in pnl.index)
    return SimpleNamespace(value=value, trades=trades), SimpleNamespace(eligible_sessions=sessions)


def test_spym_sharpe_matches_pipeline_standard_and_old_formula() -> None:
    portfolio, bundle = _spym_inputs(_pnl())
    daily, returns = spym.daily_equity_and_returns(portfolio.value, bundle.eligible_sessions)

    metrics = spym.daily_metrics(portfolio, bundle)

    assert metrics["sharpe_ratio"] == pytest.approx(_pipeline_sharpe(daily, spym.INITIAL_CASH), rel=1e-12)
    assert metrics["sharpe_ratio"] == pytest.approx(_hand_sharpe(returns), rel=1e-12)


def test_spym_sharpe_is_zero_when_equity_is_flat() -> None:
    portfolio, bundle = _spym_inputs(pd.Series(0.0, index=pd.bdate_range("2023-01-03", periods=5)))

    assert spym.daily_metrics(portfolio, bundle)["sharpe_ratio"] == 0.0
