"""Deflated Sharpe Ratio and effective-trial count against published numbers."""

import math
from statistics import NormalDist

import numpy as np
import pytest

from backtesting.screening.deflated_sharpe import (
    deflated_sharpe,
    effective_trials,
    expected_maximum_sharpe,
    probabilistic_sharpe_ratio,
)


def test_paper_numerical_example() -> None:
    # Bailey & Lopez de Prado (2014), numerical example: N=100 trials,
    # annualized V[SR]=1/2, T=1250 daily returns, annualized SR*=2.5,
    # skewness -3, kurtosis 10 -> SR_0 = 0.1132 (daily), DSR = 0.9004.
    benchmark = expected_maximum_sharpe(0.5 / 250, 100)
    assert benchmark == pytest.approx(0.1132, abs=5e-5)
    dsr = probabilistic_sharpe_ratio(2.5 / math.sqrt(250), benchmark, 1250, -3, 10)
    assert dsr == pytest.approx(0.9004, abs=5e-5)


def test_benchmark_floors_at_zero_without_selection() -> None:
    assert expected_maximum_sharpe(0.01, 1) == 0.0
    assert expected_maximum_sharpe(float("nan"), 50) == 0.0


@pytest.mark.parametrize(
    ("matrix", "expected"),
    [
        (np.eye(4), 4.0),
        (np.ones((3, 3)), 1.0),
        # Li & Ji (2005): equicorrelated rho=0.5, eigenvalues 2, .5, .5 -> 2.
        (np.full((3, 3), 0.5) + np.eye(3) * 0.5, 2.0),
    ],
)
def test_li_ji_effective_trials(matrix: np.ndarray, expected: float) -> None:
    assert effective_trials(matrix) == pytest.approx(expected, abs=1e-9)


def _independent(values: np.ndarray, cash: float) -> tuple[float, float, float]:
    previous = np.vstack([np.full((1, values.shape[1]), cash), values[:-1]])
    returns = values / previous - 1
    sharpe = returns.mean(axis=0) / returns.std(axis=0, ddof=1)
    best = int(np.argmax(sharpe))
    centred = returns[:, best] - returns[:, best].mean()
    m2 = (centred**2).mean()
    skew = (centred**3).mean() / m2**1.5
    kurt = (centred**4).mean() / m2**2
    eig = np.round(np.abs(np.linalg.eigvalsh(np.corrcoef(returns, rowvar=False))), 10)
    n_eff = float(np.sum((eig >= 1) + (eig - np.floor(eig))))
    g = 0.5772156649015329
    z = NormalDist()
    sr0 = math.sqrt(np.var(sharpe, ddof=1)) * (
        (1 - g) * z.inv_cdf(1 - 1 / n_eff) + g * z.inv_cdf(1 - 1 / (n_eff * math.e))
    )
    t = values.shape[0]
    stat = (sharpe[best] - sr0) * math.sqrt(t - 1) / math.sqrt(
        1 - skew * sharpe[best] + (kurt - 1) / 4 * sharpe[best] ** 2
    )
    return n_eff, sr0, z.cdf(stat)


def test_matches_independent_closed_form_on_chunk_boundaries(monkeypatch) -> None:
    import backtesting.screening.deflated_sharpe as module

    monkeypatch.setattr(module, "_ROW_CHUNK", 37)
    monkeypatch.setattr(module, "_COLUMN_CHUNK", 3)
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0004, 0.01, size=(500, 8))
    returns[:, 1] = returns[:, 0] * 0.9 + rng.normal(0, 0.002, 500)
    values = 1_000 * np.cumprod(1 + returns, axis=0)
    result = deflated_sharpe(values, 1_000)
    n_eff, sr0, dsr = _independent(values, 1_000)
    assert result.trials == 8
    assert result.effective_trials == pytest.approx(n_eff, rel=1e-9)
    assert result.expected_maximum_sharpe == pytest.approx(sr0, rel=1e-9)
    assert result.probability == pytest.approx(dsr, rel=1e-9)
    assert result.observations == 500


def test_duplicate_settings_count_once_and_flat_settings_are_undefined() -> None:
    rng = np.random.default_rng(3)
    walk = 1_000 * np.cumprod(1 + rng.normal(0.001, 0.01, size=300))
    values = np.column_stack([walk, walk, np.full(300, 1_000.0)])
    result = deflated_sharpe(values, 1_000)
    assert result.trials == 3
    assert result.effective_trials == pytest.approx(2.0)
    assert math.isnan(result.trial_probabilities[2])
