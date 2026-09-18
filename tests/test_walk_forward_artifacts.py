"""Focused tests for durable generic walk-forward evidence artifacts."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from backtesting.run_rsi_demo import EXPERIMENT_CONFIG
from backtesting.validation import WalkForwardWindowRules
from backtesting.validation.walk_forward_artifacts import (
    WALK_FORWARD_EVIDENCE_LOGICAL_NAME,
    build_walk_forward_evidence_document,
)
from backtesting.walk_forward.models import (
    WalkForwardConfig,
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from backtesting.walk_forward.splitter import build_walk_forward_windows
from orchestration import FixtureRunService
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document
from backtesting.out_of_sample.models import ParameterLock


def _rules(*, step_size: int = 5, mode: str = "rolling") -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=step_size,
        training_mode=mode,
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _frame(rows: int = 40) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame({"Close": range(rows)}, index=index)


def _config(tmp_path: Path, *, step_size: int = 5) -> WalkForwardConfig:
    return WalkForwardConfig(
        experiment=replace(EXPERIMENT_CONFIG, output_path=tmp_path / "base.csv"),
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=step_size,
        training_mode="rolling",
        minimum_rows_per_window=2,
        shortlist_size=1,
        incomplete_final_window="drop",
        output_path=tmp_path / "walk_forward.json",
    )


def _lock(fold_id: str) -> ParameterLock:
    return ParameterLock(
        lock_id=f"{fold_id}:lock",
        experiment_id="experiment-1",
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        normalized_parameters=(("window", 14),),
        selection_parameter_row_id="row-1",
        selection_start="2020-01-01",
        selection_end="2020-01-10",
        ranking_columns=("score",),
        ranking_ascending=(False,),
    )


def _result_from_windows(
    windows: tuple[WalkForwardWindow, ...],
    *,
    failed_fold_id: str | None = None,
) -> WalkForwardResult:
    folds = []
    for window in windows:
        failed = window.fold_id == failed_fold_id
        folds.append(
            WalkForwardFoldResult(
                fold_id=window.fold_id,
                status="failed" if failed else "successful",
                window=window,
                training_result=None,
                selection_result=None,
                test_result=None,
                shortlist_parameters=(),
                parameter_lock=None if failed else _lock(window.fold_id),
                selected_parameters=None if failed else {"window": 14},
                test_metrics={} if failed else {"total_return": 0.01},
                failure_reason="selection failed" if failed else None,
            )
        )
    failed = tuple(fold for fold in folds if fold.status == "failed")
    successful = tuple(fold for fold in folds if fold.status == "successful")
    return WalkForwardResult(
        folds=tuple(folds),
        total_fold_count=len(folds),
        successful_fold_count=len(successful),
        failed_fold_count=len(failed),
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=tuple(fold.fold_id for fold in failed),
        failure_reasons=tuple(
            (fold.fold_id, fold.failure_reason or "unknown") for fold in failed
        ),
        fold_test_metrics=pd.DataFrame(),
        average_fold_metrics={},
        median_fold_metrics={},
        out_of_sample_returns=pd.Series(dtype=float),
        out_of_sample_equity=pd.Series(dtype=float),
        compounded_return=None,
        endpoint_max_drawdown=None,
        fold_return_sharpe=None,
        total_trades=0,
    )


def _service_with_walk_forward_run(
    tmp_path: Path,
    *,
    run_id: str = "wf-run",
) -> PersistenceService:
    service = PersistenceService(tmp_path / "state" / f"{run_id}.sqlite3")
    service.register_strategy(
        strategy_id="fixture_strategy",
        strategy_version="1.0.0",
        display_name="Fixture Strategy",
        description="Synthetic walk-forward fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="walk-forward-artifact",
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
        stage=RunStage.WALK_FORWARD,
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
                actual_coverage="2020-01-01..2020-02-09",
                adjusted=True,
                row_count=40,
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


def _result(tmp_path: Path, *, failed_fold_id: str | None = None) -> WalkForwardResult:
    windows = build_walk_forward_windows(_frame(), _config(tmp_path))
    return _result_from_windows(windows, failed_fold_id=failed_fold_id)


def _leaking_result(tmp_path: Path) -> WalkForwardResult:
    result = _result(tmp_path)
    fold = result.folds[0]
    assert fold.window.selection is not None
    leaking_selection = replace(
        fold.window.selection,
        start=fold.window.train.start,
    )
    leaking_window = replace(fold.window, selection=leaking_selection)
    leaking_fold = replace(fold, window=leaking_window)
    return replace(result, folds=(leaking_fold, *result.folds[1:]))


def _registered_document(
    service: PersistenceService,
    *,
    run_id: str,
    artifact_root: Path,
    document: dict,
):
    content = canonical_json(document).encode("utf-8")
    location = f"artifacts/{run_id}/{WALK_FORWARD_EVIDENCE_LOGICAL_NAME}.json"
    target = artifact_root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    artifact = service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=WALK_FORWARD_EVIDENCE_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    return artifact


def _evidence_identity(document: dict) -> str:
    return hashlib.sha256(
        canonical_json(document["evidence"]).encode("utf-8")
    ).hexdigest()


def test_walk_forward_evidence_persists_and_retrieves(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        persisted = service.persist_walk_forward_evidence(
            run_id="wf-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )

        retrieved = service.retrieve_walk_forward_evidence(
            "wf-run",
            artifact_root=root,
        )

        assert retrieved.artifact == persisted.artifact
        assert retrieved.document == persisted.document
        assert retrieved.document["evidence"]["normalized_evidence"]["status"] == (
            "insufficient_evidence"
        )
        assert retrieved.document["source"]["run_id"] == "wf-run"
    finally:
        service.close()


def test_validation_evidence_service_matches_public_source_wrapper(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    try:
        extracted = ValidationEvidenceArtifactService(service)
        source = extracted.source_document("wf-run")
        manifest = service.build_run_manifest("wf-run")
        assert manifest.lineage is not None
        expected = {
            "run_id": manifest.run_id,
            "configuration_id": manifest.configuration_id,
            "strategy_id": manifest.strategy_id,
            "strategy_version": manifest.strategy_version,
            "stage": service.runs.get("wf-run").stage.value,
            "configuration_hash": manifest.lineage.configuration.config_hash,
            "data_identity": manifest.lineage.data.dataset_identity,
            "execution_assumptions_identity": (
                manifest.lineage.execution_assumptions.execution_assumptions_identity
            ),
            "runtime_identity": manifest.lineage.runtime.runtime_identity,
        }

        assert canonical_json(source) == canonical_json(expected)
        assert source == service.walk_forward_evidence_source_document("wf-run")
    finally:
        service.close()


def test_validation_evidence_service_persists_and_retrieves_directly(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        evidence = ValidationEvidenceArtifactService(service)
        persisted = evidence.persist_walk_forward(
            run_id="wf-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )
        retrieved = evidence.retrieve_walk_forward("wf-run", artifact_root=root)

        assert retrieved.artifact == persisted.artifact
        assert retrieved.document == persisted.document
        assert retrieved.document["artifact"]["logical_name"] == (
            WALK_FORWARD_EVIDENCE_LOGICAL_NAME
        )
    finally:
        service.close()


def test_walk_forward_evidence_identity_is_deterministic_for_identical_reruns(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    first = _service_with_walk_forward_run(tmp_path, run_id="wf-run-a")
    second = _service_with_walk_forward_run(tmp_path, run_id="wf-run-b")
    try:
        one = first.persist_walk_forward_evidence(
            run_id="wf-run-a",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )
        two = second.persist_walk_forward_evidence(
            run_id="wf-run-b",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )

        assert one.evidence_identity == two.evidence_identity
    finally:
        first.close()
        second.close()


def test_walk_forward_evidence_preserves_failed_fold(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        persisted = service.persist_walk_forward_evidence(
            run_id="wf-run",
            result=_result(tmp_path, failed_fold_id="fold_002"),
            rules=_rules(),
            artifact_root=root,
        )

        evidence = persisted.document["evidence"]
        assert evidence["normalized_evidence"]["status"] == "failed"
        assert evidence["normalized_evidence"]["reasons"] == [
            "fold_002: selection failed"
        ]
        assert evidence["folds"][1]["failure_reason"] == "selection failed"
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_fails_for_missing_or_corrupt_artifact(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        persisted = service.persist_walk_forward_evidence(
            run_id="wf-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )
        path = root / persisted.artifact.location
        path.unlink()
        with pytest.raises(ValueError, match="artifact_missing"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)

        path.write_text("{}", encoding="utf-8")
        with pytest.raises(ValueError, match="artifact_.*mismatch"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_mismatched_source_lineage(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path),
            rules=_rules(),
        )
        document["source"]["run_id"] = "other-run"
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="source run mismatch"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_mismatched_lineage_identity(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path),
            rules=_rules(),
        )
        document["source"]["configuration_hash"] = "different-hash"
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="source lineage mismatch"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_missing_fold_fields(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path),
            rules=_rules(),
        )
        document["evidence"]["folds"][0].pop("train")
        document["artifact"]["evidence_identity"] = _evidence_identity(document)
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="fold missing fields"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_inconsistent_declared_rules(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path),
            rules=_rules(),
        )
        document["evidence"]["declared_walk_forward_rules"][
            "training_window_size"
        ] = 11
        document["artifact"]["evidence_identity"] = _evidence_identity(document)
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="declared walk-forward rules"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_missing_parameter_lock(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path),
            rules=_rules(),
        )
        document["evidence"]["folds"][0]["parameter_lock_id"] = None
        document["artifact"]["evidence_identity"] = _evidence_identity(document)
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="lacks a parameter lock"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_walk_forward_evidence_retrieval_rejects_normalized_reason_mismatch(
    tmp_path: Path,
) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        document = build_walk_forward_evidence_document(
            run_id="wf-run",
            source=service.walk_forward_evidence_source_document("wf-run"),
            result=_result(tmp_path, failed_fold_id="fold_002"),
            rules=_rules(),
        )
        document["evidence"]["normalized_evidence"]["reasons"] = ["different"]
        document["artifact"]["evidence_identity"] = _evidence_identity(document)
        _registered_document(
            service,
            run_id="wf-run",
            artifact_root=root,
            document=document,
        )

        with pytest.raises(ValueError, match="normalized evidence does not match"):
            service.retrieve_walk_forward_evidence("wf-run", artifact_root=root)
    finally:
        service.close()


def test_run_service_exposes_walk_forward_evidence(tmp_path: Path) -> None:
    database = tmp_path / "state" / "wf-run.sqlite3"
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        service.persist_walk_forward_evidence(
            run_id="wf-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )
    finally:
        service.close()

    run_service = FixtureRunService(database=database)
    retrieved = run_service.walk_forward_evidence_for_run(
        "wf-run",
        artifact_root=root,
    )

    assert retrieved.document["artifact"]["logical_name"] == (
        WALK_FORWARD_EVIDENCE_LOGICAL_NAME
    )


def test_run_service_persists_retrievable_walk_forward_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "wf-run.sqlite3"
    service = _service_with_walk_forward_run(tmp_path)
    service.close()
    root = tmp_path / "artifacts"

    run_service = FixtureRunService(database=database)
    persisted = run_service.persist_walk_forward_evidence_for_run(
        "wf-run",
        result=_result(tmp_path),
        rules=_rules(),
        artifact_root=root,
    )
    retrieved = run_service.walk_forward_evidence_for_run(
        "wf-run",
        artifact_root=root,
    )

    assert retrieved.artifact == persisted.artifact
    assert retrieved.document["evidence"]["declared_walk_forward_rules"][
        "training_window_size"
    ] == 10
    assert retrieved.document["evidence"]["folds"][0]["fold_id"] == "fold_001"

    persistence = PersistenceService(database)
    try:
        persisted_manifest = persistence.read_persisted_run_manifest("wf-run")
        assert persisted_manifest is not None
        manifest = json.loads(persisted_manifest[0])
        assert [
            artifact["logical_name"] for artifact in manifest["artifacts"]
        ] == [WALK_FORWARD_EVIDENCE_LOGICAL_NAME]
    finally:
        persistence.close()


def test_run_service_rejects_invalid_walk_forward_without_valid_evidence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "wf-run.sqlite3"
    service = _service_with_walk_forward_run(tmp_path)
    service.close()
    root = tmp_path / "artifacts"
    run_service = FixtureRunService(database=database)

    with pytest.raises(ValueError, match="walk-forward result does not satisfy"):
        run_service.persist_walk_forward_evidence_for_run(
            "wf-run",
            result=_leaking_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )

    persistence = PersistenceService(database)
    try:
        assert persistence.list_run_artifacts("wf-run") == ()
        assert persistence.read_persisted_run_manifest("wf-run") is None
    finally:
        persistence.close()


def test_run_service_does_not_attach_walk_forward_evidence_to_unrelated_run(
    tmp_path: Path,
) -> None:
    database = tmp_path / "state" / "fixture-run.sqlite3"
    persistence = PersistenceService(database)
    try:
        persistence.register_strategy(
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            display_name="Fixture Strategy",
            description="Synthetic fixture run",
            lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
        )
        configuration = persistence.upsert_configuration(
            normalized_configuration_document(
                experiment_id="unrelated-fixture",
                strategy_id="fixture_strategy",
                strategy_version="1.0.0",
                market_data={"kind": "none"},
                parameters={"fixture": True},
                execution={"kind": "fixture"},
                ranking={"columns": ("score",), "ascending": (False,)},
                screening={"kind": "none"},
            )
        )
        persistence.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id="fixture_strategy",
            strategy_version="1.0.0",
            stage=RunStage.FIXTURE,
            run_id="fixture-run",
        )
    finally:
        persistence.close()

    run_service = FixtureRunService(database=database)
    assert run_service.get_run("fixture-run").status == RunStatus.CREATED.value
    with pytest.raises(ValueError, match="fixture runs"):
        run_service.persist_walk_forward_evidence_for_run(
            "fixture-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=tmp_path / "artifacts",
        )

    persistence = PersistenceService(database)
    try:
        assert persistence.list_run_artifacts("fixture-run") == ()
    finally:
        persistence.close()


def test_walk_forward_evidence_does_not_promote_progression(tmp_path: Path) -> None:
    service = _service_with_walk_forward_run(tmp_path)
    root = tmp_path / "artifacts"
    try:
        persisted = service.persist_walk_forward_evidence(
            run_id="wf-run",
            result=_result(tmp_path),
            rules=_rules(),
            artifact_root=root,
        )

        normalized = persisted.document["evidence"]["normalized_evidence"]
        assert normalized["status"] == "insufficient_evidence"
        assert normalized["eligible_to_progress"] is False
    finally:
        service.close()
