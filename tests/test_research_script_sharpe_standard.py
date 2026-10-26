"""The two standalone research scripts report the pipeline's standard VectorBT Sharpe.

These checks execute VectorBT PRO's returns accessor, so they run in the licensed
lane. The portable CI job does not install that engine.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

import backtesting.run_mes_overnight_gap_reversal as mes
import backtesting.run_spym_intraday_momentum as spym

pytestmark = pytest.mark.licensed_vectorbt


@dataclass(frozen=True)
class _ClosedTrade:
    net_pnl: float


@dataclass(frozen=True)
class _DailyPnl:
    daily_net_pnl: pd.Series
    completed_trades: tuple[_ClosedTrade, ...]


@dataclass(frozen=True)
class _TradeLedger:
    trade_count: int
    win_rate: float

    def count(self) -> int:
        return self.trade_count


@dataclass(frozen=True)
class _EquityPortfolio:
    value: pd.Series
    trades: _TradeLedger


@dataclass(frozen=True)
class _EligibleSession:
    session_date: object


@dataclass(frozen=True)
class _EligibleBook:
    eligible_sessions: tuple[_EligibleSession, ...]


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


def _mes_bundle(pnl: pd.Series) -> _DailyPnl:
    trades = tuple(_ClosedTrade(net_pnl=float(value)) for value in pnl)
    return _DailyPnl(daily_net_pnl=pnl, completed_trades=trades)


def test_mes_sharpe_matches_pipeline_standard_and_old_formula() -> None:
    pnl = _pnl()
    equity, returns, metrics = mes.schedule_complete_metrics(_mes_bundle(pnl))

    assert metrics["sharpe_ratio"] == pytest.approx(_pipeline_sharpe(equity, mes.INITIAL_CASH), rel=1e-12)
    assert metrics["sharpe_ratio"] == pytest.approx(_hand_sharpe(returns), rel=1e-12)


def _spym_inputs(pnl: pd.Series) -> tuple[_EquityPortfolio, _EligibleBook]:
    value = spym.INITIAL_CASH + pnl.cumsum()
    value.index = pnl.index.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    portfolio = _EquityPortfolio(value=value, trades=_TradeLedger(trade_count=len(pnl), win_rate=0.5))
    sessions = tuple(_EligibleSession(session_date=day.date()) for day in pnl.index)
    return portfolio, _EligibleBook(eligible_sessions=sessions)


def test_spym_sharpe_matches_pipeline_standard_and_old_formula() -> None:
    portfolio, bundle = _spym_inputs(_pnl())
    daily, returns = spym.daily_equity_and_returns(portfolio.value, bundle.eligible_sessions)

    metrics = spym.daily_metrics(portfolio, bundle)

    assert metrics["sharpe_ratio"] == pytest.approx(_pipeline_sharpe(daily, spym.INITIAL_CASH), rel=1e-12)
    assert metrics["sharpe_ratio"] == pytest.approx(_hand_sharpe(returns), rel=1e-12)


def test_spym_sharpe_is_zero_when_equity_is_flat() -> None:
    portfolio, bundle = _spym_inputs(pd.Series(0.0, index=pd.bdate_range("2023-01-03", periods=5)))

    assert spym.daily_metrics(portfolio, bundle)["sharpe_ratio"] == 0.0
