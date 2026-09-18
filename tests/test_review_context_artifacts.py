"""Focused tests for persisted review-context artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from backtesting.validation.review_context_artifacts import REVIEW_CONTEXT_LOGICAL_NAME
from persistence import ArtifactType, PersistenceService, RunStage, StrategyLifecycle
from persistence import DataProvenanceRecord, ExecutionAssumptionsRecord, canonical_json
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from tests.test_lockbox_gate import _persist_prerequisites, _service
from tools import persist_review_context as persist_review_context_cli

REVIEW_EXPERIMENT_ID = "lockbox-gate"
REVIEW_STRATEGY_ID = "rsi_mean_reversion"
REVIEW_STRATEGY_VERSION = "1.0.0"
REVIEW_PARAMETERS = {
    "window": 14,
    "entry_threshold": 30,
    "exit_threshold": 55,
}


def _review_service(tmp_path: Path) -> PersistenceService:
    return _service(
        tmp_path,
        experiment_id=REVIEW_EXPERIMENT_ID,
        strategy_id=REVIEW_STRATEGY_ID,
        strategy_version=REVIEW_STRATEGY_VERSION,
        parameters=REVIEW_PARAMETERS,
    )


def _persist_review_prerequisites(
    service: PersistenceService,
    root: Path,
) -> None:
    _persist_prerequisites(
        service,
        root,
        experiment_id=REVIEW_EXPERIMENT_ID,
        strategy_id=REVIEW_STRATEGY_ID,
        strategy_version=REVIEW_STRATEGY_VERSION,
        parameters=REVIEW_PARAMETERS,
    )


def _target_run(service: PersistenceService, run_id: str = "review-target") -> str:
    source = service.runs.get("wf-run")
    assert source is not None
    service.create_run(
        configuration_id=source.configuration_id,
        strategy_id=source.strategy_id,
        strategy_version=source.strategy_version,
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
                actual_coverage="2020-01-01..2020-04-30",
                adjusted=True,
                row_count=120,
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
    return run_id


def _source_lock_artifact(
    service: PersistenceService,
    root: Path,
    *,
    run_id: str = "review-target",
    artifact_id: str = "source-artifact-1",
    storage_key: str | None = None,
    locked_parameters: dict[str, object] | None = None,
    strategy_id: str = REVIEW_STRATEGY_ID,
    strategy_version: str = REVIEW_STRATEGY_VERSION,
    experiment_id: str = REVIEW_EXPERIMENT_ID,
    data_provenance: dict[str, object] | None = None,
    execution_assumptions: dict[str, object] | None = None,
    source_start: str = "2020-01-01",
    source_end: str = "2020-04-30",
) -> int:
    payload = {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": artifact_id,
        "experiment_id": experiment_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "source_start": source_start,
        "source_end": source_end,
        "data_provenance": data_provenance or {"provider": "fixture"},
        "execution_assumptions": execution_assumptions or {"kind": "fixture"},
        "parameter_lock": {
            "lock_id": "parameter-lock-1",
            "normalized_parameters": locked_parameters or REVIEW_PARAMETERS,
        },
        "selection_status": "passed",
        "test_status": "passed",
        "metrics": {
            "total_return": 0.1,
            "max_drawdown": -0.03,
            "number_of_trades": 5,
        },
    }
    content = canonical_json(payload).encode("utf-8")
    key = storage_key or artifact_id
    location = f"artifacts/{run_id}/source_lock_{key}.json"
    path = root / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=f"source_lock_evidence:{key}",
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=1,
    )
    return artifact.artifact_id


def _persist_context(
    service: PersistenceService,
    root: Path,
    *,
    target_run_id: str = "review-target",
    source_lock_artifact_id: int | None = None,
    source_lock_run_id: str = "review-target",
):
    artifact_id = source_lock_artifact_id or _source_lock_artifact(
        service,
        root,
        run_id=source_lock_run_id,
    )
    return ValidationEvidenceArtifactService(service).persist_review_context(
        target_run_id=target_run_id,
        source_lock_run_id=source_lock_run_id,
        source_lock_artifact_id=artifact_id,
        walk_forward_run_id="wf-run",
        monte_carlo_run_id="mc-run",
        robustness_run_id="robust-run",
        protected_data_state="gated",
        artifact_root=root,
        created_at="2026-01-01T00:00:00+00:00",
    )


def test_review_context_fixture_envelope_uses_effective_strategy_parameters() -> None:
    assert ValidationEvidenceArtifactService._effective_strategy_parameters(
        {
            "fixture": "spym_databento_rsi_vectorbt_21c",
            "strategy_parameters": {"window": 14, "entry_threshold": 30},
        }
    ) == {"window": 14, "entry_threshold": 30}


def test_review_context_flat_parameters_remain_compatible() -> None:
    assert ValidationEvidenceArtifactService._effective_strategy_parameters(
        REVIEW_PARAMETERS
    ) == REVIEW_PARAMETERS


@pytest.mark.parametrize(
    "parameters",
    (
        {"fixture": "spym_databento_rsi_vectorbt_21c"},
        {"strategy_parameters": {"window": 14}},
        {
            "fixture": "spym_databento_rsi_vectorbt_21c",
            "strategy_parameters": {"window": 14},
            "unexpected": True,
        },
        {"fixture": "", "strategy_parameters": {"window": 14}},
        {
            "fixture": "spym_databento_rsi_vectorbt_21c",
            "strategy_parameters": {},
        },
    ),
)
def test_review_context_malformed_parameter_envelopes_fail_closed(
    parameters: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="fixture parameter envelope|fixture strategy parameters"):
        ValidationEvidenceArtifactService._effective_strategy_parameters(parameters)


def test_review_context_persists_retrieves_and_evaluates_explicit_context(
    tmp_path: Path,
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)

    persisted = _persist_context(service, root)
    evidence = ValidationEvidenceArtifactService(service)
    retrieved = evidence.retrieve_review_context("review-target", artifact_root=root)
    gate = evidence.evaluate_persisted_review_context(
        "review-target",
        artifact_root=root,
    )

    assert retrieved.context_identity == persisted.context_identity
    assert gate.status == "passed"
    assert any(
        artifact.logical_name == REVIEW_CONTEXT_LOGICAL_NAME
        for artifact in service.list_run_artifacts("review-target")
    )


def test_review_context_operator_cli_invokes_service_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    artifact_id = _source_lock_artifact(service, root)
    service.close()

    exit_code = persist_review_context_cli.main(
        [
            "--database",
            str(tmp_path / "state.sqlite3"),
            "--artifact-root",
            str(root),
            "--target-run-id",
            "review-target",
            "--source-lock-run-id",
            "review-target",
            "--source-lock-artifact-id",
            str(artifact_id),
            "--walk-forward-run-id",
            "wf-run",
            "--monte-carlo-run-id",
            "mc-run",
            "--robustness-run-id",
            "robust-run",
            "--protected-data-state",
            "gated",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip()
    reopened = PersistenceService(tmp_path / "state.sqlite3")
    try:
        assert any(
            artifact.logical_name == REVIEW_CONTEXT_LOGICAL_NAME
            for artifact in reopened.list_run_artifacts("review-target")
        )
    finally:
        reopened.close()


def test_review_context_after_sealed_manifest_is_idempotent_and_conflict_safe(
    tmp_path: Path,
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    source_artifact_id = _source_lock_artifact(service, root)
    service.persist_run_manifest(service.build_run_manifest("review-target"))
    manifest_before = service.read_persisted_run_manifest("review-target")
    artifact_count_before = len(service.list_run_artifacts("review-target"))

    first = _persist_context(
        service,
        root,
        source_lock_artifact_id=source_artifact_id,
    )
    artifact_count = len(service.list_run_artifacts("review-target"))
    manifest_after = service.read_persisted_run_manifest("review-target")

    assert manifest_after == manifest_before
    assert artifact_count == artifact_count_before + 1
    assert service.retrieve_run_artifacts("review-target", artifact_root=root)

    second = _persist_context(
        service,
        root,
        source_lock_artifact_id=source_artifact_id,
    )
    assert second.context_identity == first.context_identity
    assert service.read_persisted_run_manifest("review-target") == manifest_before
    assert len(service.list_run_artifacts("review-target")) == artifact_count
    assert service.reviews.history("run", "review-target") == ()

    conflicting = _source_lock_artifact(
        service,
        root,
        run_id="review-target",
        storage_key="source-artifact-conflict",
    )
    artifact_count_with_conflicting_input = len(service.list_run_artifacts("review-target"))
    with pytest.raises(ValueError, match="conflicting review context artifact"):
        _persist_context(service, root, source_lock_artifact_id=conflicting)
    assert service.read_persisted_run_manifest("review-target") == manifest_before
    assert (
        len(service.list_run_artifacts("review-target"))
        == artifact_count_with_conflicting_input
    )
    assert service.reviews.history("run", "review-target") == ()


def test_review_context_missing_referenced_run_fails_closed(tmp_path: Path) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)

    with pytest.raises(KeyError, match="unknown run missing-wf"):
        ValidationEvidenceArtifactService(service).persist_review_context(
            target_run_id="review-target",
            source_lock_run_id="review-target",
            source_lock_artifact_id=_source_lock_artifact(service, root),
            walk_forward_run_id="missing-wf",
            monte_carlo_run_id="mc-run",
            robustness_run_id="robust-run",
            protected_data_state="gated",
            artifact_root=root,
        )


def test_review_context_parameter_lock_mismatch_fails_before_mutation(
    tmp_path: Path,
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    artifact_id = _source_lock_artifact(
        service,
        root,
        locked_parameters={"window": 99},
    )

    before = tuple(service.list_run_artifacts("review-target"))
    with pytest.raises(ValueError, match="locked parameters are invalid|parameter lock"):
        _persist_context(
            service,
            root,
            source_lock_artifact_id=artifact_id,
        )
    assert tuple(service.list_run_artifacts("review-target")) == before


def test_review_context_rejects_fabricated_source_lock_boundary() -> None:
    import inspect

    signature = inspect.signature(
        ValidationEvidenceArtifactService.persist_review_context
    )

    assert "source_lock" not in signature.parameters
    assert "source_lock_artifact_id" in signature.parameters
    assert "source_lock_run_id" in signature.parameters


def test_review_context_source_artifact_checksum_is_validated(tmp_path: Path) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    artifact_id = _source_lock_artifact(service, root)
    artifact = service.get_artifact_metadata(artifact_id)
    (root / artifact.location).write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="source-lock artifact is unavailable"):
        _persist_context(service, root, source_lock_artifact_id=artifact_id)
    assert len(service.list_run_artifacts("review-target")) == 1


@pytest.mark.parametrize(
    ("run_kwargs", "strategy_record", "expected"),
    (
        (
            {"strategy_id": "other_strategy"},
            ("other_strategy", REVIEW_STRATEGY_VERSION),
            "target strategy identity mismatches saved configuration",
        ),
        (
            {"strategy_version": "2.0.0"},
            (REVIEW_STRATEGY_ID, "2.0.0"),
            "target strategy identity mismatches saved configuration",
        ),
    ),
)
def test_review_context_target_strategy_mismatch_fails_before_mutation(
    tmp_path: Path,
    run_kwargs: dict[str, str],
    strategy_record: tuple[str, str],
    expected: str,
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    artifact_id = _source_lock_artifact(service, root)
    service.register_strategy(
        strategy_id=strategy_record[0],
        strategy_version=strategy_record[1],
        display_name="Mismatched Strategy",
        description="Review-context mismatch fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    with transaction(service.connection):
        assignments = ", ".join(f"{name}=?" for name in run_kwargs)
        service.connection.execute(
            f"UPDATE experiment_runs SET {assignments} WHERE run_id=?",
            (*run_kwargs.values(), "review-target"),
        )
    before = tuple(service.list_run_artifacts("review-target"))

    with pytest.raises(ValueError, match=expected):
        _persist_context(service, root, source_lock_artifact_id=artifact_id)
    assert tuple(service.list_run_artifacts("review-target")) == before


def test_review_context_target_lineage_mismatch_fails_before_mutation(
    tmp_path: Path,
) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    artifact_id = _source_lock_artifact(service, root)
    with transaction(service.connection):
        service.connection.execute(
            "UPDATE data_provenance SET checksum=? WHERE run_id=?",
            ("different-dataset", "review-target"),
        )
    before = tuple(service.list_run_artifacts("review-target"))

    with pytest.raises(ValueError, match="source lineage mismatch"):
        _persist_context(service, root, source_lock_artifact_id=artifact_id)
    assert tuple(service.list_run_artifacts("review-target")) == before


def test_corrupt_review_context_fails_closed(tmp_path: Path) -> None:
    service = _review_service(tmp_path)
    root = tmp_path / "artifacts"
    _persist_review_prerequisites(service, root)
    _target_run(service)
    persisted = _persist_context(service, root)
    (root / persisted.artifact.location).write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="review context artifact is unavailable"):
        ValidationEvidenceArtifactService(service).retrieve_review_context(
            "review-target",
            artifact_root=root,
        )
