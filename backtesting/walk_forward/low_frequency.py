"""Low-frequency fixed-parameter walk-forward evidence accumulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from backtesting.experiments import execute_experiment
from backtesting.experiments.models import ExperimentResult
from backtesting.out_of_sample.runner import ExperimentEvaluator, _run_partition
from backtesting.walk_forward.models import WalkForwardConfig
from backtesting.walk_forward.splitter import build_walk_forward_windows
from market_data import DataAudit
from strategies import get_strategy

EvidenceStatus = Literal["passed", "insufficient_evidence"]
PerformanceStatus = Literal["passed", "failed", "insufficient_evidence"]
CombinedStatus = Literal["passed", "failed", "insufficient_evidence"]
AggregateStatus = Literal["passed", "failed", "insufficient_evidence"]


@dataclass(frozen=True)
class LowFrequencyEvidenceConfig:
    """Policy configuration for one fixed low-frequency candidate."""

    walk_forward: WalkForwardConfig
    fixed_parameters: dict[str, Any]
    output_path: Path
    strategy_frequency: Literal["low_frequency"] = "low_frequency"
    minimum_validation_trades: int = 8
    minimum_sufficient_folds: int = 3
    minimum_pass_rate: float = 0.60
    maximum_drawdown: float = 0.35
    minimum_total_return: float = 0.0
    minimum_annualized_return: float = 0.0
    minimum_sharpe_ratio: float = 0.5
    forbidden_start_date: str = "2024-05-28"

    def __post_init__(self) -> None:
        if self.strategy_frequency != "low_frequency":
            raise ValueError("strategy_frequency must be declared as low_frequency")
        if tuple(self.walk_forward.experiment.parameter_combinations) != (
            dict(self.fixed_parameters),
        ):
            raise ValueError("walk-forward experiment must contain only fixed_parameters")
        if self.minimum_validation_trades < 1:
            raise ValueError("minimum_validation_trades must be positive")
        if self.minimum_sufficient_folds < 1:
            raise ValueError("minimum_sufficient_folds must be positive")
        if not 0 < self.minimum_pass_rate <= 1:
            raise ValueError("minimum_pass_rate must be in (0, 1]")
        if self.maximum_drawdown < 0:
            raise ValueError("maximum_drawdown must be non-negative")


@dataclass(frozen=True)
class LowFrequencyFoldEvidence:
    fold_id: str
    train_start: str
    train_end: str
    train_row_count: int
    validation_start: str
    validation_end: str
    validation_row_count: int
    parameters: dict[str, Any]
    trade_count: int
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    evidence_status: EvidenceStatus
    performance_status: PerformanceStatus
    combined_status: CombinedStatus


@dataclass(frozen=True)
class LowFrequencyAggregateEvidence:
    status: AggregateStatus
    sufficient_evidence_fold_count: int
    passing_fold_count: int
    passing_percentage: float
    required_sufficient_folds: int
    required_passing_percentage: float
    maximum_allowed_drawdown: float
    worst_drawdown: float | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class LowFrequencyEvidenceResult:
    strategy_id: str
    strategy_version: str
    experiment_id: str
    strategy_frequency: str
    fixed_parameters: dict[str, Any]
    forbidden_start_date: str
    evaluated_start: str
    evaluated_end: str
    folds: tuple[LowFrequencyFoldEvidence, ...]
    aggregate: LowFrequencyAggregateEvidence


def _assert_forbidden_dates_excluded(
    data: pd.DataFrame, forbidden_start_date: str
) -> None:
    cutoff = pd.Timestamp(forbidden_start_date)
    dates = pd.DatetimeIndex(data.index).tz_localize(None).normalize()
    if bool((dates >= cutoff).any()):
        raise ValueError(
            f"walk-forward input contains rows on or after {forbidden_start_date}"
        )


def _status_from_metrics(
    row: pd.Series,
    config: LowFrequencyEvidenceConfig,
) -> tuple[EvidenceStatus, PerformanceStatus, CombinedStatus]:
    trades = int(row["number_of_trades"])
    evidence_status: EvidenceStatus = (
        "passed"
        if trades >= config.minimum_validation_trades
        else "insufficient_evidence"
    )
    if evidence_status == "insufficient_evidence":
        return evidence_status, "insufficient_evidence", "insufficient_evidence"
    performance_passed = (
        float(row["total_return"]) > config.minimum_total_return
        and float(row["annualized_return"]) > config.minimum_annualized_return
        and float(row["sharpe_ratio"]) >= config.minimum_sharpe_ratio
        and abs(float(row["max_drawdown"])) <= config.maximum_drawdown
    )
    performance_status: PerformanceStatus = (
        "passed" if performance_passed else "failed"
    )
    combined_status: CombinedStatus = "passed" if performance_passed else "failed"
    return evidence_status, performance_status, combined_status


def _fold_evidence(
    config: LowFrequencyEvidenceConfig,
    window,
    audit: DataAudit,
    evaluator: ExperimentEvaluator,
) -> LowFrequencyFoldEvidence:
    if window.selection is not None:
        raise ValueError("low-frequency evidence uses validation windows, not selection")
    result: ExperimentResult = _run_partition(
        config.walk_forward.experiment,
        window.test,
        audit,
        (dict(config.fixed_parameters),),
        evaluator,
    )
    if len(result.ranked_results) != 1:
        raise ValueError("fixed-parameter validation must produce exactly one row")
    row = result.ranked_results.iloc[0]
    evidence_status, performance_status, combined_status = _status_from_metrics(
        row, config
    )
    return LowFrequencyFoldEvidence(
        fold_id=window.fold_id,
        train_start=window.train.start,
        train_end=window.train.end,
        train_row_count=window.train.row_count,
        validation_start=window.test.start,
        validation_end=window.test.end,
        validation_row_count=window.test.row_count,
        parameters=dict(config.fixed_parameters),
        trade_count=int(row["number_of_trades"]),
        total_return=float(row["total_return"]),
        annualized_return=float(row["annualized_return"]),
        sharpe_ratio=float(row["sharpe_ratio"]),
        max_drawdown=float(row["max_drawdown"]),
        evidence_status=evidence_status,
        performance_status=performance_status,
        combined_status=combined_status,
    )


def aggregate_low_frequency_evidence(
    folds: tuple[LowFrequencyFoldEvidence, ...],
    config: LowFrequencyEvidenceConfig,
) -> LowFrequencyAggregateEvidence:
    sufficient = tuple(fold for fold in folds if fold.evidence_status == "passed")
    passing = tuple(fold for fold in sufficient if fold.combined_status == "passed")
    pass_rate = len(passing) / len(sufficient) if sufficient else 0.0
    worst_drawdown = min((fold.max_drawdown for fold in folds), default=None)
    reasons: list[str] = []
    if len(sufficient) < config.minimum_sufficient_folds:
        reasons.append(
            f"requires at least {config.minimum_sufficient_folds} sufficient-evidence folds; "
            f"observed {len(sufficient)}"
        )
    if sufficient and pass_rate < config.minimum_pass_rate:
        reasons.append(
            f"requires at least {config.minimum_pass_rate:.0%} passing sufficient-evidence folds; "
            f"observed {pass_rate:.1%}"
        )
    if worst_drawdown is not None and abs(worst_drawdown) > config.maximum_drawdown:
        reasons.append(
            f"worst fold drawdown {worst_drawdown:.6f} exceeds "
            f"{config.maximum_drawdown:.0%}"
        )
    if len(sufficient) < config.minimum_sufficient_folds:
        status: AggregateStatus = "insufficient_evidence"
    elif reasons:
        status = "failed"
    else:
        status = "passed"
    return LowFrequencyAggregateEvidence(
        status=status,
        sufficient_evidence_fold_count=len(sufficient),
        passing_fold_count=len(passing),
        passing_percentage=pass_rate,
        required_sufficient_folds=config.minimum_sufficient_folds,
        required_passing_percentage=config.minimum_pass_rate,
        maximum_allowed_drawdown=config.maximum_drawdown,
        worst_drawdown=worst_drawdown,
        reasons=tuple(reasons),
    )


def execute_low_frequency_evidence(
    config: LowFrequencyEvidenceConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    evaluator: ExperimentEvaluator = execute_experiment,
    write_output: bool = True,
) -> LowFrequencyEvidenceResult:
    """Evaluate one fixed candidate over chronological validation folds."""
    _assert_forbidden_dates_excluded(data, config.forbidden_start_date)
    windows = build_walk_forward_windows(data, config.walk_forward)
    if not windows:
        raise ValueError("low-frequency configuration produced no validation folds")
    strategy = get_strategy(config.walk_forward.experiment.strategy_id)
    folds = tuple(
        _fold_evidence(config, window, audit, evaluator) for window in windows
    )
    aggregate = aggregate_low_frequency_evidence(folds, config)
    result = LowFrequencyEvidenceResult(
        strategy_id=config.walk_forward.experiment.strategy_id,
        strategy_version=strategy.spec.identity.version,
        experiment_id=config.walk_forward.experiment.experiment_id,
        strategy_frequency=config.strategy_frequency,
        fixed_parameters=dict(config.fixed_parameters),
        forbidden_start_date=config.forbidden_start_date,
        evaluated_start=str(data.index[0].date()),
        evaluated_end=str(data.index[-1].date()),
        folds=folds,
        aggregate=aggregate,
    )
    if write_output:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(result)
        payload["schema_version"] = 1
        payload["artifact_kind"] = "low_frequency_walk_forward_evidence"
        config.output_path.write_text(
            json.dumps(payload, indent=2, default=str, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return result
