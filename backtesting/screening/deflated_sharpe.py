"""Deflated Sharpe Ratio: a multiple-testing ("luck") check on the best setting.

Sources
-------
* Bailey, D. H. and López de Prado, M. (2014). "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality."
  Journal of Portfolio Management 40(5), 94-107.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
  - Expected maximum Sharpe ratio under the null (paper eq. for SR_0):
    SR_0 = sqrt(V[SR]) * ((1 - g) * Z^-1(1 - 1/N) + g * Z^-1(1 - 1/(N e)))
    with g the Euler-Mascheroni constant.
  - DSR = Z((SR* - SR_0) * sqrt(T - 1)
            / sqrt(1 - skew * SR* + (kurt - 1) / 4 * SR*^2))
    where SR* is the non-annualized Sharpe ratio of the selected trial, T its
    sample length, skew its return skewness and kurt its (non-excess)
    kurtosis.  95% confidence (DSR >= 0.95) is the paper's convention; here
    the value is RECORD-ONLY and never screens a setting out.
* Effective number of trials for correlated settings: Li, J. and Ji, L.
  (2005). "Adjusting multiple testing in multilocus analyses using the
  eigenvalues of a correlation matrix." Heredity 95, 221-227.
  https://doi.org/10.1038/sj.hdy.6800717
  M_eff = sum_i [ I(|l_i| >= 1) + (|l_i| - floor(|l_i|)) ] over eigenvalues
  l_i of the trials' return correlation matrix.

The asymptotic SR_0 formula is undefined for fewer than one effective trial
and negative for very small counts; SR_0 is floored at zero (a benchmark below
"no skill" would make the check weaker than an ordinary PSR test).
"""

from dataclasses import dataclass
import math
from statistics import NormalDist

import numpy as np

DSR_CONFIDENCE = 0.95
EULER_MASCHERONI = 0.5772156649015329
_NORMAL = NormalDist()
_ROW_CHUNK = 16_384
_COLUMN_CHUNK = 64


@dataclass(frozen=True)
class DeflatedSharpeResult:
    """Experiment-level luck check for the best (highest Sharpe) setting."""

    trials: int
    effective_trials: float
    sharpe_variance: float
    expected_maximum_sharpe: float
    best_trial_index: int
    best_sharpe: float
    best_skewness: float
    best_kurtosis: float
    observations: int
    probability: float
    trial_probabilities: tuple[float, ...]
    confidence: float = DSR_CONFIDENCE

    @property
    def meets_conventional_confidence(self) -> bool:
        """Record-only: the paper's 95% convention; never used to screen."""
        return math.isfinite(self.probability) and self.probability >= self.confidence


def expected_maximum_sharpe(sharpe_variance: float, trials: float) -> float:
    """Expected maximum Sharpe ratio of ``trials`` unskilled trials (SR_0)."""
    if trials <= 1 or not math.isfinite(sharpe_variance) or sharpe_variance <= 0:
        return 0.0
    gamma = EULER_MASCHERONI
    value = math.sqrt(sharpe_variance) * (
        (1 - gamma) * _NORMAL.inv_cdf(1 - 1 / trials)
        + gamma * _NORMAL.inv_cdf(1 - 1 / (trials * math.e))
    )
    return max(0.0, value)


def probabilistic_sharpe_ratio(
    sharpe: float,
    benchmark: float,
    observations: int,
    skewness: float,
    kurtosis: float,
) -> float:
    """Probability the true Sharpe exceeds ``benchmark`` (PSR; DSR when SR_0)."""
    if observations < 2 or not all(
        math.isfinite(v) for v in (sharpe, benchmark, skewness, kurtosis)
    ):
        return float("nan")
    denominator = 1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe**2
    if denominator <= 0:
        return float("nan")
    z = (sharpe - benchmark) * math.sqrt(observations - 1) / math.sqrt(denominator)
    return _NORMAL.cdf(z)


def effective_trials(correlation: np.ndarray) -> float:
    """Li and Ji (2005) effective number of independent trials."""
    # Rounded so exact integer eigenvalues are not split by float noise
    # (the Li-Ji count is discontinuous at integers).
    eigenvalues = np.round(
        np.abs(np.linalg.eigvalsh(np.asarray(correlation, dtype=float))), 10
    )
    return float(np.sum((eigenvalues >= 1) + (eigenvalues - np.floor(eigenvalues))))


