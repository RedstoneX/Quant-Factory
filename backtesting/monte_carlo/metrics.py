"""Compounded-path metrics from VectorBT PRO's returns accessor."""
import numpy as np
import pandas as pd


def returns_accessor(returns, annualization_factor=None):
    """ReturnsAccessor over bars (rows) x paths (columns); one bar = one day, a year = ann-factor days."""
    import vectorbtpro  # noqa: F401  registers the .vbt accessor

    frame = pd.DataFrame(np.asarray(returns, dtype=float))
    if frame.shape[1] == 1 and np.ndim(returns) == 1:
        frame = frame.iloc[:, 0]
    year = pd.Timedelta(days=float(annualization_factor)) if annualization_factor else "1D"
    return frame.vbt.returns(freq="1D", year_freq=year, defaults=dict(ddof=1, risk_free=0.0))


def _finite_or_nan(value):
    value = float(value)
    return value if np.isfinite(value) else float("nan")


def equity_path(returns):
    return returns_accessor(returns).cumulative(start_value=1.0).to_numpy(dtype=float)


def cumulative_return(returns):
    return float(returns_accessor(returns).total())


def maximum_drawdown(returns):
    return float(returns_accessor(returns).max_drawdown())


def path_sharpe(returns, annualization_factor=None):
    return _finite_or_nan(returns_accessor(returns, annualization_factor).sharpe_ratio())


def path_metrics(paths, annualization_factor=None):
    """Column-wise terminal return, max drawdown and Sharpe for a (paths, bars) array."""
    accessor = returns_accessor(np.asarray(paths, dtype=float).T, annualization_factor)
    sharpe = accessor.sharpe_ratio().to_numpy(dtype=float)
    sharpe = np.where(np.isfinite(sharpe), sharpe, np.nan)
    return accessor.total().to_numpy(dtype=float), accessor.max_drawdown().to_numpy(dtype=float), sharpe


def annualized_return(paths, annualization_factor):
    """Column-wise annualised compounded return for a (paths, bars) array."""
    return returns_accessor(np.asarray(paths, dtype=float).T, annualization_factor).annualized().to_numpy(dtype=float)
