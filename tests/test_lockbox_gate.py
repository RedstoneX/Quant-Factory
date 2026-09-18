"""Focused tests for the Milestone 22D-1 lockbox prerequisite gate."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pandas as pd
import pytest

from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample.models import DataPartition, ParameterLock
from backtesting.robustness.models import RobustnessResult, SourceLockEvidence
from backtesting.validation import WalkForwardWindowRules, evaluate_lockbox_prerequisites
from backtesting.walk_forward.models import (
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from persistence import (
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunStage,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from persistence.models import normalized_configuration_document


def _service(
    tmp_path: Path,
    *,
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
    parameters: dict[str, object] | None = None,
) -> PersistenceService:
    parameters = parameters or {"window": 14}
    service = PersistenceService(tmp_path / "state.sqlite3")
    service.register_strategy(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        display_name="Fixture Strategy",
        description="Lockbox gate fixture",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            market_data={"symbol": "SPY", "provider": "fixture"},
            parameters=parameters,
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "none"},
        )
    )
    for run_id, stage in (
        ("wf-run", RunStage.WALK_FORWARD),
        ("mc-run", RunStage.MONTE_CARLO),
        ("robust-run", RunStage.ROBUSTNESS),
    ):
        service.create_run(
            configuration_id=configuration.configuration_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            stage=stage,
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
    return service


def _partition(name: str, start: int, rows: int) -> DataPartition:
    index = pd.date_range("2020-01-01", periods=start + rows, freq="D", tz="UTC")[
        start:
    ]
    data = pd.DataFrame({"Close": range(rows)}, index=index)
    return DataPartition(
        name=name,
        data=data,
        start=str(index[0].date()),
        end=str(index[-1].date()),
        row_count=rows,
    )


def _rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=5,
        training_mode="rolling",
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _lock(
    lock_id: str = "parameter-lock-1",
    *,
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
    parameters: dict[str, object] | None = None,
) -> ParameterLock:
    return ParameterLock(
        lock_id=lock_id,
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        normalized_parameters=tuple(sorted((parameters or {"window": 14}).items())),
        selection_parameter_row_id="row-1",
        selection_start="2020-01-11",
        selection_end="2020-01-15",
        ranking_columns=("score",),
        ranking_ascending=(False,),
    )


def _walk_forward_result(
    *,
    failed: bool = False,
    lock_ids: tuple[str | None, ...] = ("parameter-lock-1",),
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
    parameters: dict[str, object] | None = None,
) -> WalkForwardResult:
    parameters = parameters or {"window": 14}
    folds = []
    for index, lock_id in enumerate(lock_ids):
        fold_id = f"fold_{index + 1:03d}"
        start = index * 5
        fold_failed = failed and index == 0
        folds.append(
            WalkForwardFoldResult(
                fold_id=fold_id,
                status="failed" if fold_failed else "successful",
                window=WalkForwardWindow(
                    fold_id=fold_id,
                    train=_partition(f"{fold_id}:train", start, 10),
                    selection=_partition(f"{fold_id}:selection", start + 10, 5),
                    test=_partition(f"{fold_id}:test", start + 15, 5),
                ),
                training_result=None,
                selection_result=None,
                test_result=None,
                shortlist_parameters=(),
                parameter_lock=(
                    None
                    if fold_failed or lock_id is None
                    else _lock(
                        lock_id,
                        experiment_id=experiment_id,
                        strategy_id=strategy_id,
                        strategy_version=strategy_version,
                        parameters=parameters,
                    )
                ),
                selected_parameters=None if fold_failed else parameters,
                test_metrics={} if fold_failed else {"total_return": 0.01},
                failure_reason="selection failed" if fold_failed else None,
            )
        )
    failed_folds = tuple(fold for fold in folds if fold.status == "failed")
    successful = tuple(fold for fold in folds if fold.status == "successful")
    return WalkForwardResult(
        folds=tuple(folds),
        total_fold_count=len(folds),
        successful_fold_count=len(successful),
        failed_fold_count=len(failed_folds),
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=tuple(fold.fold_id for fold in failed_folds),
        failure_reasons=tuple((fold.fold_id, "selection failed") for fold in failed_folds),
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


def _source(
    values=(0.04, 0.03, 0.02, 0.01),
    *,
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
) -> SourceSeries:
    return SourceSeries(
        source_id="source-lock-1",
        source_kind="period_returns",
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        values=tuple(values),
        provenance={"provider": "fixture"},
        execution_assumptions={"kind": "fixture"},
        period_frequency="daily",
    )


def _monte_carlo_result(
    *,
    status: str = "passed",
    values=(0.04, 0.03, 0.02, 0.01),
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
):
    if status == "insufficient_evidence":
        return run_monte_carlo(
            _source(
                (0.01, 0.02),
                experiment_id=experiment_id,
                strategy_id=strategy_id,
                strategy_version=strategy_version,
            ),
            replace(MonteCarloConfig(), simulation_count=5),
        )
    config = MonteCarloConfig(
        simulation_count=20,
        minimum_observations=3,
        maximum_loss_probability=1.0 if status == "passed" else 0.0,
        maximum_drawdown_breach_probability=1.0 if status == "passed" else 0.0,
        minimum_lower_percentile_return=-1.0 if status == "passed" else 0.10,
    )
    return run_monte_carlo(
        _source(
            values,
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        ),
        config,
    )


def _robustness_result(
    *,
    status: str = "passed",
    locked_parameters: dict[str, int] | None = None,
    source_artifact_id: str = "source-artifact-1",
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
) -> RobustnessResult:
    return RobustnessResult(
        schema_version=1,
        status=status,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        experiment_id=experiment_id,
        source_artifact_id=source_artifact_id,
        locked_parameters=locked_parameters or {"window": 14},
        data_provenance={"provider": "fixture"},
        execution_assumptions={"kind": "fixture"},
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=None,
        regime_results=(),
        component_statuses={"parameter_neighborhood": status, "regimes": status},
        reasons=() if status == "passed" else ("robustness fixture reason",),
        warnings=(),
        timestamp="2026-01-01T00:00:00+00:00",
    )


def _source_lock(
    *,
    status: str = "passed",
    locked_parameters: dict[str, int] | None = None,
    artifact_id: str = "source-artifact-1",
    parameter_lock_id: str | None = "parameter-lock-1",
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
    data_provenance: dict[str, object] | None = None,
    execution_assumptions: dict[str, object] | None = None,
) -> SourceLockEvidence:
    return SourceLockEvidence(
        status=status,
        artifact_path="results/source-lock.json",
        artifact_kind="out_of_sample",
        artifact_id=artifact_id,
        schema_version=1,
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        locked_parameters=locked_parameters or {"window": 14},
        source_start="2020-01-01",
        source_end="2020-04-30",
        data_provenance=data_provenance or {"provider": "fixture"},
        execution_assumptions=execution_assumptions or {"kind": "fixture"},
        metrics={"total_return": 0.1, "max_drawdown": -0.03, "number_of_trades": 5},
        reasons=() if status == "passed" else ("source lock fixture reason",),
        parameter_lock_id=parameter_lock_id,
    )


def _persist_prerequisites(
    service: PersistenceService,
    root: Path,
    *,
    mc_status: str = "passed",
    robust_status: str = "passed",
    robust_parameters: dict[str, int] | None = None,
    robust_source_artifact_id: str = "source-artifact-1",
    wf_failed: bool = False,
    wf_lock_ids: tuple[str | None, ...] = ("parameter-lock-1",),
    mc_values=(0.04, 0.03, 0.02, 0.01),
    experiment_id: str = "lockbox-gate",
    strategy_id: str = "fixture_strategy",
    strategy_version: str = "1.0.0",
    parameters: dict[str, object] | None = None,
) -> None:
    parameters = parameters or {"window": 14}
    evidence = ValidationEvidenceArtifactService(service)
    evidence.persist_walk_forward(
        run_id="wf-run",
        result=_walk_forward_result(
            failed=wf_failed,
            lock_ids=wf_lock_ids,
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            parameters=parameters,
        ),
        rules=_rules(),
        artifact_root=root,
    )
    evidence.persist_monte_carlo(
        run_id="mc-run",
        result=_monte_carlo_result(
            status=mc_status,
            values=mc_values,
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        ),
        artifact_root=root,
    )
    evidence.persist_robustness(
        run_id="robust-run",
        result=_robustness_result(
            status=robust_status,
            locked_parameters=robust_parameters if robust_parameters is not None else parameters,
            source_artifact_id=robust_source_artifact_id,
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
        ),
        artifact_root=root,
    )


def _gate(
    service: PersistenceService,
    root: Path,
    *,
    source_lock: SourceLockEvidence | None = None,
    protected_data_state: object = "gated",
):
    return ValidationEvidenceArtifactService(service).evaluate_lockbox_prerequisites(
        walk_forward_run_id="wf-run",
        monte_carlo_run_id="mc-run",
        robustness_run_id="robust-run",
        source_lock=source_lock if source_lock is not None else _source_lock(),
        artifact_root=root,
        protected_data_state=protected_data_state,
    )


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


def test_failed_walk_forward_without_successful_fold_locks_remains_failed(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, wf_failed=True)

        result = _gate(service, root)

        assert result.status == "failed"
        assert result.eligible_to_execute_lockbox is False
        assert any("walk_forward: fold_001: selection failed" in reason for reason in result.reasons)
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


def test_failed_prerequisite_is_failed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, mc_status="failed")

        result = _gate(service, root)

        assert result.status == "failed"
        assert result.eligible_to_execute_lockbox is False
        assert any(reason.startswith("monte_carlo:") for reason in result.reasons)
    finally:
        service.close()


def test_insufficient_prerequisite_remains_distinct(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    try:
        _persist_prerequisites(service, root, mc_status="insufficient_evidence")

        result = _gate(service, root)

        assert result.status == "insufficient_evidence"
        assert result.eligible_to_execute_lockbox is False
        assert any(reason.startswith("monte_carlo:") for reason in result.reasons)
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
