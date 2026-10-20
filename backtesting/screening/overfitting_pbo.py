"""Probability of Backtest Overfitting (PBO): a record-only check on the whole grid.

Follows VectorBT PRO's cookbook recipe "Estimate the probability of backtest
overfitting" (members.vectorbt.pro/cookbook/cross-validation) line for line:
``vbt.Splitter.from_purged_kfold(index, n_folds=8, n_test_folds=4)`` builds the
70 combinatorial train/test halves, ``splitter.apply(..., vbt.Takeable(returns),
merge_func="concat")`` scores every setting on every half, and PBO is the share
of splits whose best train setting ranks at or below the test median
(Bailey, Borwein, Lopez de Prado and Zhu, 2015).

The library has no built-in PBO, so this module is only the vendor recipe.  It
is REPORT-ONLY and never screens an idea out; any threshold is an owner decision.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from backtesting.screening.deflated_sharpe import grid_returns

PBO_FOLDS = 8
PBO_TEST_FOLDS = 4


@dataclass(frozen=True)
class OverfittingPBOResult:
    """Grid-level overfitting estimate; values near 0.5 or higher are no better than chance."""

    probability: float
    splits: int  # splits with a defined train best and test rank (70 when none are missing)
    trials: int
    observations: int
    returns_basis: str | None = None  # "daily" since 20 Oct 2026; None = not labelled


def daily_grid_returns(daily: pd.DataFrame, initial_cash: float) -> pd.DataFrame:
    """Daily returns of a (days x settings) grid of each day's closing value.

    The recipe scores daily Sharpe (freq="1D"), so PBO gets one row per day, not every bar;
    on minute data this also keeps its 70 splits small.
    """
    return grid_returns(daily.to_numpy(dtype=float), initial_cash, daily.index)


def probability_of_backtest_overfitting(
    returns: pd.DataFrame, n_folds: int = PBO_FOLDS, n_test_folds: int = PBO_TEST_FOLDS
) -> OverfittingPBOResult:
    """PBO of a (bars x settings) returns grid simulated once on the full history."""
    if returns.ndim != 2 or returns.shape[1] < 2 or returns.shape[0] < n_folds:
        raise ValueError("PBO needs a (bars x settings) returns grid with >= 2 settings")
    import vectorbtpro as vbt

    splitter = vbt.Splitter.from_purged_kfold(
        returns.index, n_folds=n_folds, n_test_folds=n_test_folds
    )
    sharpe = splitter.apply(
        lambda r: r.vbt.returns(freq="1D").sharpe_ratio(),
        vbt.Takeable(returns),
        merge_func="concat",
        # No per-split clear_cache/collect_garbage: on daily returns (~2.7k rows per setting) the
        # arrays are tiny, and 71 gc.collect calls cost 18.7 of 20.7 s per run [measured, cProfile].
        execute_kwargs=dict(show_progress=False),
    )
    train = sharpe.xs("train", level="set").unstack("split").T
    test = sharpe.xs("test", level="set").unstack("split").T
    # Skill pitfall: a split whose settings all lack a train Sharpe (no trades) has no
    # best setting, and a NaN test rank is not a below-median rank; both are skipped.
    train = train.loc[train.notna().any(axis=1)]
    best = train.idxmax(axis=1)
    rank = test.rank(axis=1) / (test.shape[1] + 1)
    omega = np.array([rank.loc[split, best[split]] for split in train.index])
    omega = omega[np.isfinite(omega)]
    pbo = np.mean(np.log(omega / (1 - omega)) <= 0) if omega.size else np.nan
    return OverfittingPBOResult(
        probability=float(pbo),
        splits=int(omega.size),
        trials=int(returns.shape[1]),
        observations=int(returns.shape[0]),
    )
