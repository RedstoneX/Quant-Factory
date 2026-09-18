"""Document-level validation for robustness evidence artifacts."""

from __future__ import annotations

from typing import Any, Mapping, get_args

from backtesting.validation.evidence_adapters import map_native_status
from backtesting.validation.evidence_models import ProtectedDataState
from backtesting.validation.robustness_artifacts.builder import (
    _compact_identity,
    _identity,
    _identity_payload,
)
from backtesting.validation.robustness_artifacts.models import (
    ROBUSTNESS_EVIDENCE_SCHEMA_VERSION,
)

_NATIVE_STATUSES = {"passed", "failed", "insufficient_evidence"}
_ALL_NATIVE_STATUSES = _NATIVE_STATUSES | {"invalid_input"}
_NORMALIZED_STATUSES = {"passed", "failed", "insufficient_evidence", "invalid"}
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


def _validate_threshold_document(document: dict[str, Any], label: str) -> None:
    _require_non_blank(document.get("rule_id"), f"{label} rule_id")
    if document.get("status") not in _ALL_NATIVE_STATUSES:
        raise ValueError(f"{label} status is unsupported")
    if "observed" not in document or "threshold" not in document:
        raise ValueError(f"{label} threshold values are missing")
    _require_non_blank(document.get("message"), f"{label} message")


def _collect_native_thresholds(robustness: dict[str, Any]) -> list[dict[str, Any]]:
    thresholds: list[dict[str, Any]] = []
    summary = robustness.get("neighborhood_summary")
    if summary is not None:
        summary_doc = _require_mapping(summary, "robustness neighborhood summary")
        if summary_doc.get("status") not in _ALL_NATIVE_STATUSES:
            raise ValueError("robustness neighborhood status is unsupported")
        thresholds.extend(
            _require_mapping(rule, "robustness neighborhood threshold")
            for rule in _require_list(
                summary_doc.get("threshold_results"),
                "robustness neighborhood thresholds",
            )
        )
    for regime in _require_list(robustness.get("regime_results"), "robustness regimes"):
        regime_doc = _require_mapping(regime, "robustness regime")
        _require_non_blank(regime_doc.get("regime_id"), "robustness regime_id")
        if regime_doc.get("status") not in _ALL_NATIVE_STATUSES:
            raise ValueError("robustness regime status is unsupported")
        for rule in _require_list(
            regime_doc.get("threshold_results"),
            "robustness regime thresholds",
        ):
            rule_doc = _require_mapping(rule, "robustness regime threshold")
            thresholds.append(
                {
                    **rule_doc,
                    "normalized_id": f"{regime_doc['regime_id']}:{rule_doc.get('rule_id')}",
                }
            )
    for rule in thresholds:
        _validate_threshold_document(rule, "robustness threshold")
    return thresholds


def _validate_source_and_config(robustness: dict[str, Any]) -> None:
    source = _require_mapping(robustness.get("source"), "robustness source")
    _require_non_blank(source.get("source_artifact_id"), "robustness source artifact")
    _require_non_blank(source.get("source_identity"), "robustness source identity")
    _require_mapping(source.get("data_provenance"), "robustness data provenance")
    _require_mapping(
        source.get("execution_assumptions"),
        "robustness execution assumptions",
    )
    expected_source_identity = _compact_identity(
        {
            "source_artifact_id": source["source_artifact_id"],
            "data_provenance": source["data_provenance"],
            "execution_assumptions": source["execution_assumptions"],
        }
    )
    if source["source_identity"] != expected_source_identity:
        raise ValueError("robustness source identity mismatch")
    forbidden = {"values", "returns", "trades", "orders", "raw_data", "source_data"}
    if forbidden & source.keys():
        raise ValueError("robustness source must not embed raw payloads")

    config = _require_mapping(robustness.get("configuration"), "robustness configuration")
    for field in ("strategy_id", "strategy_version", "experiment_id"):
        _require_non_blank(config.get(field), f"robustness configuration {field}")
    _require_mapping(
        config.get("locked_parameters"),
        "robustness locked parameters",
    )
    _require_non_blank(
        config.get("configuration_identity"),
        "robustness configuration identity",
    )
    expected_configuration_identity = _compact_identity(
        {
            "strategy_id": config["strategy_id"],
            "strategy_version": config["strategy_version"],
            "experiment_id": config["experiment_id"],
            "locked_parameters": config["locked_parameters"],
        }
    )
    if config["configuration_identity"] != expected_configuration_identity:
        raise ValueError("robustness configuration identity mismatch")


def _validate_parameter_evidence(robustness: dict[str, Any]) -> None:
    construction = robustness.get("neighborhood_construction")
    if construction is not None:
        construction_doc = _require_mapping(
            construction,
            "robustness neighborhood construction",
        )
        for field in (
            "requested_candidate_count",
            "raw_derived_count",
            "unique_normalized_count",
            "accepted_count",
            "rejected_count",
            "duplicate_count",
        ):
            if not isinstance(construction_doc.get(field), int):
                raise ValueError(f"robustness construction {field} is malformed")
        _require_list(
            construction_doc.get("candidates"),
            "robustness perturbation candidates",
        )
        _require_list(
            construction_doc.get("rejected_derivations"),
            "robustness rejected perturbations",
        )
    for point in _require_list(
        robustness.get("parameter_points"),
        "robustness parameter points",
    ):
        point_doc = _require_mapping(point, "robustness parameter point")
        _require_mapping(
            point_doc.get("normalized_parameters"),
            "robustness point parameters",
        )
        if point_doc.get("status") not in _ALL_NATIVE_STATUSES:
            raise ValueError("robustness parameter point status is unsupported")
        _require_list(
            point_doc.get("threshold_results"),
            "robustness point thresholds",
        )


