"""Canonical document construction for generic walk-forward evidence artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from backtesting.validation.evidence_adapters import normalize_walk_forward_evidence
from backtesting.validation.evidence_models import WalkForwardWindowRules
from backtesting.validation.walk_forward_artifacts.models import (
    WALK_FORWARD_EVIDENCE_LOGICAL_NAME,
    WALK_FORWARD_EVIDENCE_SCHEMA_VERSION,
)
from persistence.serialization import canonical_json


def _identity(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(document).encode("utf-8")).hexdigest()


def _rules_document(rules: WalkForwardWindowRules) -> dict[str, Any]:
    return {
        "training_window_size": rules.training_window_size,
        "selection_window_size": rules.selection_window_size,
        "test_window_size": rules.test_window_size,
        "step_size": rules.step_size,
        "training_mode": rules.training_mode,
        "minimum_rows_per_window": rules.minimum_rows_per_window,
        "incomplete_final_window": rules.incomplete_final_window,
    }


def _partition_document(partition: object | None) -> dict[str, Any] | None:
    if partition is None:
        return None
    return {
        "name": partition.name,
        "start": partition.start,
        "end": partition.end,
        "row_count": partition.row_count,
    }


def _fold_document(fold: object) -> dict[str, Any]:
    window = fold.window
    return {
        "fold_id": fold.fold_id,
        "train": _partition_document(window.train),
        "selection": _partition_document(window.selection),
        "test": _partition_document(window.test),
        "status": fold.status,
        "failure_reason": fold.failure_reason,
        "parameter_lock_id": (
            fold.parameter_lock.lock_id if fold.parameter_lock is not None else None
        ),
        "selected_parameters": fold.selected_parameters,
        "test_metrics": fold.test_metrics,
    }


def build_walk_forward_evidence_document(
    *,
    run_id: str,
    source: Mapping[str, Any],
    result: Any,
    rules: WalkForwardWindowRules,
) -> dict[str, Any]:
    """Build canonical generic walk-forward evidence from a native result."""
    from persistence import ArtifactType

    normalized = normalize_walk_forward_evidence(result, window_rules=rules)
    if normalized.status == "invalid":
        raise ValueError(
            "walk-forward result does not satisfy declared rules: "
            + "; ".join(normalized.reasons)
        )
    folds = tuple(_fold_document(fold) for fold in result.folds)
    rules_doc = _rules_document(rules)
    evidence_payload = {
        "declared_walk_forward_rules": rules_doc,
        "folds": folds,
        "normalized_evidence": {
            "stage_identity": normalized.stage_identity,
            "status": normalized.status,
            "reasons": normalized.reasons,
            "protected_data_state": normalized.protected_data_state,
            "eligible_to_progress": normalized.eligible_to_progress,
        },
    }
    evidence_identity = _identity(evidence_payload)
    document = {
        "artifact_schema_version": WALK_FORWARD_EVIDENCE_SCHEMA_VERSION,
        "artifact_kind": "generic_walk_forward_evidence",
        "artifact": {
            "logical_name": WALK_FORWARD_EVIDENCE_LOGICAL_NAME,
            "artifact_type": ArtifactType.VALIDATION_EVIDENCE.value,
            "format": "json",
            "evidence_identity": evidence_identity,
        },
        "source": dict(source),
        "evidence": evidence_payload,
    }
    return json.loads(canonical_json(document))
