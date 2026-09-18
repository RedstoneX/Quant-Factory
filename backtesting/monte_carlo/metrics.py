"""Transparent compounded-path metrics."""
import numpy as np

def equity_path(returns):
    values = np.asarray(returns, dtype=float)
    return np.cumprod(1.0 + values)

def cumulative_return(returns): return float(equity_path(returns)[-1] - 1.0)

def maximum_drawdown(returns):
    equity = equity_path(returns)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    return float(np.min(equity / peaks - 1.0))

def path_sharpe(returns, annualization_factor=None):
    values = np.asarray(returns, dtype=float)
    std = values.std(ddof=1)
    if std == 0: return float("nan")
    scale = np.sqrt(annualization_factor) if annualization_factor else 1.0
    return float(values.mean() / std * scale)
