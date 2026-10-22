"""Shared lockbox-gate evidence fixtures for the lockbox gate tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample.models import DataPartition, ParameterLock
from backtesting.robustness.models import RobustnessResult, SourceLockEvidence
from backtesting.validation import WalkForwardWindowRules
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
from backtesting.validation.evidence_service import ValidationEvidenceArtifactService
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
