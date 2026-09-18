"""Neighborhood summaries and deterministic combined-status policy."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from backtesting.robustness.models import (
    DimensionStability,
    EvaluatedParameterPoint,
    NeighborhoodConstructionResult,
    NeighborhoodSummary,
    RegimeEvaluationResult,
    RegimeLabelMetadata,
    RobustnessConfig,
    RobustnessResult,
    Status,
    ThresholdResult,
)
from backtesting.robustness.evaluation import evaluate_neighborhood
from backtesting.robustness.regimes import evaluate_regimes, label_regimes


def combine_statuses(statuses: Iterable[Status]) -> Status:
    """Apply invalid > failed > insufficient > passed precedence."""
    values = tuple(statuses)
    if any(value == "invalid_input" for value in values):
        return "invalid_input"
    if any(value == "failed" for value in values):
        return "failed"
    if any(value == "insufficient_evidence" for value in values):
        return "insufficient_evidence"
    return "passed"


def _dimension_stability(
    config: RobustnessConfig,
    points: tuple[EvaluatedParameterPoint, ...],
) -> tuple[DimensionStability, ...]:
    locked = dict(config.locked_parameters)
    summaries: list[DimensionStability] = []
    for definition in config.neighborhood.definitions:
        name = definition.parameter_name
        relevant = [
            point
            for point in points
            if all(
                point.normalized_parameters[other] == locked[other]
                for other in locked
                if other != name
            )
        ]
        relevant.sort(key=lambda point: point.normalized_parameters[name])
        returns = [point.total_return for point in relevant]
        drawdowns = [point.maximum_drawdown for point in relevant]
        if len(relevant) < 2:
            behavior = "insufficient"
        else:
            increasing = all(left <= right for left, right in zip(returns, returns[1:]))
            decreasing = all(left >= right for left, right in zip(returns, returns[1:]))
            behavior = "monotonic" if increasing or decreasing else "unstable"
        summaries.append(
            DimensionStability(
                parameter_name=name,
                tested_values=tuple(point.normalized_parameters[name] for point in relevant),
                locked_value=locked[name],
                pass_count=sum(point.status == "passed" for point in relevant),
                return_range=(max(returns) - min(returns) if returns else None),
                drawdown_range=(max(drawdowns) - min(drawdowns) if drawdowns else None),
                behavior=behavior,
            )
        )
    return tuple(summaries)


def summarize_neighborhood(
    config: RobustnessConfig,
    construction: NeighborhoodConstructionResult,
    points: tuple[EvaluatedParameterPoint, ...],
) -> NeighborhoodSummary:
    """Summarize a fixed neighborhood without selecting a replacement."""
    evaluated_count = len(points)
    passing_count = sum(point.status == "passed" for point in points)
    passing_proportion = passing_count / evaluated_count if evaluated_count else 0.0
    def point_within_limit(point: EvaluatedParameterPoint) -> bool:
        absolute_ok = (
            point.absolute_degradation
            <= config.neighborhood.maximum_absolute_degradation
        )
        relative_ok = (
            point.relative_degradation is not None
            and point.relative_degradation
            <= config.neighborhood.maximum_relative_degradation
        )
        if config.neighborhood.degradation_mode == "absolute":
            return absolute_ok
        if config.neighborhood.degradation_mode == "relative":
            return relative_ok
        return absolute_ok and relative_ok

    within_limit = sum(point_within_limit(point) for point in points)
    within_proportion = within_limit / evaluated_count if evaluated_count else 0.0
    locked_points = [point for point in points if point.is_locked_point]
    locked_status: Status = locked_points[0].status if len(locked_points) == 1 else "invalid_input"
    ranked = sorted(points, key=lambda point: (-point.total_return, tuple(sorted(point.normalized_parameters.items()))))
    locked_rank = (
        next((index + 1 for index, point in enumerate(ranked) if point.is_locked_point), None)
        if len(locked_points) == 1
        else None
    )

    finite_sharpes = [point.sharpe_ratio for point in points if point.sharpe_ratio is not None]
    returns = [point.total_return for point in points]
    drawdowns = [point.maximum_drawdown for point in points]
    minimum_ok = construction.accepted_count >= config.neighborhood.minimum_valid_neighbors
    pass_ok = passing_proportion >= config.neighborhood.required_pass_proportion
    degradation_ok = within_proportion >= config.neighborhood.required_pass_proportion
    drawdown_ok = bool(drawdowns) and max(abs(value) for value in drawdowns) <= config.maximum_drawdown
    def evidence_dependent_status(passed: bool) -> Status:
        if not minimum_ok:
            return "insufficient_evidence"
        return "passed" if passed else "failed"
    threshold_results = (
        ThresholdResult("minimum_valid_neighbors", "passed" if minimum_ok else "insufficient_evidence", construction.accepted_count, config.neighborhood.minimum_valid_neighbors, "minimum valid-neighbor evidence"),
        ThresholdResult("required_pass_proportion", evidence_dependent_status(pass_ok), passing_proportion, config.neighborhood.required_pass_proportion, "neighborhood passing proportion"),
        ThresholdResult("degradation_proportion", evidence_dependent_status(degradation_ok), within_proportion, config.neighborhood.required_pass_proportion, "proportion within configured degradation limit"),
        ThresholdResult("worst_drawdown", evidence_dependent_status(drawdown_ok), max((abs(value) for value in drawdowns), default=None), config.maximum_drawdown, "worst neighbor drawdown magnitude"),
        ThresholdResult("locked_point", locked_status, None, 1, "locked point must pass and cannot be replaced"),
    )
    component_status = combine_statuses(result.status for result in threshold_results)
    reasons = tuple(result.message for result in threshold_results if result.status != "passed")
    return NeighborhoodSummary(
        requested_candidate_count=construction.requested_candidate_count,
        raw_derived_count=construction.raw_derived_count,
        unique_normalized_count=construction.unique_normalized_count,
        rejected_count=construction.rejected_count,
        duplicate_count=construction.duplicate_count,
        valid_count=construction.accepted_count,
        evaluated_count=evaluated_count,
        passing_count=passing_count,
        passing_proportion=passing_proportion,
        proportion_within_degradation_limit=within_proportion,
        median_total_return=float(np.median(returns)) if returns else None,
        worst_total_return=min(returns) if returns else None,
        median_maximum_drawdown=float(np.median(drawdowns)) if drawdowns else None,
        worst_maximum_drawdown=min(drawdowns) if drawdowns else None,
        median_sharpe=float(np.median(finite_sharpes)) if finite_sharpes else None,
        locked_point_rank=locked_rank,
        locked_point_status=locked_status,
        dimension_stability=_dimension_stability(config, points),
        threshold_results=threshold_results,
        status=component_status,
        reasons=reasons,
    )


def build_robustness_result(
    config: RobustnessConfig,
    construction: NeighborhoodConstructionResult,
    points: tuple[EvaluatedParameterPoint, ...],
    neighborhood_summary: NeighborhoodSummary,
    regime_metadata: RegimeLabelMetadata,
    regime_results: tuple[RegimeEvaluationResult, ...],
) -> RobustnessResult:
    """Create the combined result using explicit component precedence."""
    regime_status = (
        combine_statuses(result.status for result in regime_results)
        if regime_results
        else "insufficient_evidence"
    )
    component_statuses: dict[str, Status] = {
        "parameter_neighborhood": neighborhood_summary.status,
        "regimes": regime_status,
    }
    status = combine_statuses(component_statuses.values())
    reasons = list(neighborhood_summary.reasons)
    for result in regime_results:
        if result.status != "passed":
            reasons.extend(f"{result.regime_id}: {reason}" for reason in result.reasons)
    if not regime_results:
        reasons.append("no usable regimes were available")
    return RobustnessResult(
        schema_version=1,
        status=status,
        strategy_id=config.strategy_id,
        strategy_version=config.strategy_version,
        experiment_id=config.experiment_id,
        source_artifact_id=config.source_artifact_id,
        locked_parameters=dict(config.locked_parameters),
        data_provenance=dict(config.data_provenance),
        execution_assumptions=dict(config.execution_assumptions),
        neighborhood_construction=construction,
        parameter_points=points,
        neighborhood_summary=neighborhood_summary,
        regime_metadata=regime_metadata,
        regime_results=regime_results,
        component_statuses=component_statuses,
        reasons=tuple(reasons),
        warnings=(
            "locked-point rank is informational and cannot select a replacement",
            "passing robustness is not promotion or production approval",
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def insufficient_result(
    *,
    strategy_id: str,
    strategy_version: str,
    experiment_id: str,
    artifact_id: str,
    reasons: tuple[str, ...],
    invalid: bool = False,
) -> RobustnessResult:
    """Return a strict result when no valid prior lock can be evaluated."""
    return RobustnessResult(
        schema_version=1,
        status="invalid_input" if invalid else "insufficient_evidence",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        experiment_id=experiment_id,
        source_artifact_id=artifact_id,
        locked_parameters={},
        data_provenance={},
        execution_assumptions={},
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=None,
        regime_results=(),
        component_statuses={
            "source_lock": "invalid_input" if invalid else "insufficient_evidence"
        },
        reasons=reasons,
        warnings=(),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def run_robustness_pipeline(
    config: RobustnessConfig,
    construction: NeighborhoodConstructionResult,
    experiment_config: Any,
    data: Any,
    audit: Any,
) -> RobustnessResult:
    """Evaluate the fixed neighborhood and locked returns through real infrastructure."""
    evaluation = evaluate_neighborhood(
        config,
        construction,
        experiment_config,
        data,
        audit,
    )
    neighborhood_summary = summarize_neighborhood(
        config,
        construction,
        evaluation.points,
    )
    labels = label_regimes(data["Close"], config.regimes)
    regime_results = evaluate_regimes(
        evaluation.locked_returns,
        labels,
        config.regimes,
        minimum_return=config.minimum_return,
        maximum_drawdown_limit=config.maximum_drawdown,
        minimum_sharpe=config.minimum_sharpe,
        trade_entries=evaluation.locked_entries,
    )
    return build_robustness_result(
        config,
        construction,
        evaluation.points,
        neighborhood_summary,
        labels.metadata,
        regime_results,
    )
