"""Typed screening decision assembly and stable row identity."""

import hashlib
import json
from typing import Any, Mapping

from backtesting.screening.models import ScreeningConfig, ScreeningResult
from backtesting.screening.rules import evaluate_rules


def parameter_row_identity(
    experiment_id: str,
    strategy_id: str,
    parameters: Mapping[str, Any],
) -> str:
    payload = json.dumps(
        {
            "experiment_id": experiment_id,
            "strategy_id": strategy_id,
            "parameters": dict(sorted(parameters.items())),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def screen_metrics(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    parameters: Mapping[str, Any],
    execution_assumptions: Mapping[str, Any],
    metrics: Mapping[str, Any],
    config: ScreeningConfig,
) -> ScreeningResult:
    """Apply all rules without mutating metrics or parameter inputs."""
    rule_results = evaluate_rules(dict(metrics), config)
    failed = tuple(result for result in rule_results if not result.passed)
    return ScreeningResult(
        parameter_row_id=parameter_row_identity(
            experiment_id, strategy_id, parameters
        ),
        passed=not failed,
        rule_results=rule_results,
        passed_rule_count=len(rule_results) - len(failed),
        failed_rule_count=len(failed),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        normalized_parameters=dict(parameters),
        execution_assumptions=dict(execution_assumptions),
        rejection_reasons=tuple(result.message for result in failed),
    )
