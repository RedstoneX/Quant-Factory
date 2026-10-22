"""Canonical document construction for Monte Carlo evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backtesting.validation.evidence_adapters import normalize_monte_carlo_evidence
from backtesting.validation.monte_carlo_artifacts.models import (
    MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
    MONTE_CARLO_EVIDENCE_SCHEMA_VERSION,
)
from persistence.serialization import canonical_json


def _identity(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def _source_values_identity(values: tuple[float, ...]) -> str:
    return _identity({"values": values})


def _identity_payload(evidence_payload: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(canonical_json(evidence_payload))
    payload["monte_carlo"].pop("timestamp", None)
    return payload


def _cost_scenario_document(scenario: object) -> dict[str, Any]:
    return {
        "name": scenario.name,
        "fee_increase": scenario.fee_increase,
        "slippage_increase": scenario.slippage_increase,
        "execution_price_penalty": scenario.execution_price_penalty,
    }


def _config_document(config: object) -> dict[str, Any]:
    return {
        "method": config.method,
        "seed": config.seed,
        "simulation_count": config.simulation_count,
        "percentiles": config.percentiles,
        "minimum_observations": config.minimum_observations,
        "drawdown_threshold": config.drawdown_threshold,
        "maximum_loss_probability": config.maximum_loss_probability,
        "maximum_drawdown_breach_probability": (
            config.maximum_drawdown_breach_probability
        ),
        "lower_percentile": config.lower_percentile,
        "minimum_lower_percentile_return": config.minimum_lower_percentile_return,
        "block_length": config.block_length,
        "annualization_factor": config.annualization_factor,
        "execution_cost_scenarios": tuple(
            _cost_scenario_document(scenario)
            for scenario in config.execution_cost_scenarios
        ),
        "persist_paths": config.persist_paths,
    }


def _source_document(source: object, *, observation_count: int) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "source_kind": source.source_kind,
        "experiment_id": source.experiment_id,
        "strategy_id": source.strategy_id,
        "strategy_version": source.strategy_version,
        "observation_count": observation_count,
        "source_values_identity": _source_values_identity(source.values),
        "provenance": source.provenance,
        "execution_assumptions": source.execution_assumptions,
        "period_frequency": source.period_frequency,
        "input_status": source.input_status,
        "input_reasons": source.input_reasons,
    }


def _threshold_document(rule: object) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "passed": rule.passed,
        "observed": rule.observed,
        "threshold": rule.threshold,
        "message": rule.message,
    }


def _stress_document(result: object) -> dict[str, Any]:
    return {
        "scenario_name": result.scenario_name,
        "source_observation_type": result.source_observation_type,
        "cost_inputs": result.cost_inputs,
        "translation_method": result.translation_method,
        "original_cumulative_return": result.original_cumulative_return,
        "stressed_cumulative_return": result.stressed_cumulative_return,
        "difference": result.difference,
        "status": result.status,
        "reasons": result.reasons,
    }


def _normalized_threshold_document(rule: object) -> dict[str, Any]:
    return {
        "threshold_id": rule.threshold_id,
        "status": rule.status,
        "observed": rule.observed,
        "threshold": rule.threshold,
        "reason": rule.reason,
    }


def build_monte_carlo_evidence_document(
    *,
    run_id: str,
    source: Mapping[str, Any],
    result: Any,
    protected_data_state: object = "gated",
) -> dict[str, Any]:
    """Build canonical Monte Carlo evidence from a native result."""
    from persistence import ArtifactType

    normalized = normalize_monte_carlo_evidence(
        result,
        protected_data_state=protected_data_state,
    )
    if normalized.status == "invalid":
        raise ValueError(
            "Monte Carlo result does not satisfy evidence contract: "
            + "; ".join(normalized.reasons)
        )
    evidence_payload = {
        "monte_carlo": {
            "schema_version": result.schema_version,
            "status": result.status,
            "source": _source_document(
                result.source,
                observation_count=result.observation_count,
            ),
            "config": _config_document(result.config),
            "observation_count": result.observation_count,
            "original_metrics": result.original_metrics,
            "distributions": result.distributions,
            "loss_probability": result.loss_probability,
            "drawdown_breach_probability": result.drawdown_breach_probability,
            "threshold_results": tuple(
                _threshold_document(rule) for rule in result.threshold_results
            ),
            "execution_stress": tuple(
                _stress_document(stress) for stress in result.execution_stress
            ),
            "reasons": result.reasons,
            "warnings": result.warnings,
            "timestamp": result.timestamp,
            "paths": {
                "requested": result.config.persist_paths,
                "embedded": False,
                "path_count": len(result.paths) if result.paths is not None else 0,
                "availability": (
                    "not_persisted"
                    if result.paths is None
                    else "available_in_native_result_not_embedded"
                ),
            },
        },
        "normalized_evidence": {
            "stage_identity": normalized.stage_identity,
            "status": normalized.status,
            "reasons": normalized.reasons,
            "threshold_results": tuple(
                _normalized_threshold_document(rule)
                for rule in normalized.threshold_results
            ),
            "source_identity": normalized.source_identity,
            "protected_data_state": normalized.protected_data_state,
            "eligible_to_progress": normalized.eligible_to_progress,
        },
    }
    evidence_identity = _identity(_identity_payload(evidence_payload))
    document = {
        "artifact_schema_version": MONTE_CARLO_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "monte_carlo_evidence",
        "artifact": {
            "logical_name": MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
            "artifact_type": ArtifactType.VALIDATION_EVIDENCE.value,
            "format": "json",
            "evidence_identity": evidence_identity,
        },
        "source": dict(source),
        "evidence": evidence_payload,
    }
    _ = run_id
    return json.loads(canonical_json(document))
