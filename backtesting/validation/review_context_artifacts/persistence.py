"""Persistence helpers for review-context artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backtesting.validation.review_context_artifacts.builder import (
    build_review_context_document,
)
from backtesting.validation.review_context_artifacts.models import (
    REVIEW_CONTEXT_LOGICAL_NAME,
    REVIEW_CONTEXT_SCHEMA_VERSION,
    PersistedReviewContextRecord,
)
from backtesting.validation.review_context_artifacts.validator import (
    validate_review_context_document,
)
from persistence.serialization import canonical_json


def _safe_artifact_path(root: Path, location: str) -> Path:
    relative = Path(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("artifact location is unsafe")
    candidate = (root.resolve() / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _context_artifacts(service: Any, target_run_id: str) -> tuple[Any, ...]:
    from persistence import ArtifactType

    return tuple(
        artifact
        for artifact in service.list_run_artifacts(target_run_id)
        if artifact.logical_name == REVIEW_CONTEXT_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )


def persist_review_context_artifact(
    *,
    service: Any,
    target_run_id: str,
    source_lock: Any,
    source_lock_run_id: str,
    source_lock_artifact_id: int,
    walk_forward_run_id: str,
    monte_carlo_run_id: str,
    robustness_run_id: str,
    protected_data_state: str,
    artifact_root: str | Path,
    created_at: str | None = None,
) -> PersistedReviewContextRecord:
    """Write and register one immutable post-run review context."""
    from persistence import ArtifactType

    document = build_review_context_document(
        target_run_id=target_run_id,
        source_lock=source_lock,
        source_lock_run_id=source_lock_run_id,
        source_lock_artifact_id=source_lock_artifact_id,
        walk_forward_run_id=walk_forward_run_id,
        monte_carlo_run_id=monte_carlo_run_id,
        robustness_run_id=robustness_run_id,
        protected_data_state=protected_data_state,  # type: ignore[arg-type]
        created_at=created_at,
    )
    existing = _context_artifacts(service, target_run_id)
    if len(existing) > 1:
        raise ValueError("multiple review context artifacts are registered")
    if existing:
        retrieved = retrieve_review_context_artifact(
            service=service,
            target_run_id=target_run_id,
            artifact_root=artifact_root,
        )
        if retrieved.context_identity == document["artifact"]["context_identity"]:
            return retrieved
        raise ValueError("conflicting review context artifact already exists")

    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{target_run_id}/{REVIEW_CONTEXT_LOGICAL_NAME}.json"
    target = _safe_artifact_path(Path(artifact_root), location)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=target_run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=REVIEW_CONTEXT_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=REVIEW_CONTEXT_SCHEMA_VERSION,
    )
    return PersistedReviewContextRecord(
        artifact=artifact,
        document=document,
        context_identity=document["artifact"]["context_identity"],
    )


def retrieve_review_context_artifact(
    *,
    service: Any,
    target_run_id: str,
    artifact_root: str | Path,
) -> PersistedReviewContextRecord:
    """Retrieve and validate one persisted review context artifact."""
    matches = _context_artifacts(service, target_run_id)
    if len(matches) != 1:
        raise ValueError("review context artifact is missing")
    artifact = matches[0]
    validation = service.validate_artifact(
        artifact.artifact_id,
        artifact_root=artifact_root,
    )
    if not validation.valid or validation.resolved_path is None:
        raise ValueError(
            f"review context artifact is unavailable: {validation.reason}"
        )
    try:
        document = json.loads(Path(validation.resolved_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"review context artifact JSON is corrupt: {exc}") from exc
    if not isinstance(document, Mapping):
        raise ValueError("review context artifact is not a JSON object")
    validate_review_context_document(
        document=document,
        target_run_id=target_run_id,
        artifact=artifact,
    )
    return PersistedReviewContextRecord(
        artifact=artifact,
        document=document,
        context_identity=document["artifact"]["context_identity"],
    )
