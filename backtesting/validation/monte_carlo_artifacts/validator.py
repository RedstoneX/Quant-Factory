"""Document-level validation for Monte Carlo evidence artifacts."""

from __future__ import annotations

from typing import Any, Mapping, get_args

from backtesting.validation.evidence_adapters import map_native_status
from backtesting.validation.evidence_models import ProtectedDataState
from backtesting.validation.monte_carlo_artifacts.builder import (
    _identity,
    _identity_payload,
)
from backtesting.validation.monte_carlo_artifacts.models import (
    MONTE_CARLO_EVIDENCE_SCHEMA_VERSION,
)

_NATIVE_STATUSES = {"passed", "failed", "insufficient_evidence"}
_STRESS_STATUSES = {"applied", "insufficient_evidence"}
_PROTECTED_DATA_STATES = set(get_args(ProtectedDataState))


def _require_mapping(document: object, label: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError(f"{label} is missing or malformed")
    return document


def _require_list(document: object, label: str) -> list[Any]:
    if not isinstance(document, list):
        raise ValueError(f"{label} is missing or malformed")
    return document


def _require_non_blank(document: object, label: str) -> str:
    if not isinstance(document, str) or not document.strip():
        raise ValueError(f"{label} is missing")
    return document


def _validate_config(document: dict[str, Any]) -> None:
    required = {
        "method",
        "seed",
        "simulation_count",
        "percentiles",
        "minimum_observations",
        "drawdown_threshold",
        "maximum_loss_probability",
        "maximum_drawdown_breach_probability",
        "lower_percentile",
        "minimum_lower_percentile_return",
        "block_length",
        "annualization_factor",
        "execution_cost_scenarios",
        "persist_paths",
    }
    missing = required - document.keys()
    if missing:
        raise ValueError(f"Monte Carlo config missing fields: {', '.join(sorted(missing))}")
    if not isinstance(document["seed"], int) or isinstance(document["seed"], bool):
        raise ValueError("Monte Carlo seed is malformed")
    for field in ("simulation_count", "minimum_observations"):
        if not isinstance(document[field], int) or isinstance(document[field], bool):
            raise ValueError(f"Monte Carlo {field} is malformed")
    _require_list(document["percentiles"], "Monte Carlo percentiles")
    _require_list(
        document["execution_cost_scenarios"],
        "Monte Carlo execution cost scenarios",
    )


def _validate_source(document: dict[str, Any]) -> None:
    for field in ("source_id", "source_kind", "experiment_id", "strategy_id", "strategy_version"):
        _require_non_blank(document.get(field), f"Monte Carlo source {field}")
    if not isinstance(document.get("observation_count"), int):
        raise ValueError("Monte Carlo source observation count is malformed")
    _require_non_blank(
        document.get("source_values_identity"),
        "Monte Carlo source-values identity",
    )
    if "values" in document:
        raise ValueError("Monte Carlo source values must not be embedded")
    _require_mapping(document.get("provenance"), "Monte Carlo source provenance")
    _require_mapping(
        document.get("execution_assumptions"),
        "Monte Carlo source execution assumptions",
    )


def _validate_thresholds(
    native: list[Any],
    normalized: list[Any],
) -> None:
    if len(native) != len(normalized):
        raise ValueError("Monte Carlo normalized thresholds do not match native thresholds")
    for native_rule, normalized_rule in zip(native, normalized, strict=True):
        native_doc = _require_mapping(native_rule, "Monte Carlo threshold")
        normalized_doc = _require_mapping(
            normalized_rule,
            "Monte Carlo normalized threshold",
        )
        expected_status = "passed" if native_doc.get("passed") is True else "failed"
        if normalized_doc.get("threshold_id") != native_doc.get("rule_id"):
            raise ValueError("Monte Carlo normalized threshold identity mismatch")
        if normalized_doc.get("status") != expected_status:
            raise ValueError("Monte Carlo normalized threshold status mismatch")
        if normalized_doc.get("observed") != native_doc.get("observed"):
            raise ValueError("Monte Carlo normalized threshold observed mismatch")
        if normalized_doc.get("threshold") != native_doc.get("threshold"):
            raise ValueError("Monte Carlo normalized threshold value mismatch")
        if normalized_doc.get("reason") != native_doc.get("message"):
            raise ValueError("Monte Carlo normalized threshold reason mismatch")


def _validate_monte_carlo_document(document: dict[str, Any]) -> None:
    evidence = _require_mapping(document.get("evidence"), "Monte Carlo evidence")
    monte_carlo = _require_mapping(
        evidence.get("monte_carlo"),
        "Monte Carlo native evidence",
    )
    normalized = _require_mapping(
        evidence.get("normalized_evidence"),
        "Monte Carlo normalized evidence",
    )
    if monte_carlo.get("schema_version") != 1:
        raise ValueError("unsupported native Monte Carlo schema version")
    native_status = monte_carlo.get("status")
    if native_status not in _NATIVE_STATUSES:
        raise ValueError("Monte Carlo native status is unsupported")
    _validate_source(_require_mapping(monte_carlo.get("source"), "Monte Carlo source"))
    _validate_config(_require_mapping(monte_carlo.get("config"), "Monte Carlo config"))
    if not isinstance(monte_carlo.get("observation_count"), int):
        raise ValueError("Monte Carlo observation count is malformed")
    if monte_carlo["source"]["observation_count"] != monte_carlo["observation_count"]:
        raise ValueError("Monte Carlo source observation count mismatch")
    _require_mapping(monte_carlo.get("original_metrics"), "Monte Carlo original metrics")
    _require_mapping(monte_carlo.get("distributions"), "Monte Carlo distributions")
    native_thresholds = _require_list(
        monte_carlo.get("threshold_results"),
        "Monte Carlo threshold results",
    )
    for stress in _require_list(
        monte_carlo.get("execution_stress"),
        "Monte Carlo execution stress",
    ):
        stress_doc = _require_mapping(stress, "Monte Carlo execution stress result")
        if stress_doc.get("status") not in _STRESS_STATUSES:
            raise ValueError("Monte Carlo execution stress status is unsupported")
    reasons = _require_list(monte_carlo.get("reasons"), "Monte Carlo reasons")
    _require_list(monte_carlo.get("warnings"), "Monte Carlo warnings")
    _require_non_blank(monte_carlo.get("timestamp"), "Monte Carlo timestamp")
    paths = _require_mapping(monte_carlo.get("paths"), "Monte Carlo paths")
    if "values" in paths or "paths" in paths:
        raise ValueError("Monte Carlo simulation paths must not be embedded")
    if paths.get("embedded") is not False:
        raise ValueError("Monte Carlo paths embedded flag is malformed")
    if not isinstance(paths.get("requested"), bool):
        raise ValueError("Monte Carlo paths requested flag is malformed")
    if not isinstance(paths.get("path_count"), int):
        raise ValueError("Monte Carlo path count is malformed")
    expected_status = map_native_status(native_status)
    if normalized.get("stage_identity") != "monte_carlo":
        raise ValueError("Monte Carlo normalized stage identity mismatch")
    if normalized.get("status") != expected_status:
        raise ValueError("Monte Carlo normalized status mismatch")
    if expected_status == "passed":
        expected_reasons = [str(reason).strip() for reason in reasons if str(reason).strip()]
    else:
        expected_reasons = reasons or [f"monte_carlo returned {expected_status}"]
    if normalized.get("reasons") != expected_reasons:
        raise ValueError("Monte Carlo normalized reasons mismatch")
    if normalized.get("source_identity") != monte_carlo["source"]["source_id"]:
        raise ValueError("Monte Carlo normalized source identity mismatch")
    if normalized.get("protected_data_state") not in _PROTECTED_DATA_STATES:
        raise ValueError("Monte Carlo protected-data state is unsupported")
    if not isinstance(normalized.get("eligible_to_progress"), bool):
        raise ValueError("Monte Carlo progression eligibility is malformed")
    if normalized.get("eligible_to_progress") is not False:
        raise ValueError("Monte Carlo evidence cannot automatically progress")
    _validate_thresholds(
        native_thresholds,
        _require_list(
            normalized.get("threshold_results"),
            "Monte Carlo normalized threshold results",
        ),
    )


def validate_monte_carlo_evidence_document(
    *,
    document: dict[str, Any],
    run_id: str,
    artifact: "ArtifactContractRecord",
) -> None:
    """Validate artifact identity, evidence shape, and evidence checksum."""
    if document.get("artifact_schema_version") != MONTE_CARLO_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported Monte Carlo evidence schema version")
    if document.get("artifact_kind") != "monte_carlo_evidence":
        raise ValueError("unsupported Monte Carlo evidence artifact kind")
    artifact_doc = _require_mapping(
        document.get("artifact"),
        "Monte Carlo evidence artifact identity",
    )
    if artifact_doc.get("logical_name") != artifact.logical_name:
        raise ValueError("Monte Carlo evidence logical name mismatch")
    if artifact_doc.get("artifact_type") != artifact.artifact_type.value:
        raise ValueError("Monte Carlo evidence artifact type mismatch")
    if artifact_doc.get("format") != artifact.format:
        raise ValueError("Monte Carlo evidence artifact format mismatch")
    source = document.get("source")
    if not isinstance(source, dict) or source.get("run_id") != run_id:
        raise ValueError("Monte Carlo evidence source run mismatch")
    _validate_monte_carlo_document(document)
    expected_identity = _identity(_identity_payload(document["evidence"]))
    if artifact_doc.get("evidence_identity") != expected_identity:
        raise ValueError("Monte Carlo evidence identity mismatch")


def validate_source_lineage(
    *,
    document: dict[str, Any],
    expected_source: Mapping[str, Any],
) -> None:
    source = document.get("source")
    if not isinstance(source, dict):
        raise ValueError("Monte Carlo evidence source lineage is missing")
    for key, expected_value in expected_source.items():
        if source.get(key) != expected_value:
            raise ValueError(f"Monte Carlo evidence source lineage mismatch: {key}")
