"""Integrity-checked durable review state for dashboard callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from persistence import ArtifactType, PersistenceService, ReviewState
from persistence.evidence_service import ValidationEvidenceArtifactService


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
