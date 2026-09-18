"""Selection-only parameter choice followed by locked held-out evaluation."""

from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import math
from typing import Callable

import pandas as pd

from backtesting.experiments import execute_experiment
from backtesting.experiments.runner import METRIC_COLUMNS
from backtesting.experiments.models import ExperimentConfig, ExperimentResult
from backtesting.out_of_sample.models import (
    DataPartition,
    OutOfSampleConfig,
    OutOfSampleResult,
    ParameterLock,
)
from backtesting.out_of_sample.splitter import split_chronologically
from market_data import DataAudit

ExperimentEvaluator = Callable[..., ExperimentResult]


class OutOfSampleProgressionError(ValueError):
    """Raised when screening leaves no candidate for the next OOS stage."""


def _partition_audit(audit: DataAudit, partition: DataPartition) -> DataAudit:
    """Retain provider provenance while recording the exact evaluated slice."""
    return replace(
        audit,
        actual_first_row_date=partition.start,
        actual_last_row_date=partition.end,
        row_count=partition.row_count,
        cache_action=f"partition:{partition.name}",
        cache_decision_reason="chronological out-of-sample partition",
    )


def _run_partition(
    base: ExperimentConfig,
    partition: DataPartition,
    audit: DataAudit,
    parameters: tuple[dict[str, object], ...],
    evaluator: ExperimentEvaluator,
) -> ExperimentResult:
    config = replace(
        base,
        experiment_id=f"{base.experiment_id}:{partition.name}",
        parameter_combinations=parameters,
        output_path=base.output_path.with_name(
            f"{base.output_path.stem}_{partition.name}{base.output_path.suffix}"
        ),
    )
    return evaluator(
        config,
        partition.data.copy(),
        _partition_audit(audit, partition),
        write_output=False,
    )


def _passing_parameters(
    result: ExperimentResult,
    *,
    stage: str,
) -> tuple[tuple[dict[str, object], str], ...]:
    """Map passing rows, in deterministic rank order, to normalized parameters."""
    if result.passing_results.empty:
        suffix = (
            "selection was not evaluated"
            if stage == "training"
            else "parameters were not locked"
        )
        raise OutOfSampleProgressionError(
            f"{stage} screening produced no passing candidates; {suffix}"
        )
    screening_by_id = {
        item.parameter_row_id: item for item in result.screening_results
    }
    passing: list[tuple[dict[str, object], str]] = []
    for row_id in result.passing_results["parameter_row_id"]:
        match = screening_by_id.get(str(row_id))
        if match is None or not match.passed:
            raise ValueError(
                f"{stage} passing row does not map to one passing screening result"
            )
        passing.append((dict(match.normalized_parameters), str(row_id)))
    return tuple(passing)


def lock_selected_parameters(
    base: ExperimentConfig,
    selection_result: ExperimentResult,
    selection_partition: DataPartition,
) -> ParameterLock:
    """Create a stable immutable lock from selection evidence only."""
    parameters, row_id = _passing_parameters(
        selection_result, stage="selection"
    )[0]
    identity_payload = {
        "experiment_id": base.experiment_id,
        "strategy_id": selection_result.strategy_id,
        "strategy_version": selection_result.strategy_version,
        "normalized_parameters": parameters,
        "selection_parameter_row_id": row_id,
        "selection_start": selection_partition.start,
        "selection_end": selection_partition.end,
        "ranking_columns": base.ranking_columns,
        "ranking_ascending": base.ranking_ascending,
    }
    lock_id = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ParameterLock(
        lock_id=lock_id,
        experiment_id=base.experiment_id,
        strategy_id=selection_result.strategy_id,
        strategy_version=selection_result.strategy_version,
        normalized_parameters=tuple(sorted(parameters.items())),
        selection_parameter_row_id=row_id,
        selection_start=selection_partition.start,
        selection_end=selection_partition.end,
        ranking_columns=base.ranking_columns,
        ranking_ascending=base.ranking_ascending,
    )