def _validate_normalized(
    *,
    robustness: dict[str, Any],
    normalized: dict[str, Any],
    native_thresholds: list[dict[str, Any]],
) -> None:
    expected_status = map_native_status(robustness["status"])
    if normalized.get("stage_identity") != "robustness":
        raise ValueError("robustness normalized stage identity mismatch")
    if normalized.get("status") != expected_status:
        raise ValueError("robustness normalized status mismatch")
    reasons = _require_list(robustness.get("reasons"), "robustness reasons")
    if expected_status == "passed":
        expected_reasons = [str(reason).strip() for reason in reasons if str(reason).strip()]
    else:
        expected_reasons = reasons or [f"robustness returned {expected_status}"]
    if normalized.get("reasons") != expected_reasons:
        raise ValueError("robustness normalized reasons mismatch")
    if normalized.get("source_identity") != robustness["source"]["source_artifact_id"]:
        raise ValueError("robustness normalized source identity mismatch")
    if normalized.get("protected_data_state") not in _PROTECTED_DATA_STATES:
        raise ValueError("robustness protected-data state is unsupported")
    if not isinstance(normalized.get("eligible_to_progress"), bool):
        raise ValueError("robustness progression eligibility is malformed")
    if normalized.get("eligible_to_progress") is not False:
        raise ValueError("robustness evidence cannot automatically progress")

    normalized_thresholds = _require_list(
        normalized.get("threshold_results"),
        "robustness normalized thresholds",
    )
    if len(native_thresholds) != len(normalized_thresholds):
        raise ValueError("robustness normalized thresholds do not match native thresholds")
    for native, normalized_rule in zip(native_thresholds, normalized_thresholds, strict=True):
        normalized_doc = _require_mapping(
            normalized_rule,
            "robustness normalized threshold",
        )
        native_id = native.get("normalized_id", native.get("rule_id"))
        if normalized_doc.get("threshold_id") != native_id:
            raise ValueError("robustness normalized threshold identity mismatch")
        if normalized_doc.get("status") != map_native_status(native.get("status")):
            raise ValueError("robustness normalized threshold status mismatch")
        if normalized_doc.get("observed") != native.get("observed"):
            raise ValueError("robustness normalized threshold observed mismatch")
        if normalized_doc.get("threshold") != native.get("threshold"):
            raise ValueError("robustness normalized threshold value mismatch")
        if normalized_doc.get("reason") != native.get("message"):
            raise ValueError("robustness normalized threshold reason mismatch")


def _validate_robustness_document(document: dict[str, Any]) -> None:
    evidence = _require_mapping(document.get("evidence"), "robustness evidence")
    robustness = _require_mapping(
        evidence.get("robustness"),
        "robustness native evidence",
    )
    normalized = _require_mapping(
        evidence.get("normalized_evidence"),
        "robustness normalized evidence",
    )
    if robustness.get("schema_version") != 1:
        raise ValueError("unsupported native robustness schema version")
    if robustness.get("status") not in _NATIVE_STATUSES:
        raise ValueError("robustness native status is unsupported")
    _validate_source_and_config(robustness)
    _validate_parameter_evidence(robustness)
    native_thresholds = _collect_native_thresholds(robustness)
    components = _require_mapping(
        robustness.get("component_statuses"),
        "robustness component statuses",
    )
    if any(status not in _ALL_NATIVE_STATUSES for status in components.values()):
        raise ValueError("robustness component status is unsupported")
    _require_list(robustness.get("warnings"), "robustness warnings")
    _require_non_blank(robustness.get("timestamp"), "robustness timestamp")
    if normalized.get("status") not in _NORMALIZED_STATUSES:
        raise ValueError("robustness normalized status is unsupported")
    _validate_normalized(
        robustness=robustness,
        normalized=normalized,
        native_thresholds=native_thresholds,
    )


def validate_robustness_evidence_document(
    *,
    document: dict[str, Any],
    run_id: str,
    artifact: "ArtifactContractRecord",
) -> None:
    """Validate artifact identity, evidence shape, and evidence checksum."""
    if document.get("artifact_schema_version") != ROBUSTNESS_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported robustness evidence schema version")
    if document.get("artifact_kind") != "robustness_evidence":
        raise ValueError("unsupported robustness evidence artifact kind")
    artifact_doc = _require_mapping(
        document.get("artifact"),
        "robustness evidence artifact identity",
    )
    if artifact_doc.get("logical_name") != artifact.logical_name:
        raise ValueError("robustness evidence logical name mismatch")
    if artifact_doc.get("artifact_type") != artifact.artifact_type.value:
        raise ValueError("robustness evidence artifact type mismatch")
    if artifact_doc.get("format") != artifact.format:
        raise ValueError("robustness evidence artifact format mismatch")
    source = document.get("source")
    if not isinstance(source, dict) or source.get("run_id") != run_id:
        raise ValueError("robustness evidence source run mismatch")
    _validate_robustness_document(document)
    expected_identity = _identity(_identity_payload(document["evidence"]))
    if artifact_doc.get("evidence_identity") != expected_identity:
        raise ValueError("robustness evidence identity mismatch")


def validate_source_lineage(
    *,
    document: dict[str, Any],
    expected_source: Mapping[str, Any],
) -> None:
    source = document.get("source")
    if not isinstance(source, dict):
        raise ValueError("robustness evidence source lineage is missing")
    for key, expected_value in expected_source.items():
        if source.get(key) != expected_value:
            raise ValueError(f"robustness evidence source lineage mismatch: {key}")
