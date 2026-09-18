"""Repeated past-only selection and unseen walk-forward test evaluation."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

import pandas as pd

from backtesting.experiments import execute_experiment
from backtesting.out_of_sample.runner import (
    ExperimentEvaluator,
    OutOfSampleProgressionError,
    _passing_parameters,
    _run_partition,
    evaluate_locked_test,
    lock_selected_parameters,
)
from backtesting.walk_forward.models import (
    ParameterFrequency,
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardResult,
)
from backtesting.walk_forward.splitter import build_walk_forward_windows
from market_data import DataAudit

METRIC_NAMES = (
    "total_return",
    "annualized_return",
    "sharpe_ratio",
    "max_drawdown",
    "number_of_trades",
    "win_rate",
)


def _fold_result(
    config: WalkForwardConfig,
    window,
    audit: DataAudit,
    evaluator: ExperimentEvaluator,
) -> WalkForwardFoldResult:
    base = config.experiment
    candidates = tuple(dict(item) for item in base.parameter_combinations)
    training = _run_partition(base, window.train, audit, candidates, evaluator)
    try:
        shortlist = tuple(
            parameters
            for parameters, _ in _passing_parameters(training, stage="training")[
                : config.shortlist_size
            ]
        )
    except OutOfSampleProgressionError as exc:
        return WalkForwardFoldResult(
            fold_id=window.fold_id,
            status="failed",
            window=window,
            training_result=training,
            selection_result=None,
            test_result=None,
            shortlist_parameters=(),
            parameter_lock=None,
            selected_parameters=None,
            test_metrics={},
            failure_reason=str(exc),
        )

    if window.selection is not None:
        selection = _run_partition(
            base, window.selection, audit, shortlist, evaluator
        )
        lock_source = selection
        lock_partition = window.selection
    else:
        selection = None
        lock_source = training
        lock_partition = window.train
    try:
        parameter_lock = lock_selected_parameters(
            base, lock_source, lock_partition
        )
    except OutOfSampleProgressionError as exc:
        return WalkForwardFoldResult(
            fold_id=window.fold_id,
            status="failed",
            window=window,
            training_result=training,
            selection_result=selection,
            test_result=None,
            shortlist_parameters=shortlist,
            parameter_lock=None,
            selected_parameters=None,
            test_metrics={},
            failure_reason=str(exc),
        )
    test = evaluate_locked_test(
        base, window.test, audit, parameter_lock, evaluator
    )
    metrics = {
        name: test.ranked_results.iloc[0][name]
        for name in METRIC_NAMES
        if name in test.ranked_results.columns
    }
    return WalkForwardFoldResult(
        fold_id=window.fold_id,
        status="successful",
        window=window,
        training_result=training,
        selection_result=selection,
        test_result=test,
        shortlist_parameters=shortlist,
        parameter_lock=parameter_lock,
        selected_parameters=dict(parameter_lock.normalized_parameters),
        test_metrics=metrics,
        failure_reason=None,
    )


def _parameter_stability(successful):
    keys = [
        tuple(sorted(fold.selected_parameters.items()))
        for fold in successful
        if fold.selected_parameters is not None
    ]
    counts: dict[tuple[tuple[str, Any], ...], int] = {}
    for key in keys:
        counts[key] = counts.get(key, 0) + 1
    frequencies = tuple(
        ParameterFrequency(
            normalized_parameters=key,
            fold_count=count,
            fold_percentage=count / len(keys) if keys else 0.0,
        )
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    )
    changes = sum(left != right for left, right in zip(keys, keys[1:]))
    change_percentage = changes / (len(keys) - 1) if len(keys) > 1 else 0.0
    maximum_persistence = 0
    current = 0
    previous = None
    for key in keys:
        current = current + 1 if key == previous else 1
        maximum_persistence = max(maximum_persistence, current)
        previous = key
    return frequencies, change_percentage, maximum_persistence


def _aggregate(folds: tuple[WalkForwardFoldResult, ...]) -> WalkForwardResult:
    successful = tuple(fold for fold in folds if fold.status == "successful")
    rows = [
        {"fold_id": fold.fold_id, "test_end": fold.window.test.end} | fold.test_metrics
        for fold in successful
    ]
    metrics = pd.DataFrame(rows)
    numeric_names = [name for name in METRIC_NAMES if name in metrics.columns]
    average = {
        name: float(metrics[name].mean()) for name in numeric_names
    }
    median = {
        name: float(metrics[name].median()) for name in numeric_names
    }
    returns = pd.Series(
        [float(fold.test_metrics["total_return"]) for fold in successful],
        index=[fold.window.test.end for fold in successful],
        dtype=float,
        name="fold_total_return",
    )
    equity = (1.0 + returns).cumprod().rename("endpoint_equity")
    compounded = float(equity.iloc[-1] - 1.0) if not equity.empty else None
    if equity.empty:
        max_drawdown = None
    else:
        drawdown = equity / equity.cummax().clip(lower=1.0) - 1.0
        max_drawdown = float(drawdown.min())
    if len(returns) > 1 and returns.std(ddof=1) > 0:
        fold_sharpe = float(returns.mean() / returns.std(ddof=1))
    else:
        fold_sharpe = None
    frequencies, change_percentage, persistence = _parameter_stability(successful)
    failed = tuple(fold for fold in folds if fold.status == "failed")
    return WalkForwardResult(
        folds=folds,
        total_fold_count=len(folds),
        successful_fold_count=len(successful),
        failed_fold_count=len(failed),
        selected_parameters_by_fold=tuple(
            (fold.fold_id, dict(fold.selected_parameters))
            for fold in successful
            if fold.selected_parameters is not None
        ),
        unique_parameter_set_count=len(frequencies),
        parameter_frequencies=frequencies,
        parameter_change_percentage=change_percentage,
        maximum_consecutive_persistence=persistence,
        failed_fold_ids=tuple(fold.fold_id for fold in failed),
        failure_reasons=tuple(
            (fold.fold_id, fold.failure_reason or "unknown") for fold in failed
        ),
        fold_test_metrics=metrics,
        average_fold_metrics=average,
        median_fold_metrics=median,
        out_of_sample_returns=returns,
        out_of_sample_equity=equity,
        compounded_return=compounded,
        endpoint_max_drawdown=max_drawdown,
        fold_return_sharpe=fold_sharpe,
        total_trades=sum(
            int(fold.test_metrics.get("number_of_trades", 0)) for fold in successful
        ),
    )


def execute_walk_forward(
    config: WalkForwardConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    evaluator: ExperimentEvaluator = execute_experiment,
    write_output: bool = True,
) -> WalkForwardResult:
    """Run every chronological fold; record screening failures and continue."""
    windows = build_walk_forward_windows(data, config)
    if not windows:
        raise ValueError("walk-forward configuration produced no complete folds")
    folds: list[WalkForwardFoldResult] = []
    for window in windows:
        folds.append(_fold_result(config, window, audit, evaluator))
    result = _aggregate(tuple(folds))
    if write_output:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        def partition_record(partition):
            return {
                "name": partition.name,
                "start": partition.start,
                "end": partition.end,
                "row_count": partition.row_count,
            }

        report = {
            "configuration": {
                key: value
                for key, value in asdict(config).items()
                if key != "experiment"
            },
            "summary": {
                "total_folds": result.total_fold_count,
                "successful_folds": result.successful_fold_count,
                "failed_folds": result.failed_fold_count,
                "compounded_return": result.compounded_return,
                "endpoint_max_drawdown": result.endpoint_max_drawdown,
                "fold_return_sharpe": result.fold_return_sharpe,
                "total_trades": result.total_trades,
                "parameter_change_percentage": result.parameter_change_percentage,
                "maximum_consecutive_persistence": result.maximum_consecutive_persistence,
            },
            "folds": [
                {
                    "fold_id": fold.fold_id,
                    "status": fold.status,
                    "train": partition_record(fold.window.train),
                    "selection": (
                        partition_record(fold.window.selection)
                        if fold.window.selection is not None
                        else None
                    ),
                    "test": partition_record(fold.window.test),
                    "shortlist": fold.shortlist_parameters,
                    "selected_parameters": fold.selected_parameters,
                    "parameter_lock_id": (
                        fold.parameter_lock.lock_id if fold.parameter_lock else None
                    ),
                    "test_metrics": fold.test_metrics,
                    "failure_reason": fold.failure_reason,
                }
                for fold in result.folds
            ],
        }
        config.output_path.write_text(
            json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8"
        )
    return result