def evaluate_locked_test(
    base: ExperimentConfig,
    partition: DataPartition,
    audit: DataAudit,
    parameter_lock: ParameterLock,
    evaluator: ExperimentEvaluator = execute_experiment,
) -> ExperimentResult:
    """Evaluate exactly the already-locked parameters on held-out data."""
    return _run_partition(
        base,
        partition,
        audit,
        (dict(parameter_lock.normalized_parameters),),
        evaluator,
    )


def _report_provenance(audit: DataAudit) -> dict[str, object]:
    return {
        "provider": audit.provider,
        "provider_implementation": audit.provider_implementation,
        "symbol": audit.symbol,
        "interval": audit.interval,
        "prices_adjusted": audit.prices_adjusted,
        "actual_first_row_date": audit.actual_first_row_date,
        "actual_last_row_date": audit.actual_last_row_date,
        "row_count": audit.row_count,
    }


def _json_scalar(value: object) -> object:
    if hasattr(value, "item"):
        try:
            value = value.item()
        except ValueError:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _report_execution(config: ExperimentConfig) -> dict[str, object]:
    execution = config.execution
    return {
        "execution_mode": execution.mode,
        "signal_timing": execution.signal_timing,
        "execution_price": execution.execution_price_field,
        "initial_cash": _json_scalar(execution.initial_cash),
        "fees": _json_scalar(execution.fees),
        "slippage": _json_scalar(execution.slippage),
        "position_sizing": execution.position_sizing,
        "direction": execution.direction,
        "leverage": _json_scalar(execution.leverage),
        "accumulate": execution.accumulate,
        "order_size": _json_scalar(execution.order_size),
        "price_multiplier": _json_scalar(execution.price_multiplier),
        "fixed_fee_per_contract_per_side": _json_scalar(
            execution.fixed_fee_per_contract_per_side
        ),
        "fixed_fee_per_order": _json_scalar(execution.fixed_fee_per_order),
        "slippage_points": _json_scalar(execution.absolute_slippage_points),
        "slippage_ticks": _json_scalar(execution.slippage_ticks),
        "tick_size": _json_scalar(execution.tick_size),
    }


def _row_metrics(row: pd.Series) -> dict[str, object]:
    return {name: _json_scalar(row[name]) for name in METRIC_COLUMNS if name in row}


def _row_dict(row: pd.Series) -> dict[str, object]:
    return {name: _json_scalar(value) for name, value in row.to_dict().items()}


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [_row_dict(row) for _, row in frame.iterrows()]


def _oos_report(
    *,
    config: OutOfSampleConfig,
    split,
    audit: DataAudit,
    training: ExperimentResult,
    selection: ExperimentResult,
    test: ExperimentResult,
    parameter_lock: ParameterLock,
    shortlist: tuple[dict[str, object], ...],
) -> dict[str, object]:
    test_row = test.ranked_results.iloc[0]
    selection_row = selection.passing_results.iloc[0]
    return {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": config.output_path.stem,
        "experiment_id": config.experiment.experiment_id,
        "strategy_id": test.strategy_id,
        "strategy_version": test.strategy_version,
        "source_start": split.test.start,
        "source_end": split.test.end,
        "data_provenance": _report_provenance(audit),
        "execution_assumptions": _report_execution(config.experiment),
        "split": {
            name: {
                "start": getattr(split, name).start,
                "end": getattr(split, name).end,
                "row_count": getattr(split, name).row_count,
            }
            for name in ("train", "selection", "test")
        },
        "training_status": (
            "passed" if not training.passing_results.empty else "screened_out"
        ),
        "training_candidate_count": len(training.ranked_results),
        "training_pass_count": len(training.passing_results),
        "shortlist_parameters": shortlist,
        "selection_status": str(selection_row["screening_status"]),
        "selection_metrics": _row_metrics(selection_row),
        "test_status": str(test_row["screening_status"]),
        "metrics": _row_metrics(test_row),
        "test_metrics": _row_dict(test_row),
        "parameter_lock": asdict(parameter_lock)
        | {"normalized_parameters": dict(parameter_lock.normalized_parameters)},
        "selected_parameters": dict(parameter_lock.normalized_parameters),
    }


