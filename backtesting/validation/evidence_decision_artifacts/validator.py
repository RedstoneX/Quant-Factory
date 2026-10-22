"""Strict evidence-decision artifact validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, get_args

from backtesting.validation.evidence_decision_artifacts.builder import (
    evidence_decision_identity,
)
from backtesting.validation.evidence_decision_artifacts.models import (
    EVIDENCE_DECISION_LOGICAL_NAME,
    EVIDENCE_DECISION_SCHEMA_VERSION,
)
from backtesting.validation.evidence_models import EvidenceStatus, ProtectedDataState
from backtesting.validation.lockbox_gate import (
    LockboxArtifactReference,
    LockboxGateResult,
    lockbox_gate_identity,
)
from persistence.models import ArtifactContractRecord, ArtifactType, ReviewState

_EVIDENCE_STATUSES = set(get_args(EvidenceStatus))
_PROTECTED_DATA_STATES = set(get_args(ProtectedDataState))


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is missing or malformed")
    return value


def _require_bool(value: Any, field: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")


def _require_nonblank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is missing or malformed")
    return value


def _require_optional_nonblank(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _require_nonblank(value, field)


def _require_timestamp(value: Any, field: str) -> str:
    timestamp = _require_nonblank(value, field)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return timestamp


def _require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _validate_enum(enum_type: Any, value: Any, field: str) -> str:
    try:
        return enum_type(value).value
    except ValueError as exc:
        raise ValueError(f"{field} is unsupported: {value}") from exc


def _validate_literal(values: set[str], value: Any, field: str) -> str:
    if value not in values:
        raise ValueError(f"{field} is unsupported: {value}")
    return str(value)


def validate_source_lineage(
    *,
    document: Mapping[str, Any],
    expected_source: Mapping[str, Any],
) -> None:
    if document.get("source") != dict(expected_source):
        raise ValueError("evidence decision source lineage mismatch")


def validate_evidence_decision_document(
    *,
    document: Mapping[str, Any],
    run_id: str,
    artifact: ArtifactContractRecord,
    expected_gate: LockboxGateResult | None = None,
) -> None:
    """Validate a persisted evidence-decision document and metadata."""
    if expected_gate is None:
        raise ValueError("expected lockbox gate is required")
    if artifact.logical_name != EVIDENCE_DECISION_LOGICAL_NAME:
        raise ValueError("evidence decision artifact logical name mismatch")
    if artifact.artifact_type != ArtifactType.VALIDATION_EVIDENCE:
        raise ValueError("evidence decision artifact type mismatch")
    if artifact.schema_version != EVIDENCE_DECISION_SCHEMA_VERSION:
        raise ValueError("evidence decision artifact schema version mismatch")
    if artifact.format != "json":
        raise ValueError("evidence decision artifact format mismatch")
    if artifact.run_id != run_id:
        raise ValueError("evidence decision artifact run mismatch")
    if document.get("schema_version") != EVIDENCE_DECISION_SCHEMA_VERSION:
        raise ValueError("evidence decision document schema version mismatch")
    if document.get("artifact_kind") != EVIDENCE_DECISION_LOGICAL_NAME:
        raise ValueError("evidence decision document kind mismatch")
    _require_timestamp(document.get("created_at"), "created_at")

    artifact_document = _require_mapping(document.get("artifact"), "artifact")
    if artifact_document.get("logical_name") != EVIDENCE_DECISION_LOGICAL_NAME:
        raise ValueError("evidence decision document logical name mismatch")
    if artifact_document.get("artifact_type") != ArtifactType.VALIDATION_EVIDENCE.value:
        raise ValueError("evidence decision document artifact type mismatch")
    if artifact_document.get("format") != "json":
        raise ValueError("evidence decision document artifact format mismatch")
    if artifact_document.get("schema_version") != EVIDENCE_DECISION_SCHEMA_VERSION:
        raise ValueError("evidence decision embedded schema version mismatch")

    source = _require_mapping(document.get("source"), "source")
    if source.get("run_id") != run_id:
        raise ValueError("evidence decision source run mismatch")

    decision = _require_mapping(document.get("decision"), "decision")
    if decision.get("eligible_to_progress") is not False:
        raise ValueError("evidence decision cannot be eligible to progress")
    gate = _require_mapping(decision.get("lockbox_gate"), "lockbox gate")
    review = _require_mapping(decision.get("review"), "review")

    status = _validate_literal(_EVIDENCE_STATUSES, gate.get("status"), "gate status")
    protected_state = _validate_literal(
        _PROTECTED_DATA_STATES,
        gate.get("protected_data_state"),
        "protected data state",
    )
    review_state = _validate_enum(ReviewState, review.get("state"), "review state")
    _require_bool(
        gate.get("eligible_to_execute_lockbox"),
        "eligible_to_execute_lockbox",
    )
    if gate.get("eligible_to_progress") is not False:
        raise ValueError("lockbox gate cannot be eligible to progress")
    stored_gate_identity = _require_nonblank(
        gate.get("gate_identity"),
        "lockbox gate identity",
    )

    references = gate.get("referenced_artifacts")
    if not isinstance(references, list):
        raise ValueError("referenced artifacts are missing or malformed")
    reference_records: list[LockboxArtifactReference] = []
    for reference in references:
        ref = _require_mapping(reference, "referenced artifact")
        stage = _require_nonblank(ref.get("stage"), "referenced artifact stage")
        artifact_id = _require_nonblank(
            ref.get("artifact_id"),
            "referenced artifact identity",
        )
        identity = ref.get("evidence_identity")
        if identity is not None and (not isinstance(identity, str) or not identity):
            raise ValueError("referenced evidence identity is malformed")
        reference_records.append(
            LockboxArtifactReference(
                stage=stage,  # type: ignore[arg-type]
                artifact_id=artifact_id,
                evidence_identity=identity,
            )
        )
    oos_references = [
        reference
        for reference in reference_records
        if reference.stage == "out_of_sample"
    ]
    if len(oos_references) != 1:
        raise ValueError("exactly one out-of-sample reference is required")
    if oos_references[0].evidence_identity is not None:
        raise ValueError("out-of-sample source-lock evidence identity must be omitted")

    reasons = gate.get("reasons")
    if not isinstance(reasons, list):
        raise ValueError("lockbox gate reasons are missing or malformed")
    for reason in reasons:
        if not isinstance(reason, str):
            raise ValueError("lockbox gate reason is malformed")
    parameter_lock_identity = _require_optional_nonblank(
        gate.get("parameter_lock_identity"),
        "parameter_lock_identity",
    )
    lineage_identity = _require_optional_nonblank(
        gate.get("lineage_identity"),
        "lineage_identity",
    )
    stored_gate = LockboxGateResult(
        status=status,  # type: ignore[arg-type]
        reasons=tuple(reasons),
        referenced_artifacts=tuple(reference_records),
        parameter_lock_identity=parameter_lock_identity,
        protected_data_state=protected_state,  # type: ignore[arg-type]
        lineage_identity=lineage_identity,
        gate_identity="",
        eligible_to_execute_lockbox=gate["eligible_to_execute_lockbox"],
        eligible_to_progress=False,
    )
    if lockbox_gate_identity(stored_gate) != stored_gate_identity:
        raise ValueError("stored lockbox gate identity mismatch")
    if stored_gate_identity != expected_gate.gate_identity:
        raise ValueError("lockbox gate identity mismatch")
    expected_fields = {
        "status": expected_gate.status,
        "reasons": tuple(expected_gate.reasons),
        "referenced_artifacts": tuple(expected_gate.referenced_artifacts),
        "parameter_lock_identity": expected_gate.parameter_lock_identity,
        "protected_data_state": expected_gate.protected_data_state,
        "lineage_identity": expected_gate.lineage_identity,
        "eligible_to_execute_lockbox": expected_gate.eligible_to_execute_lockbox,
        "eligible_to_progress": expected_gate.eligible_to_progress,
    }
    stored_fields = {
        "status": stored_gate.status,
        "reasons": stored_gate.reasons,
        "referenced_artifacts": stored_gate.referenced_artifacts,
        "parameter_lock_identity": stored_gate.parameter_lock_identity,
        "protected_data_state": stored_gate.protected_data_state,
        "lineage_identity": stored_gate.lineage_identity,
        "eligible_to_execute_lockbox": stored_gate.eligible_to_execute_lockbox,
        "eligible_to_progress": stored_gate.eligible_to_progress,
    }
    if stored_fields != expected_fields:
        raise ValueError("lockbox gate fields mismatch")

    audit_reference = review.get("audit_reference")
    if not isinstance(audit_reference, Mapping):
        raise ValueError("review audit reference is missing or malformed")
    _require_positive_int(audit_reference.get("audit_id"), "review audit_id")
    _require_timestamp(audit_reference.get("created_at"), "review audit created_at")
    target_type = _require_nonblank(review.get("target_type"), "review target_type")
    target_id = _require_nonblank(review.get("target_id"), "review target_id")
    reviewer = _require_nonblank(review.get("reviewer"), "review reviewer")
    reason = _require_nonblank(review.get("reason"), "review reason")
    if target_type != "run" or target_id != run_id:
        raise ValueError("review target does not match decision run")
    if audit_reference.get("target_type") != target_type:
        raise ValueError("review audit target type mismatch")
    if audit_reference.get("target_id") != target_id:
        raise ValueError("review audit target identity mismatch")
    if audit_reference.get("new_state") != review_state:
        raise ValueError("review audit state mismatch")
    if audit_reference.get("note") != reason:
        raise ValueError("review audit note mismatch")
    if audit_reference.get("operator") != reviewer:
        raise ValueError("review audit operator mismatch")

    expected_identity = evidence_decision_identity(document)
    if artifact_document.get("decision_identity") != expected_identity:
        raise ValueError("evidence decision identity mismatch")