def _returns(values: np.ndarray, initial_cash: float, start: int, stop: int) -> np.ndarray:
    block = values[start:stop].astype(float)
    if start == 0:
        previous = np.vstack([np.full((1, values.shape[1]), initial_cash), block[:-1]])
    else:
        previous = np.vstack([values[start - 1 : start].astype(float), block[:-1]])
    return block / previous - 1.0


def _moments(values: np.ndarray, initial_cash: float) -> tuple[np.ndarray, ...]:
    """Exact per-trial mean, std(ddof=1), skewness, kurtosis in column blocks."""
    trials = values.shape[1]
    mean, std, skew, kurt = (np.full(trials, np.nan) for _ in range(4))
    for first in range(0, trials, _COLUMN_CHUNK):
        cols = slice(first, min(trials, first + _COLUMN_CHUNK))
        sub = values[:, cols]
        returns = _returns(sub, initial_cash, 0, sub.shape[0])
        mu = returns.mean(axis=0)
        centred = returns - mu
        m2 = (centred**2).mean(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            skew[cols] = (centred**3).mean(axis=0) / m2**1.5
            kurt[cols] = (centred**4).mean(axis=0) / m2**2
        mean[cols] = mu
        std[cols] = returns.std(axis=0, ddof=1)
    return mean, std, skew, kurt


def _correlation(
    values: np.ndarray, initial_cash: float, mean: np.ndarray, std: np.ndarray
) -> np.ndarray:
    """Pearson correlation accumulated over row chunks; flat trials uncorrelated."""
    rows, trials = values.shape
    live = std > 0
    scale = np.where(live, std, 1.0)
    gram = np.zeros((trials, trials))
    for start in range(0, rows, _ROW_CHUNK):
        stop = min(rows, start + _ROW_CHUNK)
        z = (_returns(values, initial_cash, start, stop) - mean) / scale
        z[:, ~live] = 0.0
        gram += z.T @ z
    correlation = gram / (rows - 1)
    correlation[~live, :] = 0.0
    correlation[:, ~live] = 0.0
    np.fill_diagonal(correlation, 1.0)
    return correlation


def deflated_sharpe(
    values: np.ndarray, initial_cash: float, confidence: float = DSR_CONFIDENCE
) -> DeflatedSharpeResult:
    """Deflate the best trial's Sharpe for N correlated trials.

    ``values`` is a (bars x trials) portfolio-value matrix; per-bar simple
    returns use ``initial_cash`` as the value before the first bar.  Sharpe
    ratios are per bar (not annualized), as the paper requires; a trial with
    zero return variance has Sharpe 0 and an undefined (failing) probability.
    """
    values = np.asarray(values)
    if values.ndim != 2 or values.shape[1] < 1 or values.shape[0] < 2:
        raise ValueError("deflated Sharpe needs a (bars x trials) value matrix")
    mean, std, skew, kurt = _moments(values, initial_cash)
    with np.errstate(divide="ignore", invalid="ignore"):
        sharpe = np.where(std > 0, mean / std, 0.0)
    trials = values.shape[1]
    variance = float(np.var(sharpe, ddof=1)) if trials > 1 else float("nan")
    n_eff = (
        effective_trials(_correlation(values, initial_cash, mean, std))
        if trials > 1
        else 1.0
    )
    benchmark = expected_maximum_sharpe(variance, n_eff)
    observations = values.shape[0]
    probabilities = tuple(
        probabilistic_sharpe_ratio(
            float(sharpe[i]), benchmark, observations, float(skew[i]), float(kurt[i])
        )
        if std[i] > 0
        else float("nan")
        for i in range(trials)
    )
    best = int(np.argmax(sharpe))
    return DeflatedSharpeResult(
        trials=trials,
        effective_trials=n_eff,
        sharpe_variance=variance,
        expected_maximum_sharpe=benchmark,
        best_trial_index=best,
        best_sharpe=float(sharpe[best]),
        best_skewness=float(skew[best]),
        best_kurtosis=float(kurt[best]),
        observations=observations,
        probability=probabilities[best],
        trial_probabilities=probabilities,
        confidence=confidence,
    )
