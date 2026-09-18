"""Persistence helpers for evidence-decision artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backtesting.validation.evidence_decision_artifacts.builder import (
    build_evidence_decision_document,
)
from backtesting.validation.evidence_decision_artifacts.models import (
    EVIDENCE_DECISION_LOGICAL_NAME,
    EVIDENCE_DECISION_SCHEMA_VERSION,
    PersistedEvidenceDecisionRecord,
)
from backtesting.validation.evidence_decision_artifacts.validator import (
    validate_evidence_decision_document,
    validate_source_lineage,
)
from persistence.serialization import canonical_json

_REFERENCE_LOGICAL_NAMES = {
    "walk_forward": "walk_forward_evidence",
    "monte_carlo": "monte_carlo_evidence",
    "robustness": "robustness_evidence",
}


def _safe_artifact_path(root: Path, location: str) -> Path:
    relative = Path(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("artifact location is unsafe")
    candidate = (root.resolve() / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def _decision_artifacts(service: Any, run_id: str) -> tuple[Any, ...]:
    from persistence import ArtifactType

    return tuple(
        artifact
        for artifact in service.list_run_artifacts(run_id)
        if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )


def _validated_document(
    *,
    service: Any,
    artifact_id: int,
    artifact_root: str | Path,
) -> Mapping[str, Any]:
    validation = service.validate_artifact(artifact_id, artifact_root=artifact_root)
    if not validation.valid or validation.resolved_path is None:
        raise ValueError(
            f"referenced evidence artifact is unavailable: {validation.reason}"
        )
    try:
        document = json.loads(Path(validation.resolved_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"referenced evidence artifact JSON is corrupt: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("referenced evidence artifact is not a JSON object")
    return document


def _validate_references(
    *,
    service: Any,
    document: Mapping[str, Any],
    artifact_root: str | Path,
) -> None:
    decision = document["decision"]
    gate = decision["lockbox_gate"]
    oos_references = [
        reference
        for reference in gate["referenced_artifacts"]
        if reference["stage"] == "out_of_sample"
    ]
    if len(oos_references) != 1:
        raise ValueError("exactly one out-of-sample reference is required")
    for reference in gate["referenced_artifacts"]:
        evidence_identity = reference.get("evidence_identity")
        if evidence_identity is None:
            continue
        artifact_id = int(reference["artifact_id"])
        artifact = service.get_artifact_metadata(artifact_id)
        expected_logical_name = _REFERENCE_LOGICAL_NAMES.get(reference["stage"])
        if artifact.logical_name != expected_logical_name:
            raise ValueError("referenced evidence artifact stage mismatch")
        referenced = _validated_document(
            service=service,
            artifact_id=artifact.artifact_id,
            artifact_root=artifact_root,
        )
        actual_identity = referenced.get("artifact", {}).get("evidence_identity")
        if actual_identity != evidence_identity:
            raise ValueError("referenced evidence identity mismatch")


def persist_evidence_decision_artifact(
    *,
    service: Any,
    run_id: str,
    source: Mapping[str, Any],
    gate_result: Any,
    review: Any,
    audit_reference: Mapping[str, Any] | None,
    artifact_root: str | Path,
    created_at: str | None = None,
) -> PersistedEvidenceDecisionRecord:
    """Write and register one compact post-run evidence-decision record."""
    from persistence import ArtifactType

    document = build_evidence_decision_document(
        run_id=run_id,
        source=source,
        gate_result=gate_result,
        review=review,
        audit_reference=audit_reference,
        created_at=created_at,
    )
    existing = _decision_artifacts(service, run_id)
    if len(existing) > 1:
        raise ValueError("multiple evidence decision artifacts are registered")
    if existing:
        retrieved = retrieve_evidence_decision_artifact(
            service=service,
            run_id=run_id,
            artifact_root=artifact_root,
            expected_source=source,
            expected_gate=gate_result,
        )
        if retrieved.decision_identity == document["artifact"]["decision_identity"]:
            return retrieved
        raise ValueError("conflicting evidence decision artifact already exists")

    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{EVIDENCE_DECISION_LOGICAL_NAME}.json"
    target = _safe_artifact_path(Path(artifact_root), location)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=EVIDENCE_DECISION_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=EVIDENCE_DECISION_SCHEMA_VERSION,
    )
    return PersistedEvidenceDecisionRecord(
        artifact=artifact,
        document=document,
        decision_identity=document["artifact"]["decision_identity"],
    )


def retrieve_evidence_decision_artifact(
    *,
    service: Any,
    run_id: str,
    artifact_root: str | Path,
    expected_source: Mapping[str, Any],
    expected_gate: Any | None = None,
) -> PersistedEvidenceDecisionRecord:
    """Retrieve one validated evidence-decision artifact."""
    if expected_gate is None:
        raise ValueError("expected lockbox gate is required")

    matches = _decision_artifacts(service, run_id)
    if len(matches) != 1:
        raise ValueError("evidence decision artifact is missing")
    artifact = matches[0]
    validation = service.validate_artifact(
        artifact.artifact_id,
        artifact_root=artifact_root,
    )
    if validation is None or not validation.valid or validation.resolved_path is None:
        raise ValueError(
            f"evidence decision artifact is unavailable: "
            f"{validation.reason if validation else 'validation_not_run'}"
        )
    try:
        document = json.loads(Path(validation.resolved_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"evidence decision artifact JSON is corrupt: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("evidence decision artifact is not a JSON object")
    validate_evidence_decision_document(
        document=document,
        run_id=run_id,
        artifact=artifact,
        expected_gate=expected_gate,
    )
    validate_source_lineage(document=document, expected_source=expected_source)
    _validate_references(
        service=service,
        document=document,
        artifact_root=artifact_root,
    )
    return PersistedEvidenceDecisionRecord(
        artifact=artifact,
        document=document,
        decision_identity=document["artifact"]["decision_identity"],
    )
