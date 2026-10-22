"""Focused tests for the Milestone 22D-1 lockbox prerequisite gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.robustness.models import SourceLockEvidence
from backtesting.validation import evaluate_lockbox_prerequisites
from persistence import DataProvenanceRecord, canonical_json
from persistence.database import transaction
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
from tests.lockbox_gate_fixtures import (
    _service,
    _rules,
    _walk_forward_result,
    _monte_carlo_result,
    _robustness_result,
    _source_lock,
    _persist_prerequisites,
    _gate,
)


# Gate scoring runs the Monte Carlo metrics on the real engine.
pytestmark = pytest.mark.licensed_vectorbt


def test_valid_prerequisites_produce_executable_gated_result(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)

        result = _gate(service, root)

        assert result.status == "passed"
        assert result.reasons == ()
        assert result.protected_data_state == "gated"
        assert result.parameter_lock_identity == "parameter-lock-1"
        assert result.lineage_identity
        assert result.eligible_to_execute_lockbox is True
        assert result.eligible_to_progress is False
        assert {reference.stage for reference in result.referenced_artifacts} == {
            "out_of_sample",
            "walk_forward",
            "monte_carlo",
            "robustness",
        }
        assert (
            next(
                reference
                for reference in result.referenced_artifacts
                if reference.stage == "out_of_sample"
            ).artifact_id
            == "source-artifact-1"
        )
    finally:
        service.close()


def test_missing_artifact_is_insufficient_evidence(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        evidence.persist_walk_forward(
            run_id="wf-run",
            result=_walk_forward_result(),
            rules=_rules(),
            artifact_root=root,
        )
        evidence.persist_robustness(
            run_id="robust-run",
            result=_robustness_result(),
            artifact_root=root,
        )

        result = _gate(service, root)

        assert result.status == "insufficient_evidence"
        assert result.eligible_to_execute_lockbox is False
        assert any("no persisted manifest" in reason for reason in result.reasons)
        assert "monte_carlo" not in {
            reference.stage for reference in result.referenced_artifacts
        }
    finally:
        service.close()


def test_missing_walk_forward_artifact_is_insufficient_not_invalid(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        evidence.persist_monte_carlo(
            run_id="mc-run",
            result=_monte_carlo_result(),
            artifact_root=root,
        )
        evidence.persist_robustness(
            run_id="robust-run",
            result=_robustness_result(),
            artifact_root=root,
        )

        result = _gate(service, root)

        assert result.status == "insufficient_evidence"
        assert result.eligible_to_execute_lockbox is False
        assert any("wf-run has no persisted manifest" in reason for reason in result.reasons)
        assert "walk_forward" not in {
            reference.stage for reference in result.referenced_artifacts
        }
    finally:
        service.close()


def test_corrupt_artifact_is_invalid(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)
        path = root / "artifacts/mc-run/monte_carlo_evidence.json"
        path.write_text("{}", encoding="utf-8")

        result = _gate(service, root)

        assert result.status == "invalid"
        assert result.eligible_to_execute_lockbox is False
        assert any("mismatch" in reason for reason in result.reasons)
    finally:
        service.close()


def test_malformed_existing_artifact_missing_required_field_is_invalid(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)
        path = root / "artifacts/wf-run/walk_forward_evidence.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        del document["evidence"]["folds"][0]["fold_id"]
        path.write_text(canonical_json(document), encoding="utf-8")

        result = _gate(service, root)

        assert result.status == "invalid"
        assert result.eligible_to_execute_lockbox is False
        assert any("walk_forward:" in reason for reason in result.reasons)
    finally:
        service.close()


def test_lineage_mismatch_is_invalid(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        with transaction(service.connection):
            service.connection.execute(
                "DELETE FROM data_provenance WHERE run_id=?",
                ("robust-run",),
            )
            service.results.set_data_provenance(
                DataProvenanceRecord(
                    run_id="robust-run",
                    provider="fixture",
                    provider_implementation="fixture-provider",
                    symbol="QQQ",
                    interval="1 day",
                    timezone="UTC",
                    requested_coverage="2020-01-01",
                    actual_coverage="2020-01-01..2020-04-30",
                    adjusted=True,
                    row_count=120,
                    cache_action="fixture",
                    validation_summary_json=canonical_json({"valid": True}),
                    manifest_reference="data/manifests/fixture.json",
                    checksum="different-dataset-checksum",
                )
            )
        _persist_prerequisites(service, root)

        result = _gate(service, root)

        assert result.status == "invalid"
        assert any("source lineage mismatch" in reason for reason in result.reasons)
    finally:
        service.close()


def test_parameter_lock_mismatch_is_invalid(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(
            service,
            root,
            robust_parameters={"window": 21},
        )

        result = _gate(service, root)

        assert result.status == "invalid"
        assert any("locked_parameters mismatch" in reason for reason in result.reasons)
    finally:
        service.close()


def test_matching_walk_forward_fold_locks_pass(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(
            service,
            root,
            wf_lock_ids=("parameter-lock-1", "parameter-lock-1"),
        )

        result = _gate(service, root)

        assert result.status == "passed"
        assert result.parameter_lock_identity == "parameter-lock-1"
        assert result.eligible_to_execute_lockbox is True
    finally:
        service.close()


def test_different_valid_walk_forward_fold_locks_pass(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(
            service,
            root,
            wf_lock_ids=("fold-lock-1", "fold-lock-2"),
        )

        result = _gate(service, root)

        assert result.status == "passed"
        assert result.parameter_lock_identity == "parameter-lock-1"
        assert result.eligible_to_execute_lockbox is True
    finally:
        service.close()


def test_missing_walk_forward_fold_lock_fails_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)
        evidence = ValidationEvidenceArtifactService(service)
        walk_forward = evidence.retrieve_walk_forward("wf-run", artifact_root=root)
        monte_carlo = evidence.retrieve_monte_carlo("mc-run", artifact_root=root)
        robustness = evidence.retrieve_robustness("robust-run", artifact_root=root)
        walk_forward.document["evidence"]["folds"][0]["parameter_lock_id"] = None

        result = evaluate_lockbox_prerequisites(
            walk_forward=walk_forward,
            monte_carlo=monte_carlo,
            robustness=robustness,
            source_lock=_source_lock(),
            protected_data_state="gated",
        )

        assert result.status == "invalid"
        assert result.eligible_to_execute_lockbox is False
        assert any("parameter-lock identity is missing" in reason for reason in result.reasons)
    finally:
        service.close()


def test_failed_walk_forward_is_a_recorded_score_not_a_gate(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, wf_failed=True)

        result = _gate(service, root)

        assert result.status == "passed"
        assert result.eligible_to_execute_lockbox is True
        assert any("walk_forward (score): fold_001: selection failed" in reason for reason in result.reasons)
        assert not any("parameter-lock identity is missing" in reason for reason in result.reasons)
    finally:
        service.close()


@pytest.mark.parametrize(
    ("source_lock", "expected_reason"),
    (
        (
            _source_lock(experiment_id="other-experiment"),
            "source-lock experiment_id mismatch",
        ),
        (
            _source_lock(strategy_id="other_strategy"),
            "source-lock strategy_id mismatch",
        ),
        (
            _source_lock(strategy_version="2.0.0"),
            "source-lock strategy_version mismatch",
        ),
        (
            _source_lock(data_provenance={"provider": "other"}),
            "source-lock data_provenance mismatch",
        ),
        (
            _source_lock(execution_assumptions={"kind": "other"}),
            "source-lock execution_assumptions mismatch",
        ),
    ),
)
def test_source_lock_overlap_mismatch_fails_closed(
    tmp_path: Path,
    source_lock: SourceLockEvidence,
    expected_reason: str,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)

        result = _gate(service, root, source_lock=source_lock)

        assert result.status == "invalid"
        assert result.eligible_to_execute_lockbox is False
        assert any(expected_reason in reason for reason in result.reasons)
    finally:
        service.close()


def test_failed_monte_carlo_is_a_recorded_score_not_a_gate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, mc_status="failed")

        result = _gate(service, root)

        assert result.status == "passed"
        assert result.eligible_to_execute_lockbox is True
        assert any(reason.startswith("monte_carlo (score):") for reason in result.reasons)
    finally:
        service.close()


def test_insufficient_prerequisite_remains_distinct(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, robust_status="insufficient_evidence")

        result = _gate(service, root)

        assert result.status == "insufficient_evidence"
        assert result.eligible_to_execute_lockbox is False
        assert any(reason.startswith("robustness:") for reason in result.reasons)
    finally:
        service.close()


@pytest.mark.parametrize(
    ("protected_data_state", "expected_status"),
    (("spent", "failed"), ("invalid", "invalid"), ("mystery", "invalid")),
)
def test_invalid_or_spent_protected_state_fails_closed(
    tmp_path: Path,
    protected_data_state: object,
    expected_status: str,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root)

        result = _gate(
            service,
            root,
            protected_data_state=protected_data_state,
        )

        assert result.status == expected_status
        assert result.eligible_to_execute_lockbox is False
        assert result.eligible_to_progress is False
    finally:
        service.close()


def test_gate_identity_is_deterministic_and_changes_with_evidence(
    tmp_path: Path,
) -> None:
    first_service = _service(tmp_path / "first")
    second_service = _service(tmp_path / "second")
    changed_service = _service(tmp_path / "changed")
    try:
        _persist_prerequisites(first_service, tmp_path / "first-artifacts")
        _persist_prerequisites(second_service, tmp_path / "second-artifacts")
        _persist_prerequisites(
            changed_service,
            tmp_path / "changed-artifacts",
            mc_values=(0.04, 0.03, 0.02, 0.005),
        )

        first = _gate(first_service, tmp_path / "first-artifacts")
        second = _gate(second_service, tmp_path / "second-artifacts")
        changed = _gate(changed_service, tmp_path / "changed-artifacts")

        assert first.gate_identity == second.gate_identity
        assert first.gate_identity != changed.gate_identity
    finally:
        first_service.close()
        second_service.close()
        changed_service.close()


def test_source_lock_lineage_changes_gate_identity(tmp_path: Path) -> None:
    first_service = _service(tmp_path / "first-source")
    second_service = _service(tmp_path / "second-source")
    try:
        _persist_prerequisites(first_service, tmp_path / "first-source-artifacts")
        _persist_prerequisites(second_service, tmp_path / "second-source-artifacts")

        first = _gate(first_service, tmp_path / "first-source-artifacts")
        changed = _gate(
            second_service,
            tmp_path / "second-source-artifacts",
            source_lock=_source_lock(parameter_lock_id="parameter-lock-2"),
        )

        assert first.status == "passed"
        assert changed.status == "passed"
        assert first.gate_identity != changed.gate_identity
    finally:
        first_service.close()
        second_service.close()


def test_retrieval_failure_changes_gate_identity_and_adds_no_fake_reference(
    tmp_path: Path,
) -> None:
    valid_service = _service(tmp_path / "valid")
    missing_service = _service(tmp_path / "missing")
    try:
        _persist_prerequisites(valid_service, tmp_path / "valid-artifacts")
        evidence = ValidationEvidenceArtifactService(missing_service)
        evidence.persist_walk_forward(
            run_id="wf-run",
            result=_walk_forward_result(),
            rules=_rules(),
            artifact_root=tmp_path / "missing-artifacts",
        )
        evidence.persist_robustness(
            run_id="robust-run",
            result=_robustness_result(),
            artifact_root=tmp_path / "missing-artifacts",
        )

        valid = _gate(valid_service, tmp_path / "valid-artifacts")
        missing = _gate(missing_service, tmp_path / "missing-artifacts")

        assert valid.gate_identity != missing.gate_identity
        assert "monte_carlo" not in {
            reference.stage for reference in missing.referenced_artifacts
        }
    finally:
        valid_service.close()
        missing_service.close()


def test_gate_does_not_execute_or_mutate_lockbox_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    source_lock = _source_lock()
    try:
        _persist_prerequisites(service, root)
        before_runs = tuple(run.run_id for run in service.runs.list())

        result = _gate(service, root, source_lock=source_lock)

        after_runs = tuple(run.run_id for run in service.runs.list())
        assert result.eligible_to_execute_lockbox is True
        assert result.protected_data_state == "gated"
        assert source_lock.status == "passed"
        assert before_runs == after_runs
    finally:
        service.close()
