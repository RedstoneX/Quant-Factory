"""Transparent compounded-path metrics."""
import numpy as np

def equity_path(returns):
    values = np.asarray(returns, dtype=float)
    return np.cumprod(1.0 + values)

def cumulative_return(returns): return float(equity_path(returns)[-1] - 1.0)

def returns_accessor(returns, annualization_factor=None):
    """VectorBT PRO returns accessor (columns = paths); one period per row, no risk-free."""
    import pandas as pd
    import vectorbtpro as vbt  # noqa: F401  (registers the .vbt accessor)

    periods = float(annualization_factor) if annualization_factor else 1.0
    return pd.DataFrame(returns).vbt.returns(
        freq="1D",
        year_freq=pd.Timedelta(days=periods),
        defaults=dict(risk_free=0.0, ddof=1),
    )

def maximum_drawdown(returns):
    values = np.asarray(returns, dtype=float)
    return float(returns_accessor(values).max_drawdown().iloc[0])

def path_sharpe(returns, annualization_factor=None):
    values = np.asarray(returns, dtype=float)
    return float(returns_accessor(values, annualization_factor).sharpe_ratio().iloc[0])

def path_metrics(paths, annualization_factor=None):
    """Column-wise terminal return, max drawdown and Sharpe for a (paths, bars) array."""
    values = np.asarray(paths, dtype=float)
    accessor = returns_accessor(values.T, annualization_factor)
    return (
        np.cumprod(1.0 + values, axis=1)[:, -1] - 1.0,
        accessor.max_drawdown().to_numpy(dtype=float),
        accessor.sharpe_ratio().to_numpy(dtype=float),
    )
