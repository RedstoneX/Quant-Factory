"""Idea-level overfitting record for a walk-forward run (record-only, never screens).

Each fold's training, selection and test runs score a different number of
settings (whole grid, shortlist, one locked setting), so a Deflated Sharpe taken
from any one of them counts only that call's trials.  Per VectorBT PRO's
vbt-cross-validation guidance, the deflation must see the returns of EVERY
setting tried for the idea.  Every shortlist and lock is drawn from the base
grid, so the trials tried across all folds are exactly the base grid: it is
simulated once over the whole walk-forward span and both
``deflated_sharpe_ratio`` and the cookbook PBO are taken on those returns.
"""

from __future__ import annotations

from dataclasses import dataclass

from backtesting.out_of_sample.models import DataPartition
from backtesting.out_of_sample.runner import ExperimentEvaluator, _run_partition
from backtesting.screening.deflated_sharpe import DeflatedSharpeResult
from backtesting.screening.overfitting_pbo import OverfittingPBOResult
from backtesting.walk_forward.models import WalkForwardConfig
from market_data import DataAudit


@dataclass(frozen=True)
class IdeaOverfitting:
    """Whole-grid, whole-span luck checks; ``trials`` counts every setting tried."""

    trials: int
    deflated_sharpe: DeflatedSharpeResult | None
    overfitting_pbo: OverfittingPBOResult | None


def idea_overfitting(
    config: WalkForwardConfig,
    windows,
    data,
    audit: DataAudit,
    evaluator: ExperimentEvaluator,
    full_history: dict | None = None,
) -> IdeaOverfitting:
    """Score the full base grid over first-train to last-test bars, once."""
    span = data.loc[windows[0].train.data.index[0] : windows[-1].test.data.index[-1]]
    partition = DataPartition(
        name="idea_overfitting",
        data=span,
        start=str(span.index[0]),
        end=str(span.index[-1]),
        row_count=len(span),
    )
    candidates = tuple(dict(item) for item in config.experiment.parameter_combinations)
    grid = _run_partition(
        config.experiment, partition, audit, candidates, evaluator, **(full_history or {})
    )
    return IdeaOverfitting(
        trials=len(candidates),
        deflated_sharpe=getattr(grid, "deflated_sharpe", None),
        overfitting_pbo=getattr(grid, "overfitting_pbo", None),
    )
