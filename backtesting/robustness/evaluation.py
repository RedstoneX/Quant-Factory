"""Pipeline-backed evaluation of a predeclared parameter neighborhood."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any

import pandas as pd

from backtesting.experiments import (
    align_signals_for_execution,
    build_portfolio,
    execute_experiment,
)
from backtesting.experiments.models import ExperimentConfig
from backtesting.robustness.models import (
    EvaluatedParameterPoint,
    NeighborhoodConstructionResult,
    NeighborhoodEvaluation,
    RobustnessConfig,
    ThresholdResult,
)
from market_data import DataAudit
from strategies import get_strategy


def _series(value: Any, index: pd.Index, name: str) -> pd.Series:
    if isinstance(value, pd.Series):
        result = value.copy()
    else:
        result = pd.Series(value, index=index)
    result.name = name
    return result


def evaluate_neighborhood(
    config: RobustnessConfig,
    construction: NeighborhoodConstructionResult,
    experiment_config: ExperimentConfig,
    data: pd.DataFrame,
    audit: DataAudit,
) -> NeighborhoodEvaluation:
    """Evaluate all accepted candidates with one identical experiment config."""
    if experiment_config.strategy_id != config.strategy_id:
        raise ValueError("experiment strategy does not match robustness strategy")
    strategy = get_strategy(config.strategy_id)
    if strategy.spec.identity.version != config.strategy_version:
        raise ValueError("strategy version does not match robustness lock")
    actual_start = str(data.index[0].date())
    actual_end = str(data.index[-1].date())
    if actual_start != config.source_start or actual_end != config.source_end:
        raise ValueError("market data boundaries do not match locked source")

    expected_execution = {
        "execution_mode": experiment_config.execution.mode,
        "fees": experiment_config.execution.fees,
        "slippage": experiment_config.execution.slippage,
        "initial_cash": experiment_config.execution.initial_cash,
        "direction": experiment_config.execution.direction,
        "leverage": experiment_config.execution.leverage,
        "accumulate": experiment_config.execution.accumulate,
    }
    for key, expected in expected_execution.items():
        if config.execution_assumptions.get(key) != expected:
            raise ValueError(f"execution assumption mismatch: {key}")

    source_run_identity = f"{config.experiment_id}:robustness:{config.source_artifact_id}"
    candidate_parameters = tuple(
        dict(candidate.normalized_parameters) for candidate in construction.candidates
    )
    robustness_experiment = replace(
        experiment_config,
        experiment_id=source_run_identity,
        parameter_combinations=candidate_parameters,
    )
    experiment_result = execute_experiment(
        robustness_experiment,
        data,
        audit,
        write_output=False,
    )
    rows_by_id = {
        str(row["parameter_row_id"]): row
        for _, row in experiment_result.ranked_results.iterrows()
    }
    screen_by_parameters = {
        tuple(sorted(item.normalized_parameters.items())): item
        for item in experiment_result.screening_results
    }
    candidate_by_parameters = {
        tuple(sorted(item.normalized_parameters.items())): item
        for item in construction.candidates
    }

    locked_key = tuple(sorted(dict(config.locked_parameters).items()))
    locked_screen = screen_by_parameters.get(locked_key)
    if locked_screen is None:
        raise ValueError("locked point was not evaluated")
    locked_row = rows_by_id[locked_screen.parameter_row_id]
    locked_return = float(locked_row["total_return"])

    points: list[EvaluatedParameterPoint] = []
    epsilon = 1e-12
    for key in sorted(screen_by_parameters):
        screening = screen_by_parameters[key]
        candidate = candidate_by_parameters[key]
        row = rows_by_id[screening.parameter_row_id]
        total_return = float(row["total_return"])
        maximum_drawdown = float(row["max_drawdown"])
        raw_sharpe = float(row["sharpe_ratio"])
        sharpe = raw_sharpe if math.isfinite(raw_sharpe) else None
        trade_count = int(row["number_of_trades"])
        absolute_degradation = locked_return - total_return
        if abs(locked_return) <= epsilon:
            relative_degradation = None
            warnings = ("relative degradation unavailable because locked return is zero",)
        else:
            relative_degradation = absolute_degradation / abs(locked_return)
            warnings = ()

        absolute_ok = absolute_degradation <= config.neighborhood.maximum_absolute_degradation
        relative_ok = (
            relative_degradation is not None
            and relative_degradation <= config.neighborhood.maximum_relative_degradation
        )
        degradation_mode = config.neighborhood.degradation_mode
        degradation_ok = (
            absolute_ok
            if degradation_mode == "absolute"
            else relative_ok
            if degradation_mode == "relative"
            else absolute_ok and relative_ok
        )
        checks: list[tuple[str, bool, float | None, float]] = [
            ("minimum_return", total_return >= config.minimum_return, total_return, config.minimum_return),
            ("maximum_drawdown", abs(maximum_drawdown) <= config.maximum_drawdown, abs(maximum_drawdown), config.maximum_drawdown),
            ("absolute_degradation", absolute_ok, absolute_degradation, config.neighborhood.maximum_absolute_degradation),
        ]
        if degradation_mode in {"relative", "both"}:
            checks.append(
                ("relative_degradation", relative_ok, relative_degradation, config.neighborhood.maximum_relative_degradation)
            )
        if config.minimum_sharpe is not None:
            checks.append(
                ("minimum_sharpe", sharpe is not None and sharpe >= config.minimum_sharpe, sharpe, config.minimum_sharpe)
            )
        threshold_results = tuple(
            ThresholdResult(
                rule_id=rule_id,
                status="passed" if passed else "failed",
                observed=observed,
                threshold=threshold,
                message=f"{rule_id}: observed {observed!r}, threshold {threshold!r}",
            )
            for rule_id, passed, observed, threshold in checks
        )
        reasons = [item.message for item in threshold_results if item.status == "failed"]
        if not screening.passed:
            reasons.extend(screening.rejection_reasons)
        status = "passed" if not reasons and degradation_ok else "failed"
        points.append(
            EvaluatedParameterPoint(
                normalized_parameters=dict(screening.normalized_parameters),
                derivations=candidate.derivations,
                is_locked_point=candidate.is_locked_point,
                status=status,
                total_return=total_return,
                maximum_drawdown=maximum_drawdown,
                sharpe_ratio=sharpe,
                trade_count=trade_count,
                screening_status="passed" if screening.passed else "screened_out",
                hygiene_status="passed",
                absolute_degradation=absolute_degradation,
                relative_degradation=relative_degradation,
                degradation_unit=(
                    "decimal return difference; 0.25 equals 25 percentage points"
                ),
                degradation_interpretation=(
                    "positive means candidate underperformed the locked point; "
                    "negative means it outperformed but cannot replace the lock"
                ),
                threshold_results=threshold_results,
                reasons=tuple(reasons),
                warnings=warnings,
                source_run_identity=source_run_identity,
            )
        )

    locked_signals = strategy.generate_signals(data, dict(config.locked_parameters))
    locked_portfolio = build_portfolio(data, locked_signals, robustness_experiment)
    locked_returns = _series(locked_portfolio.returns, data.index, "strategy_return")
    aligned_signals = align_signals_for_execution(
        locked_signals,
        experiment_config.execution,
    )
    locked_entries = _series(aligned_signals.entries, data.index, "entry").astype(bool)
    return NeighborhoodEvaluation(
        points=tuple(points),
        locked_returns=locked_returns,
        locked_entries=locked_entries,
        source_run_identity=source_run_identity,
    )
