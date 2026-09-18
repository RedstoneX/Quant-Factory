"""Prepare the deterministic Milestone 23 browser acceptance fixture set."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import pandas as pd

from backtesting.monte_carlo import MonteCarloConfig, SourceSeries, run_monte_carlo
from backtesting.out_of_sample.models import DataPartition, ParameterLock
from backtesting.robustness.models import RobustnessResult
from backtesting.validation import WalkForwardWindowRules
from backtesting.validation.evidence_decision_artifacts import (
    EVIDENCE_DECISION_LOGICAL_NAME,
)
from backtesting.walk_forward.models import (
    WalkForwardFoldResult,
    WalkForwardResult,
    WalkForwardWindow,
)
from orchestration import FixtureRunService
from persistence import ArtifactType, PersistenceService, RunStage, RunStatus, canonical_json
from persistence.database import transaction
from persistence.evidence_service import ValidationEvidenceArtifactService
from prefect_spike.spym_vectorbt_fixture import (
    SPYM_21C_FIXTURE_KIND,
    ensure_spym_21c_saved_configuration,
    spym_21c_saved_configuration_document,
)

FIXTURE_LABEL = "m23_browser_acceptance"
TARGET_LAUNCH_KEY = "launch_m23_browser_spym_target"
TARGET_RUN_ID = f"{FIXTURE_LABEL}_spym_target"
SOURCE_LOCK_RUN_ID = f"{FIXTURE_LABEL}_spym_source_lock"
WALK_FORWARD_RUN_ID = f"{FIXTURE_LABEL}_spym_walk_forward"
MONTE_CARLO_RUN_ID = f"{FIXTURE_LABEL}_spym_monte_carlo"
ROBUSTNESS_RUN_ID = f"{FIXTURE_LABEL}_spym_robustness"
SOURCE_LOCK_LOGICAL_NAME = f"{FIXTURE_LABEL}_source_lock_evidence"
SOURCE_LOCK_ARTIFACT_ID = f"{FIXTURE_LABEL}_source_lock"

FixtureLauncher = Callable[..., Any]


@dataclass(frozen=True)
class Milestone23BrowserFixtureSummary:
    """Machine-readable identity summary for the deterministic browser fixture."""

    database: str
    artifact_root: str
    target_run_id: str
    walk_forward_run_id: str
    monte_carlo_run_id: str
    robustness_run_id: str
    source_lock_artifact_id: int
    review_context_identity: str

    def to_dict(self) -> dict[str, object]:
        return {
            "fixture_kind": "milestone_23_infrastructure_acceptance",
            "database": self.database,
            "artifact_root": self.artifact_root,
            "target_run_id": self.target_run_id,
            "walk_forward_run_id": self.walk_forward_run_id,
            "monte_carlo_run_id": self.monte_carlo_run_id,
            "robustness_run_id": self.robustness_run_id,
            "source_lock_artifact_id": self.source_lock_artifact_id,
            "review_context_identity": self.review_context_identity,
        }


def prepare_milestone23_browser_fixture(
    *,
    database: str | Path,
    artifact_root: str | Path,
    fixture_launcher: FixtureLauncher | None = None,
) -> Milestone23BrowserFixtureSummary:
    """Create or validate the explicit, deterministic Milestone 23 fixture set.

    This deliberately prepares infrastructure acceptance evidence only. It never
    creates a human review decision and never represents the SPYM fixture as
    production research evidence.
    """
    database_path = Path(database)
    root = Path(artifact_root)
    service = PersistenceService(database_path)
    try:
        existing_runs = tuple(
            service.runs.get(run_id)
            for run_id in _fixture_run_ids()
        )
        if any(existing_runs):
            if not all(existing_runs):
                raise RuntimeError("Milestone 23 browser acceptance fixture is partial")
            return _validate_existing_fixture(service, root)

        configuration_id = ensure_spym_21c_saved_configuration(service)
        launch = FixtureRunService(
            database=database_path,
            **({"fixture_launcher": fixture_launcher} if fixture_launcher else {}),
        ).launch_fixture(
            idempotency_key=TARGET_LAUNCH_KEY,
            configuration_id=configuration_id,
            run_id=TARGET_RUN_ID,
        )
        if launch.run.status != RunStatus.SUCCEEDED.value:
            raise RuntimeError("Milestone 23 browser acceptance SPYM target did not succeed")
        _persist_companion_evidence(service, root, configuration_id)
        return _validate_existing_fixture(service, root)
    finally:
        service.close()


def _fixture_run_ids() -> tuple[str, ...]:
    return (
        TARGET_RUN_ID,
        SOURCE_LOCK_RUN_ID,
        WALK_FORWARD_RUN_ID,
        MONTE_CARLO_RUN_ID,
        ROBUSTNESS_RUN_ID,
    )


def _effective_spym_parameters(configuration: Mapping[str, Any]) -> dict[str, Any]:
    envelope = configuration.get("parameters")
    if not isinstance(envelope, Mapping) or set(envelope) != {
        "fixture",
        "strategy_parameters",
    }:
        raise RuntimeError("SPYM acceptance fixture parameter envelope is invalid")
    if envelope.get("fixture") != SPYM_21C_FIXTURE_KIND:
        raise RuntimeError("SPYM acceptance fixture kind is invalid")
    parameters = envelope.get("strategy_parameters")
    if not isinstance(parameters, Mapping) or not parameters:
        raise RuntimeError("SPYM acceptance fixture strategy parameters are invalid")
    return dict(parameters)


def _validate_target(
    service: PersistenceService,
) -> tuple[Any, dict[str, Any], Any, Any, dict[str, Any]]:
    target = service.runs.get(TARGET_RUN_ID)
    if target is None:
        raise RuntimeError("Milestone 23 browser acceptance target is missing")
    if target.status != RunStatus.SUCCEEDED:
        raise RuntimeError("Milestone 23 browser acceptance target is not successful")
    configuration = service.configurations.get(target.configuration_id)
    if configuration is None:
        raise RuntimeError("Milestone 23 browser acceptance target configuration is missing")
    expected = canonical_json(spym_21c_saved_configuration_document())
    if configuration.canonical_config_json != expected:
        raise RuntimeError("Milestone 23 browser acceptance target configuration conflicts")
    document = json.loads(configuration.canonical_config_json)
    parameters = _effective_spym_parameters(document)
    provenance = service.results.get_data_provenance(TARGET_RUN_ID)
    execution = service.results.get_execution_assumptions(TARGET_RUN_ID)
    if provenance is None or execution is None:
        raise RuntimeError("Milestone 23 browser acceptance target lineage is incomplete")
    return target, document, provenance, execution, parameters


def _persist_companion_evidence(
    service: PersistenceService,
    root: Path,
    configuration_id: str,
) -> None:
    target, configuration, provenance, execution, parameters = _validate_target(service)
    if target.configuration_id != configuration_id:
        raise RuntimeError("Milestone 23 browser acceptance target identity conflicts")
    environment = json.loads(target.environment_json)
    for run_id, stage in (
        (SOURCE_LOCK_RUN_ID, RunStage.OOS),
        (WALK_FORWARD_RUN_ID, RunStage.WALK_FORWARD),
        (MONTE_CARLO_RUN_ID, RunStage.MONTE_CARLO),
        (ROBUSTNESS_RUN_ID, RunStage.ROBUSTNESS),
    ):
        service.create_run(
            configuration_id=target.configuration_id,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
            stage=stage,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
            environment=environment,
        )
        with transaction(service.connection):
            service.results.set_data_provenance(replace(provenance, run_id=run_id))
            service.results.set_execution_assumptions(replace(execution, run_id=run_id))

    evidence = ValidationEvidenceArtifactService(service)
    experiment_id = str(configuration["experiment_id"])
    evidence.persist_walk_forward(
        run_id=WALK_FORWARD_RUN_ID,
        result=_walk_forward_result(
            experiment_id=experiment_id,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
            parameters=parameters,
        ),
        rules=_walk_forward_rules(),
        artifact_root=root,
    )
    evidence.persist_monte_carlo(
        run_id=MONTE_CARLO_RUN_ID,
        result=_monte_carlo_result(
            experiment_id=experiment_id,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
        ),
        artifact_root=root,
    )
    target_source = evidence.source_document(TARGET_RUN_ID)
    source_lock_artifact_id = _persist_source_lock_artifact(
        service,
        root,
        target=target,
        configuration=configuration,
        provenance=provenance,
        execution=execution,
        parameters=parameters,
        target_source=target_source,
    )
    evidence.persist_robustness(
        run_id=ROBUSTNESS_RUN_ID,
        result=_robustness_result(
            experiment_id=experiment_id,
            strategy_id=target.strategy_id,
            strategy_version=target.strategy_version,
            parameters=parameters,
            target_source=target_source,
            provider=provenance.provider,
            execution=json.loads(execution.assumptions_json),
        ),
        artifact_root=root,
    )
    evidence.persist_review_context(
        target_run_id=TARGET_RUN_ID,
        source_lock_run_id=SOURCE_LOCK_RUN_ID,
        source_lock_artifact_id=source_lock_artifact_id,
        walk_forward_run_id=WALK_FORWARD_RUN_ID,
        monte_carlo_run_id=MONTE_CARLO_RUN_ID,
        robustness_run_id=ROBUSTNESS_RUN_ID,
        protected_data_state="gated",
        artifact_root=root,
    )


def _persist_source_lock_artifact(
    service: PersistenceService,
    root: Path,
    *,
    target: Any,
    configuration: Mapping[str, Any],
    provenance: Any,
    execution: Any,
    parameters: dict[str, Any],
    target_source: Mapping[str, Any],
) -> int:
    location = f"artifacts/{SOURCE_LOCK_RUN_ID}/{SOURCE_LOCK_LOGICAL_NAME}.json"
    payload = {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": SOURCE_LOCK_ARTIFACT_ID,
        "experiment_id": configuration["experiment_id"],
        "strategy_id": target.strategy_id,
        "strategy_version": target.strategy_version,
        "source_start": "2025-10-31",
        "source_end": "2025-10-31",
        "data_provenance": {
            "dataset_identity": target_source["data_identity"],
            "provider": provenance.provider,
        },
        "execution_assumptions": json.loads(execution.assumptions_json),
        "parameter_lock": {
            "lock_id": f"{FIXTURE_LABEL}_parameter_lock",
            "normalized_parameters": parameters,
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
    path = root / location
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    artifact = service.register_artifact(
        run_id=SOURCE_LOCK_RUN_ID,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=SOURCE_LOCK_LOGICAL_NAME,
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=1,
    )
    return artifact.artifact_id


def _walk_forward_rules() -> WalkForwardWindowRules:
    return WalkForwardWindowRules(
        training_window_size=10,
        selection_window_size=5,
        test_window_size=5,
        step_size=5,
        training_mode="rolling",
        minimum_rows_per_window=2,
        incomplete_final_window="drop",
    )


def _partition(name: str, start: int, rows: int) -> DataPartition:
    index = pd.date_range("2020-01-01", periods=start + rows, freq="D", tz="UTC")[
        start:
    ]
    return DataPartition(
        name=name,
        data=pd.DataFrame({"Close": range(rows)}, index=index),
        start=str(index[0].date()),
        end=str(index[-1].date()),
        row_count=rows,
    )


def _walk_forward_result(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
) -> WalkForwardResult:
    fold_id = f"{FIXTURE_LABEL}_fold_001"
    return WalkForwardResult(
        folds=(
            WalkForwardFoldResult(
                fold_id=fold_id,
                status="successful",
                window=WalkForwardWindow(
                    fold_id=fold_id,
                    train=_partition(f"{fold_id}:train", 0, 10),
                    selection=_partition(f"{fold_id}:selection", 10, 5),
                    test=_partition(f"{fold_id}:test", 15, 5),
                ),
                training_result=None,
                selection_result=None,
                test_result=None,
                shortlist_parameters=(),
                parameter_lock=ParameterLock(
                    lock_id=f"{FIXTURE_LABEL}_parameter_lock",
                    experiment_id=experiment_id,
                    strategy_id=strategy_id,
                    strategy_version=strategy_version,
                    normalized_parameters=tuple(sorted(parameters.items())),
                    selection_parameter_row_id=f"{FIXTURE_LABEL}_selected_row",
                    selection_start="2020-01-11",
                    selection_end="2020-01-15",
                    ranking_columns=("score",),
                    ranking_ascending=(False,),
                ),
                selected_parameters=parameters,
                test_metrics={"total_return": 0.01},
                failure_reason=None,
            ),
        ),
        total_fold_count=1,
        successful_fold_count=1,
        failed_fold_count=0,
        selected_parameters_by_fold=(),
        unique_parameter_set_count=0,
        parameter_frequencies=(),
        parameter_change_percentage=0.0,
        maximum_consecutive_persistence=0,
        failed_fold_ids=(),
        failure_reasons=(),
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


def _monte_carlo_result(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
):
    return run_monte_carlo(
        SourceSeries(
            source_id=f"{FIXTURE_LABEL}_source_lock",
            source_kind="period_returns",
            experiment_id=experiment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            values=(0.04, 0.03, 0.02, 0.01),
            provenance={"fixture": FIXTURE_LABEL},
            execution_assumptions={"fixture": FIXTURE_LABEL},
            period_frequency="daily",
        ),
        MonteCarloConfig(
            simulation_count=20,
            minimum_observations=3,
            maximum_loss_probability=1.0,
            maximum_drawdown_breach_probability=1.0,
            minimum_lower_percentile_return=-1.0,
        ),
    )


def _robustness_result(
    *,
    experiment_id: str,
    strategy_id: str,
    strategy_version: str,
    parameters: dict[str, Any],
    target_source: Mapping[str, Any],
    provider: str,
    execution: dict[str, Any],
) -> RobustnessResult:
    return RobustnessResult(
        schema_version=1,
        status="passed",
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        experiment_id=experiment_id,
        source_artifact_id=SOURCE_LOCK_ARTIFACT_ID,
        locked_parameters=parameters,
        data_provenance={
            "dataset_identity": target_source["data_identity"],
            "provider": provider,
        },
        execution_assumptions=execution,
        neighborhood_construction=None,
        parameter_points=(),
        neighborhood_summary=None,
        regime_metadata=None,
        regime_results=(),
        component_statuses={"parameter_neighborhood": "passed", "regimes": "passed"},
        reasons=(),
        warnings=("Deterministic Milestone 23 infrastructure acceptance fixture.",),
        timestamp="2026-07-18T00:00:00+00:00",
    )


def _validate_existing_fixture(
    service: PersistenceService,
    root: Path,
) -> Milestone23BrowserFixtureSummary:
    target, _, _, _, _ = _validate_target(service)
    expected_stages = {
        SOURCE_LOCK_RUN_ID: RunStage.OOS,
        WALK_FORWARD_RUN_ID: RunStage.WALK_FORWARD,
        MONTE_CARLO_RUN_ID: RunStage.MONTE_CARLO,
        ROBUSTNESS_RUN_ID: RunStage.ROBUSTNESS,
    }
    for run_id, stage in expected_stages.items():
        run = service.runs.get(run_id)
        if run is None or run.stage != stage or run.status != RunStatus.SUCCEEDED:
            raise RuntimeError("Milestone 23 browser acceptance companion run conflicts")
        if (
            run.configuration_id != target.configuration_id
            or run.strategy_id != target.strategy_id
            or run.strategy_version != target.strategy_version
        ):
            raise RuntimeError("Milestone 23 browser acceptance companion identity conflicts")
    source_artifacts = tuple(
        artifact
        for artifact in service.list_run_artifacts(SOURCE_LOCK_RUN_ID)
        if artifact.logical_name == SOURCE_LOCK_LOGICAL_NAME
        and artifact.artifact_type == ArtifactType.VALIDATION_EVIDENCE
    )
    if len(source_artifacts) != 1:
        raise RuntimeError("Milestone 23 browser acceptance source-lock artifact conflicts")
    evidence = ValidationEvidenceArtifactService(service)
    gate = evidence.evaluate_persisted_review_context(TARGET_RUN_ID, artifact_root=root)
    if gate.status != "passed" or not gate.eligible_to_execute_lockbox:
        raise RuntimeError("Milestone 23 browser acceptance review context is not eligible")
    if any(
        artifact.logical_name == EVIDENCE_DECISION_LOGICAL_NAME
        for artifact in service.list_run_artifacts(TARGET_RUN_ID)
    ):
        raise RuntimeError("Milestone 23 browser acceptance fixture already has a review decision")
    context = evidence.retrieve_review_context(TARGET_RUN_ID, artifact_root=root)
    return Milestone23BrowserFixtureSummary(
        database=str(service.connection.execute("PRAGMA database_list").fetchone()[2]),
        artifact_root=str(root),
        target_run_id=TARGET_RUN_ID,
        walk_forward_run_id=WALK_FORWARD_RUN_ID,
        monte_carlo_run_id=MONTE_CARLO_RUN_ID,
        robustness_run_id=ROBUSTNESS_RUN_ID,
        source_lock_artifact_id=source_artifacts[0].artifact_id,
        review_context_identity=context.context_identity,
    )
