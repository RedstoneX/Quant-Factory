"""Sharpe and max drawdown come from VectorBT PRO and match the old hand formulas."""
import numpy as np
import pandas as pd
import pytest

from backtesting.monte_carlo.metrics import maximum_drawdown, path_metrics, path_sharpe
from backtesting.robustness.regimes import _sharpe

pytestmark = pytest.mark.licensed_vectorbt
RTOL = 1e-12


def _old_drawdown(r):
    eq = np.cumprod(1.0 + r)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], eq)))[1:]
    return float(np.min(eq / peaks - 1.0))


def _old_sharpe(r, af=None):
    return float(r.mean() / r.std(ddof=1) * (np.sqrt(af) if af else 1.0))


def _paths():
    return np.random.default_rng(7).normal(0.001, 0.02, (6, 400))


@pytest.mark.parametrize("af", [None, 252])
def test_monte_carlo_path_metrics_match_hand_formulas(af):
    paths = _paths()
    _, drawdown, sharpe = path_metrics(paths, af)
    for i, row in enumerate(paths):
        assert drawdown[i] == pytest.approx(_old_drawdown(row), rel=RTOL)
        assert sharpe[i] == pytest.approx(_old_sharpe(row, af), rel=RTOL)
        assert path_sharpe(row, af) == pytest.approx(sharpe[i], rel=RTOL)
        assert maximum_drawdown(row) == pytest.approx(drawdown[i], rel=RTOL)


def test_zero_volatility_is_nan_and_regime_sharpe_is_none():
    assert np.isnan(path_sharpe(np.zeros(10), 252))
    assert _sharpe(np.zeros(10), 252) is None
    assert _sharpe(np.array([0.01]), 252) is None


def test_regime_sharpe_matches_hand_formula():
    row = _paths()[0]
    assert _sharpe(row, 252) == pytest.approx(_old_sharpe(row, 252), rel=RTOL)


def test_session_metrics_with_zero_risk_free_match_hand_formulas():
    import vectorbtpro as vbt  # noqa: F401

    r = pd.Series(_paths()[1])
    acc = r.vbt.returns(freq="1D", year_freq=pd.Timedelta(days=252), defaults=dict(risk_free=0.0, ddof=1))
    assert float(acc.sharpe_ratio()) == pytest.approx(_old_sharpe(r.to_numpy(), 252), rel=RTOL)
    baseline = pd.concat([pd.Series([10_000.0]), 10_000.0 * (1 + r).cumprod()], ignore_index=True)
    assert float(acc.max_drawdown()) == pytest.approx(float((baseline / baseline.cummax() - 1).min()), rel=RTOL)
