"""Canonical evidence-decision artifact construction."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any, get_args

from backtesting.validation.evidence_decision_artifacts.models import (
    EVIDENCE_DECISION_LOGICAL_NAME,
    EVIDENCE_DECISION_SCHEMA_VERSION,
)
from backtesting.validation.evidence_models import EvidenceStatus, ProtectedDataState
from backtesting.validation.lockbox_gate import LockboxGateResult
from persistence.models import ReviewRecord, ReviewState
from persistence.repositories import utc_now
from persistence.serialization import canonical_json

_EVIDENCE_STATUSES = set(get_args(EvidenceStatus))
_PROTECTED_DATA_STATES = set(get_args(ProtectedDataState))


def _identity(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _enum_value(enum_type: Any, value: Any, *, field: str) -> str:
    try:
        return enum_type(value).value
    except ValueError as exc:
        raise ValueError(f"{field} is unsupported: {value}") from exc


def _literal_value(values: set[str], value: Any, *, field: str) -> str:
    if value not in values:
        raise ValueError(f"{field} is unsupported: {value}")
    return str(value)


def _artifact_reference(reference: Any) -> dict[str, Any]:
    return {
        "stage": reference.stage,
        "artifact_id": reference.artifact_id,
        "evidence_identity": reference.evidence_identity,
    }


def _review_document(
    *,
    review: ReviewRecord,
    audit_reference: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "target_type": review.target_type,
        "target_id": review.target_id,
        "state": _enum_value(ReviewState, review.state, field="review state"),
        "reviewer": review.operator,
        "reason": review.note,
        "audit_reference": dict(audit_reference or {}),
    }


def evidence_decision_identity(document: Mapping[str, Any]) -> str:
    """Stable identity for evidence/review facts, excluding audit-only timestamps."""
    payload = {
        "source": document.get("source"),
        "decision": document.get("decision"),
    }
    review = payload.get("decision", {}).get("review")  # type: ignore[union-attr]
    if isinstance(review, dict):
        audit = review.get("audit_reference")
        if isinstance(audit, dict):
            audit = dict(audit)
            audit.pop("audit_id", None)
            audit.pop("created_at", None)
            review = dict(review)
            review["audit_reference"] = audit
            payload["decision"] = dict(payload["decision"])  # type: ignore[arg-type]
            payload["decision"]["review"] = review  # type: ignore[index]
    return _identity(payload)


def build_evidence_decision_document(
    *,
    run_id: str,
    source: Mapping[str, Any],
    gate_result: LockboxGateResult,
    review: ReviewRecord,
    audit_reference: Mapping[str, Any] | None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build the canonical compact evidence-decision artifact document."""
    status = _literal_value(
        _EVIDENCE_STATUSES,
        gate_result.status,
        field="gate status",
    )
    protected_state = _literal_value(
        _PROTECTED_DATA_STATES,
        gate_result.protected_data_state,
        field="protected data state",
    )
    if gate_result.eligible_to_progress is not False:
        raise ValueError("lockbox gate must not be eligible to progress")
    decision = {
        "lockbox_gate": {
            "gate_identity": gate_result.gate_identity,
            "status": status,
            "reasons": tuple(gate_result.reasons),
            "referenced_artifacts": tuple(
                _artifact_reference(reference)
                for reference in gate_result.referenced_artifacts
            ),
            "parameter_lock_identity": gate_result.parameter_lock_identity,
            "lineage_identity": gate_result.lineage_identity,
            "protected_data_state": protected_state,
            "eligible_to_execute_lockbox": gate_result.eligible_to_execute_lockbox,
            "eligible_to_progress": False,
        },
        "review": _review_document(
            review=review,
            audit_reference=audit_reference,
        ),
        "eligible_to_progress": False,
    }
    document = {
        "schema_version": EVIDENCE_DECISION_SCHEMA_VERSION,
        "artifact_kind": EVIDENCE_DECISION_LOGICAL_NAME,
        "artifact": {
            "logical_name": EVIDENCE_DECISION_LOGICAL_NAME,
            "artifact_type": "validation_evidence",
            "format": "json",
            "schema_version": EVIDENCE_DECISION_SCHEMA_VERSION,
            "decision_identity": "",
        },
        "source": dict(source),
        "decision": decision,
        "created_at": created_at or utc_now(),
    }
    if document["source"].get("run_id") != run_id:
        raise ValueError("source run identity does not match decision run")
    document["artifact"]["decision_identity"] = evidence_decision_identity(document)
    return document
