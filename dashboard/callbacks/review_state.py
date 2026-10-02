"""Integrity-checked durable review state for dashboard callbacks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from persistence import (
    ArtifactType,
    PersistenceService,
    ReviewState,
    RunStage,
    RunStatus,
)
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from persistence.database import artifact_file_transaction, transaction
from persistence.repositories import utc_now
from persistence.serialization import canonical_json

SCREENING_REJECTION_SCHEMA_VERSION = 2
SCREENING_REJECTION_ARTIFACT_KIND = "terminal_screening_rejection_decision"


@dataclass(frozen=True)
class DurableReviewSnapshot:
    """Latest validated durable decision and its append-only audit history."""

    state: ReviewState
    note: str
    operator: str | None
    updated_at: str | None
    history: tuple[dict[str, Any], ...]
    decision_identity: str | None

    @property
    def display_state(self) -> str:
        return self.state.value.replace("_", " ").capitalize()


@dataclass(frozen=True)
class ScreeningRejectionDecision:
    document: dict[str, Any]
    decision_identity: str


def _screening_rejection_context(
    service: PersistenceService,
    run_id: str,
    *,
    artifact_root: str | Path,
) -> dict[str, Any]:
    run = service.runs.get(run_id)
    if run is None:
        raise KeyError(f"unknown run {run_id}")
    if run.stage != RunStage.SCREENING or run.status != RunStatus.SUCCEEDED:
        raise ValueError("run is not a completed screening outcome")
    rows = service.results.list_parameter_results(run_id)
    if not rows or any(row.screening_status != "screened_out" for row in rows):
        raise ValueError("screening run is not a terminal rejected outcome")
    retrieval = service.retrieve_run_artifacts(run_id, artifact_root=artifact_root)
    invalid = [
        validation.reason
        for validation in retrieval.validations
        if not validation.valid
    ]
    if invalid:
        raise ValueError(f"screening evidence artifact integrity failed: {invalid[0]}")
    source = ValidationEvidenceArtifactService(service).source_document(run_id)
    result_rows = [
        {
            "row_id": row.row_id,
            "normalized_parameters_json": row.normalized_parameters_json,
            "metrics_json": row.metrics_json,
            "ranking_position": row.ranking_position,
            "screening_status": row.screening_status,
            "rejection_reasons": row.rejection_reasons,
        }
        for row in rows
    ]
    return {
        "source": source,
        "manifest_checksum": retrieval.manifest_checksum,
        "parameter_results": result_rows,
    }


def screening_rejection_available(
    service: PersistenceService,
    run_id: str,
    *,
    artifact_root: str | Path,
) -> bool:
    _screening_rejection_context(service, run_id, artifact_root=artifact_root)
    artifacts = tuple(
        artifact
        for artifact in service.list_run_artifacts(run_id)
        if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )
    if len(artifacts) > 1:
        raise ValueError("multiple evidence decision artifacts are registered")
    if artifacts:
        _read_screening_rejection_decision(
            service,
            artifacts[0],
            run_id=run_id,
            artifact_root=artifact_root,
        )
    return True


def _screening_decision_identity(document: dict[str, Any]) -> str:
    identity_document = json.loads(canonical_json(document))
    identity_document.pop("created_at", None)
    identity_document.get("artifact", {}).pop("decision_identity", None)
    return hashlib.sha256(
        canonical_json(identity_document).encode("utf-8")
    ).hexdigest()


def _read_screening_rejection_decision(
    service: PersistenceService,
    artifact: Any,
    *,
    run_id: str,
    artifact_root: str | Path,
) -> ScreeningRejectionDecision:
    if artifact.schema_version != SCREENING_REJECTION_SCHEMA_VERSION:
        raise ValueError("screening rejection artifact schema version mismatch")
    if artifact.run_id != run_id or artifact.format != "json":
        raise ValueError("screening rejection artifact metadata mismatch")
    validation = service.validate_artifact(
        artifact.artifact_id, artifact_root=artifact_root
    )
    if not validation.valid or validation.resolved_path is None:
        raise ValueError(f"screening rejection artifact is unavailable: {validation.reason}")
    try:
        document = json.loads(Path(validation.resolved_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("screening rejection artifact JSON is corrupt") from exc
    if (
        not isinstance(document, dict)
        or document.get("artifact_kind") != SCREENING_REJECTION_ARTIFACT_KIND
    ):
        raise ValueError("screening rejection artifact kind mismatch")
    if document.get("schema_version") != SCREENING_REJECTION_SCHEMA_VERSION:
        raise ValueError("screening rejection document schema version mismatch")
    artifact_document = document.get("artifact")
    if not isinstance(artifact_document, dict) or artifact_document.get(
        "logical_name"
    ) != EVIDENCE_DECISION_LOGICAL_NAME:
        raise ValueError("screening rejection embedded artifact metadata mismatch")
    expected_context = _screening_rejection_context(
        service, run_id, artifact_root=artifact_root
    )
    if document.get("screening_context") != expected_context:
        raise ValueError("screening rejection evidence identity mismatch")
    identity = artifact_document.get("decision_identity")
    if (
        not isinstance(identity, str)
        or identity != _screening_decision_identity(document)
    ):
        raise ValueError("screening rejection decision identity mismatch")
    decision = document.get("decision")
    review = decision.get("review") if isinstance(decision, dict) else None
    if not isinstance(review, dict) or review.get("state") != ReviewState.REJECT.value:
        raise ValueError("screening rejection artifact must record Reject")
    if decision.get("eligible_to_progress") is not False:
        raise ValueError("screening rejection artifact cannot permit advancement")
    return ScreeningRejectionDecision(document=document, decision_identity=identity)


def persist_screening_rejection_review(
    service: PersistenceService,
    *,
    run_id: str,
    review_reason: str,
    reviewer: str,
    artifact_root: str | Path,
) -> ScreeningRejectionDecision:
    artifacts = tuple(
        artifact
        for artifact in service.list_run_artifacts(run_id)
        if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )
    if len(artifacts) > 1:
        raise ValueError("multiple evidence decision artifacts are registered")
    if artifacts:
        if artifacts[0].schema_version != SCREENING_REJECTION_SCHEMA_VERSION:
            raise ValueError("conflicting evidence decision artifact already exists")
        existing = _read_screening_rejection_decision(
            service, artifacts[0], run_id=run_id, artifact_root=artifact_root
        )
        review = existing.document["decision"]["review"]
        if review == {
            "state": ReviewState.REJECT.value,
            "reason": review_reason,
            "reviewer": reviewer,
        }:
            return existing
        raise ValueError("conflicting evidence decision artifact already exists")
    context = _screening_rejection_context(
        service, run_id, artifact_root=artifact_root
    )
    with artifact_file_transaction() as files:
        with transaction(service.connection):
            review = service.update_review(
                target_type="run",
                target_id=run_id,
                state=ReviewState.REJECT,
                note=review_reason,
                operator=reviewer,
            )
            history = service.reviews.history("run", run_id)
            document: dict[str, Any] = {
                "schema_version": SCREENING_REJECTION_SCHEMA_VERSION,
                "artifact_kind": SCREENING_REJECTION_ARTIFACT_KIND,
                "created_at": utc_now(),
                "artifact": {
                    "logical_name": EVIDENCE_DECISION_LOGICAL_NAME,
                    "artifact_type": ArtifactType.VALIDATION_EVIDENCE.value,
                    "format": "json",
                    "schema_version": SCREENING_REJECTION_SCHEMA_VERSION,
                },
                "screening_context": context,
                "decision": {
                    "eligible_to_progress": False,
                    "review": {
                        "state": review.state.value,
                        "reason": review.note,
                        "reviewer": review.operator,
                    },
                    "audit_reference": history[-1] if history else None,
                },
            }
            document["artifact"]["decision_identity"] = (
                _screening_decision_identity(document)
            )
            content = canonical_json(document).encode("utf-8")
            location = f"artifacts/{run_id}/{EVIDENCE_DECISION_LOGICAL_NAME}.json"
            target = (Path(artifact_root).resolve() / location).resolve()
            target.relative_to(Path(artifact_root).resolve())
            files.write_bytes(target, content)
            artifact = service.register_artifact(
                run_id=run_id,
                artifact_type=ArtifactType.VALIDATION_EVIDENCE,
                logical_name=EVIDENCE_DECISION_LOGICAL_NAME,
                media_type="application/json",
                format="json",
                location=location,
                content=content,
                schema_version=SCREENING_REJECTION_SCHEMA_VERSION,
            )
            return _read_screening_rejection_decision(
                service, artifact, run_id=run_id, artifact_root=artifact_root
            )


def load_durable_review(
    database: str | Path,
    artifact_root: str | Path,
    run_id: str,
) -> DurableReviewSnapshot:
    """Load one review without trusting orphaned state or an invalid artifact."""

    service = PersistenceService(database)
    try:
        if service.runs.get(run_id) is None:
            raise KeyError(f"unknown run {run_id}")
        artifacts = tuple(
            artifact
            for artifact in service.list_run_artifacts(run_id)
            if artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
        )
        if len(artifacts) > 1:
            raise ValueError("multiple evidence decision artifacts are registered")

        current = service.reviews.get_current("run", run_id)
        history = service.reviews.history("run", run_id)
        if not artifacts:
            if current is not None or history:
                raise ValueError(
                    "durable review state exists without a validated evidence decision artifact"
                )
            return DurableReviewSnapshot(
                state=ReviewState.UNREVIEWED,
                note="",
                operator=None,
                updated_at=None,
                history=(),
                decision_identity=None,
            )

        if artifacts[0].schema_version == SCREENING_REJECTION_SCHEMA_VERSION:
            decision = _read_screening_rejection_decision(
                service,
                artifacts[0],
                run_id=run_id,
                artifact_root=artifact_root,
            )
        else:
            evidence = ValidationEvidenceArtifactService(service)
            gate = evidence.evaluate_persisted_review_context(
                run_id,
                artifact_root=artifact_root,
            )
            decision = evidence.retrieve_evidence_decision(
                run_id,
                artifact_root=artifact_root,
                expected_gate=gate,
            )
        review = decision.document["decision"]["review"]
        state = ReviewState(str(review["state"]))
        note = str(review.get("reason", ""))
        operator = str(review.get("reviewer", "")) or None
        if current is None:
            raise ValueError("validated evidence decision has no durable review state")
        if (
            current.state != state
            or current.note != note
            or current.operator != operator
        ):
            raise ValueError(
                "durable review state does not match the validated evidence decision"
            )
        if not history:
            raise ValueError("validated evidence decision has no audit history")
        latest = history[-1]
        if (
            latest.get("new_state") != state.value
            or latest.get("note") != note
            or latest.get("operator") != operator
        ):
            raise ValueError(
                "latest review audit event does not match the validated evidence decision"
            )
        return DurableReviewSnapshot(
            state=state,
            note=note,
            operator=operator,
            updated_at=str(latest.get("created_at") or current.updated_at),
            history=history,
            decision_identity=decision.decision_identity,
        )
    finally:
        service.close()
