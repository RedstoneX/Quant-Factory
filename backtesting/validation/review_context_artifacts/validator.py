"""Strict review-context artifact validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from backtesting.validation.review_context_artifacts.builder import (
    review_context_identity,
)
from backtesting.validation.review_context_artifacts.models import (
    REVIEW_CONTEXT_LOGICAL_NAME,
    REVIEW_CONTEXT_SCHEMA_VERSION,
)
from persistence.models import ArtifactContractRecord, ArtifactType

_PROTECTED_DATA_STATES = {"gated", "spent", "invalid"}


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} is missing or malformed")
    return value


def _require_nonblank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is missing or malformed")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _require_timestamp(value: Any, field: str) -> str:
    timestamp = _require_nonblank(value, field)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return timestamp


def source_lock_from_document(document: Mapping[str, Any]) -> Any:
    from backtesting.robustness.models import SourceLockEvidence

    required = (
        "status",
        "artifact_path",
        "artifact_kind",
        "artifact_id",
        "experiment_id",
        "strategy_id",
        "strategy_version",
        "data_provenance",
        "execution_assumptions",
        "metrics",
        "reasons",
    )
    for field in required:
        if field not in document:
            raise ValueError(f"source_lock.{field} is missing")
    if document["artifact_kind"] not in {"out_of_sample", "walk_forward", "unknown"}:
        raise ValueError("source_lock.artifact_kind is unsupported")
    if not isinstance(document.get("data_provenance"), Mapping):
        raise ValueError("source_lock.data_provenance is missing or malformed")
    if not isinstance(document.get("execution_assumptions"), Mapping):
        raise ValueError("source_lock.execution_assumptions is missing or malformed")
    if not isinstance(document.get("metrics"), Mapping):
        raise ValueError("source_lock.metrics is missing or malformed")
    reasons = document.get("reasons")
    if not isinstance(reasons, (list, tuple)):
        raise ValueError("source_lock.reasons is missing or malformed")
    return SourceLockEvidence(
        status=_require_nonblank(document.get("status"), "source_lock.status"),  # type: ignore[arg-type]
        artifact_path=_require_nonblank(
            document.get("artifact_path"),
            "source_lock.artifact_path",
        ),
        artifact_kind=document["artifact_kind"],  # type: ignore[arg-type]
        artifact_id=_require_nonblank(
            document.get("artifact_id"),
            "source_lock.artifact_id",
        ),
        schema_version=document.get("schema_version"),
        experiment_id=_require_nonblank(
            document.get("experiment_id"),
            "source_lock.experiment_id",
        ),
        strategy_id=_require_nonblank(
            document.get("strategy_id"),
            "source_lock.strategy_id",
        ),
        strategy_version=_require_nonblank(
            document.get("strategy_version"),
            "source_lock.strategy_version",
        ),
        locked_parameters=(
            dict(document["locked_parameters"])
            if isinstance(document.get("locked_parameters"), Mapping)
            else None
        ),
        source_start=document.get("source_start"),
        source_end=document.get("source_end"),
        data_provenance=dict(document["data_provenance"]),
        execution_assumptions=dict(document["execution_assumptions"]),
        metrics=dict(document["metrics"]),
        reasons=tuple(str(reason) for reason in reasons),
        parameter_lock_id=document.get("parameter_lock_id"),
    )


def validate_review_context_document(
    *,
    document: Mapping[str, Any],
    target_run_id: str,
    artifact: ArtifactContractRecord,
) -> SourceLockEvidence:
    """Validate a persisted review context and return its typed source lock."""
    if artifact.logical_name != REVIEW_CONTEXT_LOGICAL_NAME:
        raise ValueError("review context artifact logical name mismatch")
    if artifact.artifact_type != ArtifactType.VALIDATION_EVIDENCE:
        raise ValueError("review context artifact type mismatch")
    if artifact.schema_version != REVIEW_CONTEXT_SCHEMA_VERSION:
        raise ValueError("review context artifact schema version mismatch")
    if artifact.format != "json":
        raise ValueError("review context artifact format mismatch")
    if artifact.run_id != target_run_id:
        raise ValueError("review context artifact run mismatch")
    if document.get("schema_version") != REVIEW_CONTEXT_SCHEMA_VERSION:
        raise ValueError("review context document schema version mismatch")
    if document.get("artifact_kind") != REVIEW_CONTEXT_LOGICAL_NAME:
        raise ValueError("review context document kind mismatch")
    _require_timestamp(document.get("created_at"), "created_at")
    artifact_document = _require_mapping(document.get("artifact"), "artifact")
    if artifact_document.get("logical_name") != REVIEW_CONTEXT_LOGICAL_NAME:
        raise ValueError("review context embedded logical name mismatch")
    if artifact_document.get("artifact_type") != ArtifactType.VALIDATION_EVIDENCE.value:
        raise ValueError("review context embedded artifact type mismatch")
    if artifact_document.get("format") != "json":
        raise ValueError("review context embedded format mismatch")
    if artifact_document.get("schema_version") != REVIEW_CONTEXT_SCHEMA_VERSION:
        raise ValueError("review context embedded schema version mismatch")
    if document.get("target_run_id") != target_run_id:
        raise ValueError("review context target run mismatch")
    _require_nonblank(document.get("source_lock_run_id"), "source_lock_run_id")
    _require_positive_int(
        document.get("source_lock_artifact_id"),
        "source_lock_artifact_id",
    )
    for field in (
        "walk_forward_run_id",
        "monte_carlo_run_id",
        "robustness_run_id",
    ):
        _require_nonblank(document.get(field), field)
    if document.get("protected_data_state") not in _PROTECTED_DATA_STATES:
        raise ValueError("protected data state is unsupported")
    source_lock = source_lock_from_document(
        _require_mapping(document.get("source_lock"), "source_lock")
    )
    if artifact_document.get("context_identity") != review_context_identity(document):
        raise ValueError("review context identity mismatch")
    return source_lock
