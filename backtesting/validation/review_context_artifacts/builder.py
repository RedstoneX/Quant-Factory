"""Canonical review-context artifact construction."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping

from backtesting.validation.evidence_models import ProtectedDataState
from backtesting.validation.review_context_artifacts.models import (
    REVIEW_CONTEXT_LOGICAL_NAME,
    REVIEW_CONTEXT_SCHEMA_VERSION,
)
from persistence.repositories import utc_now
from persistence.serialization import canonical_json

_PROTECTED_DATA_STATES = {"gated", "spent", "invalid"}


def _identity(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def source_lock_document(source_lock: Any) -> dict[str, Any]:
    if is_dataclass(source_lock):
        return asdict(source_lock)
    if isinstance(source_lock, Mapping):
        return dict(source_lock)
    fields = (
        "status",
        "artifact_path",
        "artifact_kind",
        "artifact_id",
        "schema_version",
        "experiment_id",
        "strategy_id",
        "strategy_version",
        "locked_parameters",
        "source_start",
        "source_end",
        "data_provenance",
        "execution_assumptions",
        "metrics",
        "reasons",
        "parameter_lock_id",
    )
    return {field: getattr(source_lock, field) for field in fields}


def review_context_identity(document: Mapping[str, Any]) -> str:
    payload = {
        "target_run_id": document.get("target_run_id"),
        "source_lock_run_id": document.get("source_lock_run_id"),
        "source_lock_artifact_id": document.get("source_lock_artifact_id"),
        "source_lock": document.get("source_lock"),
        "walk_forward_run_id": document.get("walk_forward_run_id"),
        "monte_carlo_run_id": document.get("monte_carlo_run_id"),
        "robustness_run_id": document.get("robustness_run_id"),
        "protected_data_state": document.get("protected_data_state"),
    }
    return _identity(payload)


def build_review_context_document(
    *,
    target_run_id: str,
    source_lock: Any,
    source_lock_run_id: str,
    source_lock_artifact_id: int,
    walk_forward_run_id: str,
    monte_carlo_run_id: str,
    robustness_run_id: str,
    protected_data_state: ProtectedDataState,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a canonical persisted review-context document from explicit inputs."""
    if protected_data_state not in _PROTECTED_DATA_STATES:
        raise ValueError(f"protected data state is unsupported: {protected_data_state}")
    document = {
        "schema_version": REVIEW_CONTEXT_SCHEMA_VERSION,
        "artifact_kind": REVIEW_CONTEXT_LOGICAL_NAME,
        "artifact": {
            "logical_name": REVIEW_CONTEXT_LOGICAL_NAME,
            "artifact_type": "validation_evidence",
            "format": "json",
            "schema_version": REVIEW_CONTEXT_SCHEMA_VERSION,
            "context_identity": "",
        },
        "target_run_id": target_run_id,
        "source_lock_run_id": source_lock_run_id,
        "source_lock_artifact_id": source_lock_artifact_id,
        "source_lock": source_lock_document(source_lock),
        "walk_forward_run_id": walk_forward_run_id,
        "monte_carlo_run_id": monte_carlo_run_id,
        "robustness_run_id": robustness_run_id,
        "protected_data_state": protected_data_state,
        "created_at": created_at or utc_now(),
    }
    document["artifact"]["context_identity"] = review_context_identity(document)
    return document
