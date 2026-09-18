"""Focused tests for durable evidence decision artifacts."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
    build_evidence_decision_document,
    evidence_decision_identity,
    retrieve_evidence_decision_artifact,
)
from backtesting.validation.lockbox_gate import (
    LockboxArtifactReference,
    LockboxGateResult,
    lockbox_gate_identity,
)
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    ReviewState,
    RunStage,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document


def _service_with_run(tmp_path: Path, *, run_id: str = "decision-run") -> PersistenceService:
    service = PersistenceService(tmp_path / "state.sqlite3")
    service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic decision fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="decision-artifact",
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            market_data={"symbol": "SPY", "provider": "fixture"},
            parameters={"fixture": True},
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "none"},
        )
    )
    service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        stage=RunStage.OOS,
        run_id=run_id,
    )
    with transaction(service.connection):
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=run_id,
                provider="fixture",
                provider_implementation="fixture-provider",
                symbol="SPY",
                interval="1 day",
                timezone="UTC",
                requested_coverage="2020-01-01",
                actual_coverage="2020-01-01..2020-01-10",
                adjusted=True,
                row_count=10,
                cache_action="fixture",
                validation_summary_json=canonical_json({"valid": True}),
                manifest_reference="data/manifests/fixture.json",
                checksum="dataset-checksum",
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=run_id,
                assumptions_json=canonical_json({"kind": "fixture"}),
            )
        )
    return service


def _reference_artifact(
    service: PersistenceService,
    *,
    root: Path,
    run_id: str = "decision-run",
    logical_name: str,
    evidence_identity: str,
) -> int:
    document = {"artifact": {"evidence_identity": evidence_identity}}
    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{logical_name}.json"
    target = root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=logical_name,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )
    return artifact.artifact_id


def _references(
    service: PersistenceService,
    *,
    root: Path,
    evidence_identity: str = "wf-evidence",
) -> tuple[LockboxArtifactReference, ...]:
    wf_id = _reference_artifact(
        service,
        root=root,
        logical_name="walk_forward_evidence",
        evidence_identity=evidence_identity,
    )
    mc_id = _reference_artifact(
        service,
        root=root,
        logical_name="monte_carlo_evidence",
        evidence_identity="mc-evidence",
    )
    rb_id = _reference_artifact(
        service,
        root=root,
        logical_name="robustness_evidence",
        evidence_identity="rb-evidence",
    )
    return (
        LockboxArtifactReference("out_of_sample", "source-lock-artifact", None),
        LockboxArtifactReference("walk_forward", str(wf_id), evidence_identity),
        LockboxArtifactReference("monte_carlo", str(mc_id), "mc-evidence"),
        LockboxArtifactReference("robustness", str(rb_id), "rb-evidence"),
    )


def _gate(
    references: tuple[LockboxArtifactReference, ...],
    *,
    status: str = "passed",
    reasons: tuple[str, ...] = ("gate reviewed",),
) -> LockboxGateResult:
    draft = LockboxGateResult(
        status=status,
        reasons=reasons,
        referenced_artifacts=references,
        parameter_lock_identity="parameter-lock-1",
        protected_data_state="gated",
        lineage_identity="lineage-1",
        gate_identity="",
        eligible_to_execute_lockbox=status == "passed",
        eligible_to_progress=False,
    )
    return replace(draft, gate_identity=lockbox_gate_identity(draft))


def _review(service: PersistenceService, *, state: ReviewState = ReviewState.REVISE):
    record = service.update_review(
        target_type="run",
        target_id="decision-run",
        state=state,
        note="human review note",
        operator="reviewer-1",
    )
    return record, service.reviews.history("run", "decision-run")[-1]


def _registered_decision(
    service: PersistenceService,
    *,
    root: Path,
    document: dict,
    run_id: str = "decision-run",
):
    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{EVIDENCE_DECISION_LOGICAL_NAME}.json"
    target = root / location
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
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return artifact


def _artifact_bytes(root: Path, artifact) -> bytes:
    return (root / artifact.location).read_bytes()


def _artifact_count(service: PersistenceService) -> int:
    return len(service.list_run_artifacts("decision-run"))


def _audit_count(service: PersistenceService) -> int:
    return len(service.reviews.history("run", "decision-run"))


def _recompute_gate_identity(document: dict) -> None:
    gate = document["decision"]["lockbox_gate"]
    references = tuple(
        LockboxArtifactReference(
            stage=reference["stage"],
            artifact_id=reference["artifact_id"],
            evidence_identity=reference["evidence_identity"],
        )
        for reference in gate["referenced_artifacts"]
    )
    draft = LockboxGateResult(
        status=gate["status"],
        reasons=tuple(gate["reasons"]),
        referenced_artifacts=references,
        parameter_lock_identity=gate["parameter_lock_identity"],
        protected_data_state=gate["protected_data_state"],
        lineage_identity=gate["lineage_identity"],
        gate_identity="",
        eligible_to_execute_lockbox=gate["eligible_to_execute_lockbox"],
        eligible_to_progress=gate["eligible_to_progress"],
    )
    gate["gate_identity"] = lockbox_gate_identity(draft)
    document["artifact"]["decision_identity"] = evidence_decision_identity(document)


@pytest.mark.parametrize("status", ["passed", "failed", "insufficient_evidence", "invalid"])
def test_decision_records_all_gate_statuses(tmp_path: Path, status: str) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    gate = _gate(_references(service, root=root), status=status)
    decision = ValidationEvidenceArtifactService(service).persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )

    assert decision.document["decision"]["lockbox_gate"]["status"] == status
    assert decision.document["decision"]["eligible_to_progress"] is False


@pytest.mark.parametrize(
    "state",
    [
        ReviewState.REJECT,
        ReviewState.REVISE,
        ReviewState.APPROVED_FOR_NEXT_EVIDENCE_STAGE,
    ],
)
def test_explicit_review_states_persist(tmp_path: Path, state: ReviewState) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    gate = _gate(_references(service, root=root))
    decision = ValidationEvidenceArtifactService(service).persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=state,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )

    assert decision.document["decision"]["review"]["state"] == state.value


def test_decision_identity_ignores_creation_timestamp(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)

    first = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
        created_at="2026-01-01T00:00:00+00:00",
    )
    second = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference={**audit, "audit_id": audit["audit_id"] + 1, "created_at": "2026-01-02T00:00:00+00:00"},
        created_at="2026-01-03T00:00:00+00:00",
    )

    assert first["artifact"]["decision_identity"] == second["artifact"]["decision_identity"]
    assert first["created_at"] != second["created_at"]


def test_decision_identity_changes_for_meaningful_inputs(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    review, audit = _review(service)
    references = _references(service, root=root)
    first = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=_gate(references, status="passed"),
        review=review,
        audit_reference=audit,
    )
    changed_gate = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=_gate(references, status="failed", reasons=("failed gate",)),
        review=review,
        audit_reference=audit,
    )
    changed_review = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=_gate(references),
        review=replace(review, state=ReviewState.REJECT),
        audit_reference=audit,
    )

    assert first["artifact"]["decision_identity"] != changed_gate["artifact"]["decision_identity"]
    assert first["artifact"]["decision_identity"] != changed_review["artifact"]["decision_identity"]


def test_decision_persists_retrieves_and_preserves_registry_link(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))

    persisted = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )
    retrieved = evidence.retrieve_evidence_decision(
        "decision-run",
        artifact_root=root,
        expected_gate=gate,
    )

    assert retrieved.artifact == persisted.artifact
    assert retrieved.decision_identity == persisted.decision_identity
    assert any(
        artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        for artifact in service.list_run_artifacts("decision-run")
    )


def test_decision_after_sealed_manifest_preserves_manifest_and_idempotency(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))
    service.persist_run_manifest(service.build_run_manifest("decision-run"))
    manifest_before = service.read_persisted_run_manifest("decision-run")
    artifact_count_before = _artifact_count(service)

    first = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
        created_at="2026-01-01T00:00:00+00:00",
    )
    manifest_after = service.read_persisted_run_manifest("decision-run")
    file_before = _artifact_bytes(root, first.artifact)
    audit_count = _audit_count(service)
    artifact_count = _artifact_count(service)
    review_before = service.reviews.get_current("run", "decision-run")

    assert manifest_after == manifest_before
    assert artifact_count == artifact_count_before + 1
    retrieval = service.retrieve_run_artifacts("decision-run", artifact_root=root)
    assert any(
        artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        for artifact in retrieval.artifacts
    )
    assert evidence.retrieve_evidence_decision(
        "decision-run",
        artifact_root=root,
        expected_gate=gate,
    ).decision_identity == first.decision_identity
    assert audit_count == 1
    assert review_before is not None

    second = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
        created_at="2026-01-02T00:00:00+00:00",
    )
    assert second.decision_identity == first.decision_identity
    assert service.read_persisted_run_manifest("decision-run") == manifest_before
    assert _artifact_bytes(root, first.artifact) == file_before
    assert _artifact_count(service) == artifact_count
    assert _audit_count(service) == audit_count
    assert service.reviews.get_current("run", "decision-run") == review_before

    with pytest.raises(ValueError, match="conflicting evidence decision artifact"):
        evidence.persist_evidence_decision(
            run_id="decision-run",
            gate_result=gate,
            review_state=ReviewState.REJECT,
            review_reason="different review note",
            reviewer="reviewer-1",
            artifact_root=root,
        )
    assert service.read_persisted_run_manifest("decision-run") == manifest_before
    assert _artifact_bytes(root, first.artifact) == file_before
    assert _artifact_count(service) == artifact_count
    assert _audit_count(service) == audit_count


def test_identical_retry_returns_existing_without_mutation(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))
    first = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
        created_at="2026-01-01T00:00:00+00:00",
    )
    manifest_before = service.read_persisted_run_manifest("decision-run")
    file_before = _artifact_bytes(root, first.artifact)
    artifact_count = _artifact_count(service)
    audit_count = _audit_count(service)
    review_before = service.reviews.get_current("run", "decision-run")

    second = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
        created_at="2026-01-02T00:00:00+00:00",
    )

    assert second.artifact == first.artifact
    assert second.decision_identity == first.decision_identity
    assert service.read_persisted_run_manifest("decision-run") == manifest_before
    assert _artifact_bytes(root, first.artifact) == file_before
    assert _artifact_count(service) == artifact_count
    assert _audit_count(service) == audit_count
    assert service.reviews.get_current("run", "decision-run") == review_before


def test_conflicting_retry_fails_without_mutation_and_original_retrieves(
    tmp_path: Path,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))
    first = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )
    manifest_before = service.read_persisted_run_manifest("decision-run")
    file_before = _artifact_bytes(root, first.artifact)
    artifact_count = _artifact_count(service)
    audit_count = _audit_count(service)
    review_before = service.reviews.get_current("run", "decision-run")

    with pytest.raises(ValueError, match="conflicting evidence decision artifact"):
        evidence.persist_evidence_decision(
            run_id="decision-run",
            gate_result=gate,
            review_state=ReviewState.REJECT,
            review_reason="different review note",
            reviewer="reviewer-1",
            artifact_root=root,
        )

    assert service.read_persisted_run_manifest("decision-run") == manifest_before
    assert _artifact_bytes(root, first.artifact) == file_before
    assert _artifact_count(service) == artifact_count
    assert _audit_count(service) == audit_count
    assert service.reviews.get_current("run", "decision-run") == review_before
    retrieved = evidence.retrieve_evidence_decision(
        "decision-run",
        artifact_root=root,
        expected_gate=gate,
    )
    assert retrieved.decision_identity == first.decision_identity


def test_corrupt_decision_artifact_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))
    persisted = evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )
    (root / persisted.artifact.location).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="unavailable|mismatch"):
        evidence.retrieve_evidence_decision(
            "decision-run",
            artifact_root=root,
            expected_gate=gate,
        )


def test_changed_referenced_evidence_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    references = _references(service, root=root)
    gate = _gate(references)
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )
    changed = {"artifact": {"evidence_identity": "changed"}}
    wf_artifact = service.get_artifact_metadata(int(references[1].artifact_id))
    (root / wf_artifact.location).write_text(canonical_json(changed), encoding="utf-8")

    with pytest.raises(ValueError, match="referenced evidence artifact is unavailable"):
        evidence.retrieve_evidence_decision(
            "decision-run",
            artifact_root=root,
            expected_gate=gate,
        )


def test_missing_referenced_evidence_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    references = _references(service, root=root)
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=_gate(references),
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )
    wf_artifact = service.get_artifact_metadata(int(references[1].artifact_id))
    (root / wf_artifact.location).unlink()

    with pytest.raises(ValueError, match="referenced evidence artifact is unavailable"):
        evidence.retrieve_evidence_decision(
            "decision-run",
            artifact_root=root,
            expected_gate=_gate(references),
        )


def test_gate_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    references = _references(service, root=root)
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=_gate(references),
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )

    with pytest.raises(ValueError, match="lockbox gate identity mismatch"):
        evidence.retrieve_evidence_decision(
            "decision-run",
            artifact_root=root,
            expected_gate=_gate(references, status="failed", reasons=("changed",)),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda document: document.update({"schema_version": 99}), "schema version"),
        (
            lambda document: document["artifact"].update({"schema_version": 99}),
            "embedded schema version",
        ),
        (lambda document: document.update({"created_at": "not-a-time"}), "created_at"),
        (
            lambda document: document.update({"created_at": "2026-01-01T00:00:00"}),
            "timezone offset",
        ),
    ],
)
def test_schema_or_timestamp_corruption_fails_closed(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    mutation(document)
    if "created_at" in message or "timezone" in message:
        document["artifact"]["decision_identity"] = evidence_decision_identity(document)
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=message):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("not-a-time", "review audit created_at"),
        ("2026-01-01T00:00:00", "timezone offset"),
    ],
)
def test_invalid_or_naive_audit_timestamp_fails_closed(
    tmp_path: Path,
    value: str,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference={**audit, "created_at": value},
    )
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=message):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize("audit_id", [None, "1", 0, -1])
def test_missing_or_invalid_audit_id_fails_closed(
    tmp_path: Path,
    audit_id: object,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    audit_reference = dict(audit)
    if audit_id is None:
        audit_reference.pop("audit_id")
    else:
        audit_reference["audit_id"] = audit_id
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit_reference,
    )
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match="review audit_id"):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document: document["decision"]["lockbox_gate"].update(
                {"reasons": ["changed reason"]}
            ),
            "stored lockbox gate identity mismatch",
        ),
        (
            lambda document: document["decision"]["lockbox_gate"].update(
                {"eligible_to_execute_lockbox": False}
            ),
            "lockbox gate identity mismatch",
        ),
    ],
)
def test_inconsistent_gate_identity_or_fields_fail_closed(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    mutation(document)
    if message == "lockbox gate identity mismatch":
        _recompute_gate_identity(document)
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=message):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize("reason", [None, 123, {"reason": "bad"}])
def test_malformed_gate_reason_entries_fail_closed(
    tmp_path: Path,
    reason: object,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    document["decision"]["lockbox_gate"]["reasons"] = [reason]
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match="lockbox gate reason is malformed"):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize("field", ["parameter_lock_identity", "lineage_identity"])
@pytest.mark.parametrize("value", ["", "   ", 123])
def test_malformed_optional_gate_identities_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    document["decision"]["lockbox_gate"][field] = value
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=field):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda document: document["decision"]["review"]["audit_reference"].update(
                {"note": "different"}
            ),
            "review audit note mismatch",
        ),
        (
            lambda document: document["decision"]["review"].update(
                {"audit_reference": None}
            ),
            "review audit reference is missing",
        ),
    ],
)
def test_review_audit_mismatch_or_missing_reference_fails_closed(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    mutation(document)
    document["artifact"]["decision_identity"] = evidence_decision_identity(document)
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=message):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


def test_oos_reference_mismatch_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    references = _references(service, root=root)
    gate = _gate(references)
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    document["decision"]["lockbox_gate"]["referenced_artifacts"] = [
        reference
        for reference in document["decision"]["lockbox_gate"]["referenced_artifacts"]
        if reference["stage"] != "out_of_sample"
    ]
    document["artifact"]["decision_identity"] = evidence_decision_identity(document)
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match="exactly one out-of-sample reference"):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


def test_retrieval_without_expected_gate_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    evidence = ValidationEvidenceArtifactService(service)
    gate = _gate(_references(service, root=root))
    evidence.persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.REVISE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )

    with pytest.raises(ValueError, match="expected lockbox gate is required"):
        evidence.retrieve_evidence_decision("decision-run", artifact_root=root)


def test_referenced_evidence_metadata_mismatch_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    wf_id = _reference_artifact(
        service,
        root=root,
        logical_name="walk_forward_evidence",
        evidence_identity="wf-evidence",
    )
    mc_id = _reference_artifact(
        service,
        root=root,
        logical_name="monte_carlo_evidence",
        evidence_identity="mc-evidence",
    )
    rb_id = _reference_artifact(
        service,
        root=root,
        logical_name="robustness_evidence",
        evidence_identity="rb-evidence",
    )
    references = (
        LockboxArtifactReference("out_of_sample", "source-lock-artifact", None),
        LockboxArtifactReference("walk_forward", str(mc_id), "mc-evidence"),
        LockboxArtifactReference("monte_carlo", str(mc_id), "mc-evidence"),
        LockboxArtifactReference("robustness", str(rb_id), "rb-evidence"),
    )
    # Keep the real walk-forward artifact registered so the manifest remains normal;
    # the decision record itself points the walk-forward slot at Monte Carlo metadata.
    assert wf_id != mc_id
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(references)
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match="referenced evidence artifact stage mismatch"):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("state", "bogus", "review state is unsupported"),
        ("eligible_to_progress", True, "cannot be eligible to progress"),
        ("protected_data_state", "spent", "stored lockbox gate identity mismatch"),
    ],
)
def test_corrupt_review_or_protected_fields_fail_closed(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    references = _references(service, root=root)
    gate = _gate(references)
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    if field == "state":
        document["decision"]["review"]["state"] = value
    elif field == "eligible_to_progress":
        document["decision"]["eligible_to_progress"] = value
    else:
        document["decision"]["lockbox_gate"]["protected_data_state"] = value
    document["artifact"]["decision_identity"] = "precomputed-corrupt"
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match=message):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


def test_source_lineage_mismatch_fails_closed(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    source = ValidationEvidenceArtifactService(service).source_document("decision-run")
    gate = _gate(_references(service, root=root))
    review, audit = _review(service)
    document = build_evidence_decision_document(
        run_id="decision-run",
        source=source,
        gate_result=gate,
        review=review,
        audit_reference=audit,
    )
    document["source"]["strategy_version"] = "changed"
    document["artifact"]["decision_identity"] = evidence_decision_identity(document)
    _registered_decision(service, root=root, document=document)

    with pytest.raises(ValueError, match="source lineage mismatch"):
        retrieve_evidence_decision_artifact(
            service=service,
            run_id="decision-run",
            artifact_root=root,
            expected_source=source,
            expected_gate=gate,
        )


def test_decision_record_does_not_execute_or_promote(tmp_path: Path) -> None:
    service = _service_with_run(tmp_path)
    root = tmp_path / "artifacts"
    run_before = service.runs.get("decision-run")
    strategy_before = service.strategies.get("fixture_strategy", "1.0.0")
    gate = _gate(_references(service, root=root))

    decision = ValidationEvidenceArtifactService(service).persist_evidence_decision(
        run_id="decision-run",
        gate_result=gate,
        review_state=ReviewState.APPROVED_FOR_NEXT_EVIDENCE_STAGE,
        review_reason="human review note",
        reviewer="reviewer-1",
        artifact_root=root,
    )

    assert decision.document["decision"]["eligible_to_progress"] is False
    assert service.runs.get("decision-run") == run_before
    assert service.strategies.get("fixture_strategy", "1.0.0") == strategy_before
