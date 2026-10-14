"""Deflated Sharpe Ratio: a multiple-testing ("luck") check on the best setting.

Computed by VectorBT PRO's ``ReturnsAccessor.deflated_sharpe_ratio`` (Bailey and
Lopez de Prado, 2014, https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
which treats every column as one trial.  The value is RECORD-ONLY and never
screens a setting out; 95% (DSR >= 0.95) is the paper's convention.

The library counts raw trials, so ``effective_trials`` records the trial count
(no correlation-based reduction is applied).
"""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

DSR_CONFIDENCE = 0.95


@dataclass(frozen=True)
class DeflatedSharpeResult:
    """Experiment-level luck check for the best (highest Sharpe) setting."""

    trials: int
    effective_trials: float
    best_trial_index: int
    best_sharpe: float
    observations: int
    probability: float
    trial_probabilities: tuple[float, ...]
    confidence: float = DSR_CONFIDENCE

    @property
    def meets_conventional_confidence(self) -> bool:
        """Record-only: the paper's 95% convention; never used to screen."""
        return math.isfinite(self.probability) and self.probability >= self.confidence


def deflated_sharpe(
    values: np.ndarray, initial_cash: float, confidence: float = DSR_CONFIDENCE
) -> DeflatedSharpeResult:
    """Deflate the best trial's Sharpe for N trials.

    ``values`` is a (bars x trials) portfolio-value matrix; per-bar simple
    returns use ``initial_cash`` as the value before the first bar.  Sharpe
    ratios are per bar (not annualized), as the paper requires; a trial with
    zero return variance has an undefined (failing) probability.
    """
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] < 1 or values.shape[0] < 2:
        raise ValueError("deflated Sharpe needs a (bars x trials) value matrix")
    import vectorbtpro  # noqa: F401  (registers the .vbt accessors)

    start = np.full((1, values.shape[1]), initial_cash)
    returns = pd.DataFrame(np.vstack([start, values])).vbt.to_returns().iloc[1:]
    accessor = returns.vbt.returns()
    sharpe = accessor.sharpe_ratio(annualized=False).to_numpy(dtype=float)
    probabilities = accessor.deflated_sharpe_ratio().to_numpy(dtype=float)
    finite = np.where(np.isfinite(sharpe), sharpe, -np.inf)
    best = int(np.argmax(finite))
    trials = values.shape[1]
    return DeflatedSharpeResult(
        trials=trials,
        effective_trials=float(trials),
        best_trial_index=best,
        best_sharpe=float(sharpe[best]) if np.isfinite(sharpe[best]) else float("nan"),
        observations=values.shape[0],
        probability=float(probabilities[best]),
        trial_probabilities=tuple(float(p) for p in probabilities),
        confidence=confidence,
    )
