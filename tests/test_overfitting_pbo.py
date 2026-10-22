"""Probability of Backtest Overfitting, per VectorBT PRO's cookbook recipe (record-only)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtesting.experiments import execute_experiment
from backtesting.screening.overfitting_pbo import probability_of_backtest_overfitting
from tests.test_spy_donchian_oos import _audit
from tests.test_walk_forward_splitter_vbt import DONCHIAN, _market

pytestmark = pytest.mark.licensed_vectorbt


def _grid(edge: float, seed: int = 11, rows: int = 2_000, columns: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0, 0.01, size=(rows, columns))
    returns[:, 0] += edge
    index = pd.bdate_range("2015-01-02", periods=rows)
    return pd.DataFrame(returns, index=index)


def test_noise_grid_is_near_one_half() -> None:
    # One noise grid's 70 splits are strongly dependent (measured 0.06-0.74 across
    # seeds), so the expectation of 0.5 is checked on the mean of 12 grids (measured 0.525).
    results = [probability_of_backtest_overfitting(_grid(0.0, seed, 1_000)) for seed in range(12)]
    assert all(r.splits == 70 and r.trials == 40 for r in results)  # C(8, 4) halves
    assert 0.4 <= np.mean([r.probability for r in results]) <= 0.6


def test_dominant_setting_has_low_pbo() -> None:
    result = probability_of_backtest_overfitting(_grid(edge=0.004))
    assert result.probability <= 0.05


def test_single_setting_is_rejected() -> None:
    with pytest.raises(ValueError):
        probability_of_backtest_overfitting(_grid(edge=0.0, columns=1))


def test_experiment_records_pbo_next_to_deflated_sharpe_and_never_screens() -> None:
    data = _market()
    result = execute_experiment(DONCHIAN, data, _audit(data), write_output=False)
    assert result.deflated_sharpe is not None
    pbo = result.overfitting_pbo
    assert pbo is not None and pbo.trials == result.deflated_sharpe.trials
    # PBO scores daily Sharpe (the vendor recipe), so it sees one row per trading day.
    days = len(set(pd.DatetimeIndex(data.index).date))
    assert pbo.observations == days and 0.0 <= pbo.probability <= 1.0
    assert not any(
        "pbo" in rule.metric or "overfit" in rule.metric
        for screening in result.screening_results
        for rule in screening.rule_results
    )


def test_executor_memory_options_do_not_change_the_result() -> None:
    # clear_cache/collect_garbage only free memory between splits; the recipe without them must agree.
    import vectorbtpro as vbt

    returns = _grid(edge=0.002, rows=1_000, columns=12)
    splitter = vbt.Splitter.from_purged_kfold(returns.index, n_folds=8, n_test_folds=4)
    sharpe = splitter.apply(
        lambda r: r.vbt.returns(freq="1D").sharpe_ratio(),
        vbt.Takeable(returns),
        merge_func="concat",
        execute_kwargs=dict(show_progress=False),
    )
    train = sharpe.xs("train", level="set").unstack("split").T
    test = sharpe.xs("test", level="set").unstack("split").T
    train = train.loc[train.notna().any(axis=1)]
    best = train.idxmax(axis=1)
    rank = test.rank(axis=1) / (test.shape[1] + 1)
    omega = np.array([rank.loc[split, best[split]] for split in train.index])
    omega = omega[np.isfinite(omega)]
    expected = float(np.mean(np.log(omega / (1 - omega)) <= 0))
    result = probability_of_backtest_overfitting(returns)
    assert (result.probability, result.splits) == (expected, int(omega.size))
