"""Exact parity of vectorised Monte Carlo resampling/metrics against frozen loop versions."""
import numpy as np
import pytest
from backtesting.monte_carlo.metrics import path_metrics
from backtesting.monte_carlo.models import MonteCarloConfig
from backtesting.monte_carlo.resampling import resample_paths


def _old_resample(values, config):
    source = np.asarray(values, dtype=float)
    rng = np.random.default_rng(config.seed)
    n, sims = len(source), config.simulation_count
    if config.method == "iid_bootstrap":
        return rng.choice(source, size=(sims, n), replace=True)
    if config.method == "path_permutation":
        return np.stack([rng.permutation(source) for _ in range(sims)])
    block = config.block_length
    starts = np.arange(0, n - block + 1)
    paths = []
    for _ in range(sims):
        pieces = []
        while sum(len(x) for x in pieces) < n:
            start = int(rng.choice(starts))
            pieces.append(source[start:start + block])
        paths.append(np.concatenate(pieces)[:n])
    return np.stack(paths)


def _old_metrics(p, ann):
    eq = np.cumprod(1.0 + p)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], eq)))[1:]
    std = p.std(ddof=1)
    sh = float("nan") if std == 0 else float(p.mean() / std * (np.sqrt(ann) if ann else 1.0))
    return float(eq[-1] - 1.0), float(np.min(eq / peaks - 1.0)), sh


SRC = np.random.default_rng(3).normal(0.001, 0.01, 253)


@pytest.mark.parametrize("method,block", [("iid_bootstrap", None), ("path_permutation", None), ("moving_block_bootstrap", 1), ("moving_block_bootstrap", 7), ("moving_block_bootstrap", 253)])
@pytest.mark.parametrize("sims", [1, 50, 400])
def test_resample_identical(method, block, sims):
    cfg = MonteCarloConfig(seed=11, simulation_count=sims, method=method, block_length=block)
    assert np.array_equal(resample_paths(SRC, cfg), _old_resample(SRC, cfg))


@pytest.mark.parametrize("ann", [None, 252])
@pytest.mark.licensed_vectorbt
def test_metrics_identical(ann):
    paths = np.vstack([np.random.default_rng(9).choice(SRC, (60, 253)), np.zeros((1, 253))])
    t, d, s = path_metrics(paths, ann)
    old = np.array([_old_metrics(p, ann) for p in paths])
    assert np.array_equal(t, old[:, 0]) and np.array_equal(d, old[:, 1])
    # Library Sharpe differs from the loop formula only by float rounding order (<1e-14).
    assert np.allclose(s, old[:, 2], rtol=1e-12, atol=1e-12, equal_nan=True)
