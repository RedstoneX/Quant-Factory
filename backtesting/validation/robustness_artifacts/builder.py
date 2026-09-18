"""Canonical document construction for robustness evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backtesting.validation.evidence_adapters import normalize_robustness_evidence
from backtesting.validation.robustness_artifacts.models import (
    ROBUSTNESS_EVIDENCE_LOGICAL_NAME,
    ROBUSTNESS_EVIDENCE_SCHEMA_VERSION,
)
from persistence.serialization import canonical_json


def _identity(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def _compact_identity(payload: Any) -> str:
    return _identity({"payload": payload})


def _identity_payload(evidence_payload: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(canonical_json(evidence_payload))
    payload["robustness"].pop("timestamp", None)
    return payload


def _threshold_document(rule: object) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id,
        "status": rule.status,
        "observed": rule.observed,
        "threshold": rule.threshold,
        "message": rule.message,
    }


def _derivation_document(derivation: object) -> dict[str, Any]:
    return {
        "parameter_name": derivation.parameter_name,
        "locked_value": derivation.locked_value,
        "method": derivation.method,
        "source_value": derivation.source_value,
        "raw_value": derivation.raw_value,
        "normalized_value": derivation.normalized_value,
        "status": derivation.status,
        "rejection_reason": derivation.rejection_reason,
        "normalization_created_duplicate": derivation.normalization_created_duplicate,
    }


def _candidate_document(candidate: object) -> dict[str, Any]:
    return {
        "normalized_parameters": candidate.normalized_parameters,
        "derivations": tuple(
            _derivation_document(derivation) for derivation in candidate.derivations
        ),
        "is_locked_point": candidate.is_locked_point,
    }


def _construction_document(construction: object | None) -> dict[str, Any] | None:
    if construction is None:
        return None
    return {
        "requested_candidate_count": construction.requested_candidate_count,
        "raw_derived_count": construction.raw_derived_count,
        "unique_normalized_count": construction.unique_normalized_count,
        "accepted_count": construction.accepted_count,
        "rejected_count": construction.rejected_count,
        "duplicate_count": construction.duplicate_count,
        "candidates": tuple(
            _candidate_document(candidate) for candidate in construction.candidates
        ),
        "rejected_derivations": tuple(
            _derivation_document(derivation)
            for derivation in construction.rejected_derivations
        ),
    }


def _parameter_point_document(point: object) -> dict[str, Any]:
    return {
        "normalized_parameters": point.normalized_parameters,
        "derivations": tuple(
            _derivation_document(derivation) for derivation in point.derivations
        ),
        "is_locked_point": point.is_locked_point,
        "status": point.status,
        "total_return": point.total_return,
        "maximum_drawdown": point.maximum_drawdown,
        "sharpe_ratio": point.sharpe_ratio,
        "trade_count": point.trade_count,
        "screening_status": point.screening_status,
        "hygiene_status": point.hygiene_status,
        "absolute_degradation": point.absolute_degradation,
        "relative_degradation": point.relative_degradation,
        "degradation_unit": point.degradation_unit,
        "degradation_interpretation": point.degradation_interpretation,
        "threshold_results": tuple(
            _threshold_document(rule) for rule in point.threshold_results
        ),
        "reasons": point.reasons,
        "warnings": point.warnings,
        "source_run_identity": point.source_run_identity,
    }


def _dimension_document(dimension: object) -> dict[str, Any]:
    return {
        "parameter_name": dimension.parameter_name,
        "tested_values": dimension.tested_values,
        "locked_value": dimension.locked_value,
        "pass_count": dimension.pass_count,
        "return_range": dimension.return_range,
        "drawdown_range": dimension.drawdown_range,
        "behavior": dimension.behavior,
    }


def _summary_document(summary: object | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    return {
        "requested_candidate_count": summary.requested_candidate_count,
        "raw_derived_count": summary.raw_derived_count,
        "unique_normalized_count": summary.unique_normalized_count,
        "rejected_count": summary.rejected_count,
        "duplicate_count": summary.duplicate_count,
        "valid_count": summary.valid_count,
        "evaluated_count": summary.evaluated_count,
        "passing_count": summary.passing_count,
        "passing_proportion": summary.passing_proportion,
        "proportion_within_degradation_limit": (
            summary.proportion_within_degradation_limit
        ),
        "median_total_return": summary.median_total_return,
        "worst_total_return": summary.worst_total_return,
        "median_maximum_drawdown": summary.median_maximum_drawdown,
        "worst_maximum_drawdown": summary.worst_maximum_drawdown,
        "median_sharpe": summary.median_sharpe,
        "locked_point_rank": summary.locked_point_rank,
        "locked_point_status": summary.locked_point_status,
        "dimension_stability": tuple(
            _dimension_document(dimension)
            for dimension in summary.dimension_stability
        ),
        "threshold_results": tuple(
            _threshold_document(rule) for rule in summary.threshold_results
        ),
        "status": summary.status,
        "reasons": summary.reasons,
    }


def _metadata_document(metadata: object | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    return {
        "first_usable_timestamp": metadata.first_usable_timestamp,
        "warmup_observation_count": metadata.warmup_observation_count,
        "trend_rule": metadata.trend_rule,
        "volatility_rule": metadata.volatility_rule,
        "annualization_factor": metadata.annualization_factor,
        "attribution_policy": metadata.attribution_policy,
    }


def _regime_document(regime: object) -> dict[str, Any]:
    return {
        "regime_id": regime.regime_id,
        "trend_component": regime.trend_component,
        "volatility_component": regime.volatility_component,
        "first_timestamp": regime.first_timestamp,
        "last_timestamp": regime.last_timestamp,
        "observation_count": regime.observation_count,
        "trade_count": regime.trade_count,
        "total_return": regime.total_return,
        "maximum_drawdown": regime.maximum_drawdown,
        "sharpe_ratio": regime.sharpe_ratio,
        "win_rate": regime.win_rate,
        "minimum_observations": regime.minimum_observations,
        "minimum_trades": regime.minimum_trades,
        "threshold_results": tuple(
            _threshold_document(rule) for rule in regime.threshold_results
        ),
        "status": regime.status,
        "reasons": regime.reasons,
        "warnings": regime.warnings,
    }


def _normalized_threshold_document(rule: object) -> dict[str, Any]:
    return {
        "threshold_id": rule.threshold_id,
        "status": rule.status,
        "observed": rule.observed,
        "threshold": rule.threshold,
        "reason": rule.reason,
    }


def build_robustness_evidence_document(
    *,
    run_id: str,
    source: Mapping[str, Any],
    result: Any,
    protected_data_state: object = "gated",
) -> dict[str, Any]:
    """Build canonical robustness evidence from a native result."""
    from persistence import ArtifactType

    normalized = normalize_robustness_evidence(
        result,
        protected_data_state=protected_data_state,
    )
    if normalized.status == "invalid":
        raise ValueError(
            "Robustness result does not satisfy evidence contract: "
            + "; ".join(normalized.reasons)
        )
    evidence_payload = {
        "robustness": {
            "schema_version": result.schema_version,
            "status": result.status,
            "source": {
                "source_artifact_id": result.source_artifact_id,
                "source_identity": _compact_identity(
                    {
                        "source_artifact_id": result.source_artifact_id,
                        "data_provenance": result.data_provenance,
                        "execution_assumptions": result.execution_assumptions,
                    }
                ),
                "data_provenance": result.data_provenance,
                "execution_assumptions": result.execution_assumptions,
            },
            "configuration": {
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "experiment_id": result.experiment_id,
                "locked_parameters": result.locked_parameters,
                "configuration_identity": _compact_identity(
                    {
                        "strategy_id": result.strategy_id,
                        "strategy_version": result.strategy_version,
                        "experiment_id": result.experiment_id,
                        "locked_parameters": result.locked_parameters,
                    }
                ),
            },
            "neighborhood_construction": _construction_document(
                result.neighborhood_construction
            ),
            "parameter_points": tuple(
                _parameter_point_document(point) for point in result.parameter_points
            ),
            "neighborhood_summary": _summary_document(result.neighborhood_summary),
            "regime_metadata": _metadata_document(result.regime_metadata),
            "regime_results": tuple(
                _regime_document(regime) for regime in result.regime_results
            ),
            "component_statuses": result.component_statuses,
            "reasons": result.reasons,
            "warnings": result.warnings,
            "timestamp": result.timestamp,
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
        "artifact_schema_version": ROBUSTNESS_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "robustness_evidence",
        "artifact": {
            "logical_name": ROBUSTNESS_EVIDENCE_LOGICAL_NAME,
            "artifact_type": ArtifactType.VALIDATION_EVIDENCE.value,
            "format": "json",
            "evidence_identity": evidence_identity,
        },
        "source": dict(source),
        "evidence": evidence_payload,
    }
    _ = run_id
    return json.loads(canonical_json(document))
