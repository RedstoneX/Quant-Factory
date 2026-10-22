"""Persistence helpers for Monte Carlo evidence artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backtesting.validation.monte_carlo_artifacts.builder import (
    build_monte_carlo_evidence_document,
)
from backtesting.validation.monte_carlo_artifacts.models import (
    MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
    MONTE_CARLO_EVIDENCE_SCHEMA_VERSION,
    PersistedMonteCarloEvidence,
)
from backtesting.validation.monte_carlo_artifacts.validator import (
    validate_monte_carlo_evidence_document,
    validate_source_lineage,
)
from persistence.serialization import canonical_json


def _safe_artifact_path(root: Path, location: str) -> Path:
    relative = Path(location)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("artifact location is unsafe")
    candidate = (root.resolve() / relative).resolve()
    candidate.relative_to(root.resolve())
    return candidate


def persist_monte_carlo_evidence_artifact(
    *,
    service: Any,
    run_id: str,
    source: Mapping[str, Any],
    result: Any,
    artifact_root: str | Path,
    protected_data_state: object = "gated",
) -> PersistedMonteCarloEvidence:
    """Write, register, and manifest one Monte Carlo evidence artifact."""
    from persistence import ArtifactType

    document = build_monte_carlo_evidence_document(
        run_id=run_id,
        source=source,
        result=result,
        protected_data_state=protected_data_state,
    )
    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{MONTE_CARLO_EVIDENCE_LOGICAL_NAME}.json"
    target = _safe_artifact_path(Path(artifact_root), location)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=MONTE_CARLO_EVIDENCE_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=MONTE_CARLO_EVIDENCE_SCHEMA_VERSION,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return PersistedMonteCarloEvidence(
        artifact=artifact,
        document=document,
        evidence_identity=document["artifact"]["evidence_identity"],
    )


def retrieve_monte_carlo_evidence_artifact(
    *,
    service: Any,
    run_id: str,
    artifact_root: str | Path,
    expected_source: Mapping[str, Any],
) -> PersistedMonteCarloEvidence:
    """Retrieve one validated Monte Carlo evidence artifact."""
    from persistence import ArtifactType

    retrieval = service.retrieve_run_artifacts(run_id, artifact_root=artifact_root)
    matches = tuple(
        artifact
        for artifact in retrieval.artifacts
        if artifact.logical_name == MONTE_CARLO_EVIDENCE_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )
    if len(matches) != 1:
        raise ValueError("Monte Carlo evidence artifact is missing")
    artifact = matches[0]
    validation_by_id = {
        validation.artifact_id: validation for validation in retrieval.validations
    }
    validation = validation_by_id.get(artifact.artifact_id)
    if validation is None or not validation.valid or validation.resolved_path is None:
        raise ValueError(
            f"Monte Carlo evidence artifact is unavailable: "
            f"{validation.reason if validation else 'validation_not_run'}"
        )
    try:
        document = json.loads(Path(validation.resolved_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Monte Carlo evidence artifact JSON is corrupt: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("Monte Carlo evidence artifact is not a JSON object")
    validate_monte_carlo_evidence_document(
        document=document,
        run_id=run_id,
        artifact=artifact,
    )
    validate_source_lineage(document=document, expected_source=expected_source)
    return PersistedMonteCarloEvidence(
        artifact=artifact,
        document=document,
        evidence_identity=document["artifact"]["evidence_identity"],
    )
