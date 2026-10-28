"""The two standalone research scripts report VectorBT's max drawdown, matching the old formula.

Licensed lane: these execute VectorBT PRO's returns accessor.
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


def _pnl(sessions: int = 300) -> pd.Series:
    rng = np.random.default_rng(7)
    return pd.Series(rng.normal(3.0, 40.0, sessions), index=pd.bdate_range("2023-01-03", periods=sessions))


def _spym_inputs(pnl: pd.Series) -> tuple[_EquityPortfolio, _EligibleBook]:
    value = spym.INITIAL_CASH + pnl.cumsum()
    value.index = pnl.index.tz_localize("America/New_York") + pd.Timedelta(hours=16)
    portfolio = _EquityPortfolio(value=value, trades=_TradeLedger(trade_count=len(pnl), win_rate=0.5))
    return portfolio, _EligibleBook(eligible_sessions=tuple(_EligibleSession(day.date()) for day in pnl.index))


def _hand_drawdown(equity: pd.Series, initial_cash: float) -> float:
    """The formula both scripts used before switching to VectorBT (starting cash counts as a peak)."""
    path = pd.concat([pd.Series([initial_cash]), equity.reset_index(drop=True)], ignore_index=True)
    return float((path / path.cummax() - 1.0).min())


def test_mes_max_drawdown_matches_old_formula() -> None:
    pnl = _pnl()
    bundle = _DailyPnl(daily_net_pnl=pnl, completed_trades=tuple(_ClosedTrade(float(v)) for v in pnl))
    equity, _returns, metrics = mes.schedule_complete_metrics(bundle)

    assert metrics["max_drawdown"] < 0.0
    assert metrics["max_drawdown"] == pytest.approx(_hand_drawdown(equity, mes.INITIAL_CASH), rel=1e-12)


def test_spym_max_drawdown_matches_old_formula() -> None:
    portfolio, bundle = _spym_inputs(_pnl())
    daily, _returns = spym.daily_equity_and_returns(portfolio.value, bundle.eligible_sessions)

    metrics = spym.daily_metrics(portfolio, bundle)

    assert metrics["max_drawdown"] < 0.0
    assert metrics["max_drawdown"] == pytest.approx(_hand_drawdown(daily, spym.INITIAL_CASH), rel=1e-12)


def test_spym_max_drawdown_is_zero_when_equity_is_flat() -> None:
    portfolio, bundle = _spym_inputs(pd.Series(0.0, index=pd.bdate_range("2023-01-03", periods=5)))

    assert spym.daily_metrics(portfolio, bundle)["max_drawdown"] == 0.0
