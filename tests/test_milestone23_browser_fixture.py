"""Coverage for the public Milestone 23 browser acceptance fixture preparer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from persistence import PersistenceService, ReviewState, RunStage, RunStatus
from persistence.evidence_service import ValidationEvidenceArtifactService
from prefect_spike.fixture_flow import deterministic_fixture_body
from prefect_spike.milestone23_browser_fixture import (
    MONTE_CARLO_RUN_ID,
    ROBUSTNESS_RUN_ID,
    SOURCE_LOCK_LOGICAL_NAME,
    SOURCE_LOCK_RUN_ID,
    TARGET_RUN_ID,
    WALK_FORWARD_RUN_ID,
    prepare_milestone23_browser_fixture,
)
from prefect_spike.spym_vectorbt_fixture import (
    ensure_spym_21c_saved_configuration,
    spym_21c_saved_configuration_document,
)
from tools import prepare_milestone23_browser_fixture as browser_fixture_cli


def _launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def _persisted_snapshot(
    service: PersistenceService,
    root: Path,
    *,
    include_context: bool = True,
) -> dict[str, object]:
    run_ids = (
        TARGET_RUN_ID,
        SOURCE_LOCK_RUN_ID,
        WALK_FORWARD_RUN_ID,
        MONTE_CARLO_RUN_ID,
        ROBUSTNESS_RUN_ID,
    )
    runs = {
        run_id: (
            run.run_id,
            run.configuration_id,
            run.strategy_id,
            run.strategy_version,
            run.stage.value,
            run.status.value,
            run.attempt_count,
        )
        for run_id in run_ids
        if (run := service.runs.get(run_id)) is not None
    }
    artifacts = tuple(
        sorted(
            (
                artifact.artifact_id,
                artifact.run_id,
                artifact.logical_name,
                artifact.checksum,
                artifact.location,
            )
            for run_id in run_ids
            for artifact in service.list_run_artifacts(run_id)
        )
    )
    review = service.reviews.get_current("run", TARGET_RUN_ID)
    history = service.reviews.history("run", TARGET_RUN_ID)
    snapshot: dict[str, object] = {
        "runs": runs,
        "artifacts": artifacts,
        "review": None
        if review is None
        else (review.state.value, review.note, review.operator),
        "review_history": history,
        "evidence_decision_count": sum(
            artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            for artifact in service.list_run_artifacts(TARGET_RUN_ID)
        ),
    }
    if include_context:
        context = ValidationEvidenceArtifactService(service).retrieve_review_context(
            TARGET_RUN_ID,
            artifact_root=root,
        )
        snapshot["review_context_identity"] = context.context_identity
    return snapshot


def test_preparer_builds_valid_idempotent_acceptance_fixture(tmp_path: Path) -> None:
    database = tmp_path / "state" / "fixture.sqlite3"
    root = tmp_path / "artifacts"

    first = prepare_milestone23_browser_fixture(
        database=database,
        artifact_root=root,
        fixture_launcher=_launcher,
    )
    service = PersistenceService(database)
    try:
        before = _persisted_snapshot(service, root)
        assert before["review"] == (
            ReviewState.INFRASTRUCTURE_FIXTURE.value,
            "Milestone 21C deterministic SPYM VectorBT Pro fixture run.",
            "local-user",
        )
        assert before["evidence_decision_count"] == 0
    finally:
        service.close()
    second = prepare_milestone23_browser_fixture(
        database=database,
        artifact_root=root,
        fixture_launcher=_launcher,
    )

    assert second == first
    service = PersistenceService(database)
    try:
        assert _persisted_snapshot(service, root) == before
        target = service.runs.get(TARGET_RUN_ID)
        assert target is not None and target.status == RunStatus.SUCCEEDED
        assert target.stage == RunStage.FIXTURE
        for run_id, stage in (
            (SOURCE_LOCK_RUN_ID, RunStage.OOS),
            (WALK_FORWARD_RUN_ID, RunStage.WALK_FORWARD),
            (MONTE_CARLO_RUN_ID, RunStage.MONTE_CARLO),
            (ROBUSTNESS_RUN_ID, RunStage.ROBUSTNESS),
        ):
            run = service.runs.get(run_id)
            assert run is not None and run.stage == stage
            assert run.configuration_id == target.configuration_id
            assert run.strategy_id == target.strategy_id
            assert run.strategy_version == target.strategy_version
        gate = ValidationEvidenceArtifactService(service).evaluate_persisted_review_context(
            TARGET_RUN_ID,
            artifact_root=root,
        )
        assert gate.status == "passed"
        assert gate.eligible_to_execute_lockbox is True
        assert not any(
            artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
            for artifact in service.list_run_artifacts(TARGET_RUN_ID)
        )
        assert any(
            artifact.logical_name == SOURCE_LOCK_LOGICAL_NAME
            for artifact in service.list_run_artifacts(SOURCE_LOCK_RUN_ID)
        )
    finally:
        service.close()


def test_preparer_fails_closed_without_repairing_corrupt_source_lock(
    tmp_path: Path,
) -> None:
    database = tmp_path / "corrupt.sqlite3"
    root = tmp_path / "corrupt-artifacts"
    prepare_milestone23_browser_fixture(
        database=database,
        artifact_root=root,
        fixture_launcher=_launcher,
    )
    service = PersistenceService(database)
    try:
        before = _persisted_snapshot(service, root)
        source_artifact = next(
            artifact
            for artifact in service.list_run_artifacts(SOURCE_LOCK_RUN_ID)
            if artifact.logical_name == SOURCE_LOCK_LOGICAL_NAME
        )
        source_path = root / source_artifact.location
        source_path.write_bytes(b"{corrupt-source-lock")
        metadata_before = (
            source_artifact.artifact_id,
            source_artifact.checksum,
            source_artifact.location,
        )
    finally:
        service.close()

    with pytest.raises(
        (RuntimeError, ValueError),
        match="source-lock artifact is unavailable",
    ):
        prepare_milestone23_browser_fixture(
            database=database,
            artifact_root=root,
            fixture_launcher=_launcher,
        )

    service = PersistenceService(database)
    try:
        after = _persisted_snapshot(service, root, include_context=False)
        before_without_context = dict(before)
        before_without_context.pop("review_context_identity")
        assert after == before_without_context
        source_artifact = next(
            artifact
            for artifact in service.list_run_artifacts(SOURCE_LOCK_RUN_ID)
            if artifact.logical_name == SOURCE_LOCK_LOGICAL_NAME
        )
        assert (
            source_artifact.artifact_id,
            source_artifact.checksum,
            source_artifact.location,
        ) == metadata_before
        assert source_path.read_bytes() == b"{corrupt-source-lock"
    finally:
        service.close()


def test_preparer_fails_closed_for_partial_or_conflicting_fixture_state(
    tmp_path: Path,
) -> None:
    partial_database = tmp_path / "partial.sqlite3"
    partial = PersistenceService(partial_database)
    try:
        configuration_id = ensure_spym_21c_saved_configuration(partial)
        configuration = partial.configurations.get(configuration_id)
        assert configuration is not None
        partial.create_run(
            configuration_id=configuration_id,
            strategy_id=configuration.strategy_id,
            strategy_version=configuration.strategy_version,
            stage=RunStage.FIXTURE,
            run_id=TARGET_RUN_ID,
        )
    finally:
        partial.close()
    with pytest.raises(RuntimeError, match="partial"):
        prepare_milestone23_browser_fixture(
            database=partial_database,
            artifact_root=tmp_path / "partial-artifacts",
            fixture_launcher=_launcher,
        )

    conflict_database = tmp_path / "conflict.sqlite3"
    prepare_milestone23_browser_fixture(
        database=conflict_database,
        artifact_root=tmp_path / "conflict-artifacts",
        fixture_launcher=_launcher,
    )
    conflict = PersistenceService(conflict_database)
    try:
        document = spym_21c_saved_configuration_document()
        document["market_data"] = {"symbol": "CONFLICT", "provider": "fixture"}
        alternate = conflict.upsert_configuration(document)
        conflict.connection.execute(
            "UPDATE experiment_runs SET configuration_id=? WHERE run_id=?",
            (alternate.configuration_id, TARGET_RUN_ID),
        )
        conflict.connection.commit()
    finally:
        conflict.close()
    with pytest.raises(RuntimeError, match="configuration conflicts"):
        prepare_milestone23_browser_fixture(
            database=conflict_database,
            artifact_root=tmp_path / "conflict-artifacts",
            fixture_launcher=_launcher,
        )


def test_cli_emits_machine_readable_fixture_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "cli.sqlite3"
    root = tmp_path / "cli-artifacts"

    exit_code = browser_fixture_cli.main(
        ["--database", str(database), "--artifact-root", str(root)],
        prepare=lambda **kwargs: prepare_milestone23_browser_fixture(
            fixture_launcher=_launcher,
            **kwargs,
        ),
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["fixture_kind"] == "milestone_23_infrastructure_acceptance"
    assert summary["target_run_id"] == TARGET_RUN_ID
    assert summary["walk_forward_run_id"] == WALK_FORWARD_RUN_ID
    assert summary["monte_carlo_run_id"] == MONTE_CARLO_RUN_ID
    assert summary["robustness_run_id"] == ROBUSTNESS_RUN_ID
    assert isinstance(summary["source_lock_artifact_id"], int)
    assert summary["review_context_identity"]