def _write_report(path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, default=str, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _oos_failure_report(
    *,
    config: OutOfSampleConfig,
    split,
    audit: DataAudit,
    training: ExperimentResult,
    stage: str,
    reason: str,
    shortlist: tuple[dict[str, object], ...] = (),
    selection: ExperimentResult | None = None,
) -> dict[str, object]:
    strategy_version = training.strategy_version
    report = {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": config.output_path.stem,
        "experiment_id": config.experiment.experiment_id,
        "strategy_id": config.experiment.strategy_id,
        "strategy_version": strategy_version,
        "source_start": split.test.start,
        "source_end": split.test.end,
        "data_provenance": _report_provenance(audit),
        "execution_assumptions": _report_execution(config.experiment),
        "split": {
            name: {
                "start": getattr(split, name).start,
                "end": getattr(split, name).end,
                "row_count": getattr(split, name).row_count,
            }
            for name in ("train", "selection", "test")
        },
        "failure_stage": stage,
        "failure_reason": reason,
        "training_status": (
            "passed" if not training.passing_results.empty else "screened_out"
        ),
        "training_candidate_count": len(training.ranked_results),
        "training_pass_count": len(training.passing_results),
        "training_results": _records(training.ranked_results),
        "shortlist_parameters": shortlist,
        "selection_status": "not_run",
        "selection_results": [],
        "test_status": "not_run",
        "metrics": {},
        "test_metrics": {},
        "parameter_lock": None,
        "selected_parameters": None,
    }
    if selection is not None:
        report["selection_status"] = (
            "passed" if not selection.passing_results.empty else "screened_out"
        )
        report["selection_results"] = _records(selection.ranked_results)
    return report


def execute_out_of_sample(
    config: OutOfSampleConfig,
    data: pd.DataFrame,
    audit: DataAudit,
    *,
    evaluator: ExperimentEvaluator = execute_experiment,
    write_output: bool = True,
) -> OutOfSampleResult:
    """Select without test data, lock parameters, then evaluate held-out test."""
    split = split_chronologically(data, config.split)
    candidates = tuple(dict(item) for item in config.experiment.parameter_combinations)
    training = _run_partition(
        config.experiment, split.train, audit, candidates, evaluator
    )
    try:
        training_survivors = _passing_parameters(training, stage="training")
    except OutOfSampleProgressionError as exc:
        if write_output:
            _write_report(
                config.output_path,
                _oos_failure_report(
                    config=config,
                    split=split,
                    audit=audit,
                    training=training,
                    stage="training",
                    reason=str(exc),
                ),
            )
        raise
    shortlist = tuple(
        parameters
        for parameters, _ in training_survivors[: config.shortlist_size]
    )
    selection = _run_partition(
        config.experiment, split.selection, audit, shortlist, evaluator
    )
    try:
        parameter_lock = lock_selected_parameters(
            config.experiment, selection, split.selection
        )
    except OutOfSampleProgressionError as exc:
        if write_output:
            _write_report(
                config.output_path,
                _oos_failure_report(
                    config=config,
                    split=split,
                    audit=audit,
                    training=training,
                    stage="selection",
                    reason=str(exc),
                    shortlist=shortlist,
                    selection=selection,
                ),
            )
        raise
    test = evaluate_locked_test(
        config.experiment, split.test, audit, parameter_lock, evaluator
    )

    if write_output:
        report = _oos_report(
            config=config,
            split=split,
            audit=audit,
            training=training,
            selection=selection,
            test=test,
            parameter_lock=parameter_lock,
            shortlist=shortlist,
        )
        _write_report(config.output_path, report)

    return OutOfSampleResult(
        split=split,
        training_result=training,
        selection_result=selection,
        test_result=test,
        parameter_lock=parameter_lock,
        shortlist_parameters=shortlist,
        selected_parameters=dict(parameter_lock.normalized_parameters),
    )
