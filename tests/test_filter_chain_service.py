"""Focused proof for evidence-derived connected filter handoffs."""

from __future__ import annotations

from dataclasses import replace
import inspect
from pathlib import Path
import threading

import pytest

from orchestration.filter_chain import (
    FILTER_HANDOFF_ENVIRONMENT_KEY,
    FactoryFilterChainService,
    FilterStageInvocationUnknownError,
    PersistedStageReference,
    VALIDATION_STAGE_ORDER,
)
from persistence import (
    ArtifactType,
    DataProvenanceRecord,
    ExecutionAssumptionsRecord,
    PersistenceService,
    RunEventType,
    RunStage,
    RunStatus,
    StrategyLifecycle,
    canonical_json,
)
from persistence.database import transaction
from persistence.evidence_service import (
    ValidationEvidenceArtifactService,
)
from persistence.models import normalized_configuration_document
from prefect_spike.milestone23_browser_fixture import (
    FIXTURE_LABEL,
    SOURCE_LOCK_ARTIFACT_ID,
    _monte_carlo_result,
    _robustness_result,
    _walk_forward_result,
    _walk_forward_rules,
)
from strategies.spym_rsi_mean_reversion_fixture import (
    SPYM_RSI_ENTRY_THRESHOLD,
    SPYM_RSI_EXIT_THRESHOLD,
    SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC,
    SPYM_RSI_WINDOW,
)


STRATEGY_ID = SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.identity.strategy_id
STRATEGY_VERSION = SPYM_RSI_MEAN_REVERSION_FIXTURE_SPEC.identity.version
PARAMETERS = {
    "window": SPYM_RSI_WINDOW,
    "entry_threshold": SPYM_RSI_ENTRY_THRESHOLD,
    "exit_threshold": SPYM_RSI_EXIT_THRESHOLD,
}


def _service(tmp_path: Path, *, screening_status: str = "passed") -> PersistenceService:
    service = PersistenceService(tmp_path / "state.sqlite3")
    service.register_strategy(
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        display_name="Connected fixture",
        description="Mechanics evidence only",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="connected-filter-chain",
            strategy_id=STRATEGY_ID,
            strategy_version=STRATEGY_VERSION,
            market_data={"provider": "fixture", "symbol": "SYNTHETIC"},
            parameters=PARAMETERS,
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "fixed"},
        )
    )
    screening = service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION,
        stage=RunStage.SCREENING,
        run_id="screening-run",
        status=RunStatus.SUCCEEDED,
    )
    with transaction(service.connection):
        service.results.add_parameter_result(
            run_id=screening.run_id,
            row_id="screening-row",
            normalized_parameters=PARAMETERS,
            metrics={"total_return": 0.01},
            ranking_position=1,
            screening_status=screening_status,
            rejection_reasons=(
                "minimum return not met" if screening_status != "passed" else ""
            ),
        )
    return service


def _set_lineage(service: PersistenceService, run_id: str) -> None:
    with transaction(service.connection):
        service.results.set_data_provenance(
            DataProvenanceRecord(
                run_id=run_id,
                provider="fixture",
                provider_implementation="connected-filter-fixture",
                symbol="SYNTHETIC",
                interval="1 day",
                timezone="UTC",
                requested_coverage="2020-01-01..2020-04-30",
                actual_coverage="2020-01-01..2020-04-30",
                adjusted=True,
                row_count=120,
                cache_action="fixture",
                validation_summary_json=canonical_json({"valid": True}),
                manifest_reference="fixture",
                checksum="fixture-checksum",
            )
        )
        service.results.set_execution_assumptions(
            ExecutionAssumptionsRecord(
                run_id=run_id,
                assumptions_json=canonical_json({"kind": "fixture"}),
            )
        )


def _create_stage(
    service: PersistenceService,
    stage: RunStage,
    run_id: str,
) -> str:
    run = service.runs.get(run_id)
    assert run is not None
    assert run.stage == stage
    assert run.status == RunStatus.CREATED
    service.transition_run(run_id, RunStatus.RUNNING)
    _set_lineage(service, run_id)
    return run_id


def _persist_source_lock(
    service: PersistenceService,
    root: Path,
    run_id: str,
) -> None:
    source = ValidationEvidenceArtifactService(service).source_document(run_id)
    payload = {
        "schema_version": 1,
        "artifact_kind": "out_of_sample",
        "artifact_id": SOURCE_LOCK_ARTIFACT_ID,
        "experiment_id": "connected-filter-chain",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "source_start": "2020-01-01",
        "source_end": "2020-04-30",
        "data_provenance": {
            "dataset_identity": source["data_identity"],
            "provider": "fixture",
        },
        "execution_assumptions": {"kind": "fixture"},
        "parameter_lock": {
            "lock_id": f"{FIXTURE_LABEL}_parameter_lock",
            "normalized_parameters": PARAMETERS,
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
    location = f"artifacts/{run_id}/source_lock.json"
    target = root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=f"source_lock_evidence:{SOURCE_LOCK_ARTIFACT_ID}",
        media_type="application/json",
        format="json",
        location=location,
        content=content,
        schema_version=1,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))


def _stage_adapter(
    service: PersistenceService,
    root: Path,
    stage: RunStage,
    calls: list[tuple[str, str]],
    *,
    failed_walk_forward: bool = False,
    corrupt: bool = False,
):
    def execute(context):
        calls.append((stage.value, context.previous_run_id))
        run_id = _create_stage(service, stage, context.run_id)
        evidence = ValidationEvidenceArtifactService(service)
        if stage == RunStage.OOS:
            _persist_source_lock(service, root, run_id)
        elif stage == RunStage.WALK_FORWARD:
            result = _walk_forward_result(
                experiment_id="connected-filter-chain",
                strategy_id=STRATEGY_ID,
                strategy_version=STRATEGY_VERSION,
                parameters=PARAMETERS,
            )
            if failed_walk_forward:
                fold = replace(
                    result.folds[0],
                    status="failed",
                    parameter_lock=None,
                    selected_parameters=None,
                    test_metrics={},
                    failure_reason="fixture stage failed",
                )
                result = replace(
                    result,
                    folds=(fold,),
                    successful_fold_count=0,
                    failed_fold_count=1,
                    failed_fold_ids=(fold.fold_id,),
                    failure_reasons=((fold.fold_id, "fixture stage failed"),),
                )
            evidence.persist_walk_forward(
                run_id=run_id,
                result=result,
                rules=_walk_forward_rules(),
                artifact_root=root,
            )
        elif stage == RunStage.ROBUSTNESS:
            source = evidence.source_document(run_id)
            evidence.persist_robustness(
                run_id=run_id,
                result=_robustness_result(
                    experiment_id="connected-filter-chain",
                    strategy_id=STRATEGY_ID,
                    strategy_version=STRATEGY_VERSION,
                    parameters=PARAMETERS,
                    target_source=source,
                    provider="fixture",
                    execution={"kind": "fixture"},
                ),
                artifact_root=root,
            )
        else:
            evidence.persist_monte_carlo(
                run_id=run_id,
                result=_monte_carlo_result(
                    experiment_id="connected-filter-chain",
                    strategy_id=STRATEGY_ID,
                    strategy_version=STRATEGY_VERSION,
                ),
                artifact_root=root,
            )
        if corrupt:
            artifact = service.list_run_artifacts(run_id)[0]
            (root / artifact.location).write_text("{}", encoding="utf-8")
        service.transition_run(run_id, RunStatus.SUCCEEDED)
        return PersistedStageReference(stage=stage, run_id=run_id)

    return execute


def _adapters(
    service: PersistenceService,
    root: Path,
    calls: list[tuple[str, str]],
    overrides: dict[RunStage, dict[str, bool]] | None = None,
):
    overrides = overrides or {}
    return {
        stage: _stage_adapter(
            service,
            root,
            stage,
            calls,
            **overrides.get(stage, {}),
        )
        for stage in VALIDATION_STAGE_ORDER
    }


def test_screened_out_run_stops_without_invoking_later_filters(tmp_path: Path) -> None:
    service = _service(tmp_path, screening_status="screened_out")
    calls: list[tuple[str, str]] = []
    try:
        outcome = FactoryFilterChainService(
            service, artifact_root=tmp_path / "artifacts"
        ).run(
            screening_run_id="screening-run",
            stage_adapters=_adapters(service, tmp_path / "artifacts", calls),
        )
        assert outcome.status == "screened_out"
        assert outcome.reasons == ("minimum return not met",)
        assert calls == []
    finally:
        service.close()


def test_survivor_advances_in_fixed_order_from_validated_evidence(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    try:
        outcome = FactoryFilterChainService(service, artifact_root=root).run(
            screening_run_id="screening-run",
            stage_adapters=_adapters(service, root, calls),
        )
        assert tuple(stage for stage, _ in calls) == tuple(
            stage.value for stage in VALIDATION_STAGE_ORDER
        )
        assert calls[0][1] == "screening-run"
        assert tuple(source for _, source in calls[1:]) == tuple(
            handoff.run_id for handoff in outcome.completed[:-1]
        )
        assert outcome.status == "ready_for_protected_test"
        assert outcome.protected_test_gate.status == "passed"
        assert outcome.protected_test_gate.eligible_to_execute_lockbox is True
        assert outcome.protected_test_gate.eligible_to_progress is False
    finally:
        service.close()


def test_persisted_failure_stops_before_next_stage(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    try:
        outcome = FactoryFilterChainService(service, artifact_root=root).run(
            screening_run_id="screening-run",
            stage_adapters=_adapters(
                service,
                root,
                calls,
                overrides={RunStage.WALK_FORWARD: {"failed_walk_forward": True}},
            ),
        )
        assert tuple(stage for stage, _ in calls) == ("oos", "walk_forward")
        assert calls[0][1] == "screening-run"
        assert outcome.status == "stopped"
        assert outcome.stopped_at == "walk_forward"
        assert "fixture stage failed" in outcome.reasons[0]
    finally:
        service.close()


def test_corrupt_persisted_evidence_stops_chain(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    try:
        outcome = FactoryFilterChainService(service, artifact_root=root).run(
            screening_run_id="screening-run",
            stage_adapters=_adapters(
                service,
                root,
                calls,
                overrides={RunStage.ROBUSTNESS: {"corrupt": True}},
            ),
        )
        assert outcome.status == "stopped"
        assert outcome.stopped_at == "robustness"
        assert calls[-1][0] == "robustness"
        assert all(stage != "monte_carlo" for stage, _ in calls)
        assert outcome.completed[-1].status == "invalid"
    finally:
        service.close()


def test_broken_predecessor_lineage_is_rejected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    try:
        run_id = FactoryFilterChainService._handoff_run_id(
            screening_run_id="screening-run",
            source_run_id="screening-run",
            stage=RunStage.OOS,
        )
        screening = service.runs.get("screening-run")
        assert screening is not None
        service.create_run(
            configuration_id=screening.configuration_id,
            strategy_id=screening.strategy_id,
            strategy_version=screening.strategy_version,
            stage=RunStage.OOS,
            run_id=run_id,
            status=RunStatus.SUCCEEDED,
            environment={
                FILTER_HANDOFF_ENVIRONMENT_KEY: {"source_run_id": "wrong-run"}
            },
        )
        with pytest.raises(ValueError, match="predecessor lineage is invalid"):
            FactoryFilterChainService(service, artifact_root=root).run(
                screening_run_id="screening-run",
                stage_adapters=_adapters(service, root, calls),
            )
        assert calls == []
    finally:
        service.close()


def test_callers_cannot_inject_a_protected_test_gate() -> None:
    parameters = inspect.signature(FactoryFilterChainService.run).parameters
    assert "protected_test_gate" not in parameters


def test_replay_reopens_the_same_handoffs_without_reinvoking_adapters(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls: list[tuple[str, str]] = []
    try:
        coordinator = FactoryFilterChainService(service, artifact_root=root)
        first = coordinator.run(
            screening_run_id="screening-run",
            stage_adapters=_adapters(service, root, calls),
        )

        def must_not_repeat(_context):
            raise AssertionError("a persisted filter handoff must be reopened")

        second = coordinator.run(
            screening_run_id="screening-run",
            stage_adapters={stage: must_not_repeat for stage in VALIDATION_STAGE_ORDER},
        )

        assert second == first
        assert len(service.runs.list()) == 5
    finally:
        service.close()


def test_atomic_reservation_prevents_two_workers_from_invoking_same_stage(
    tmp_path: Path,
) -> None:
    database_service = _service(tmp_path)
    database_service.close()
    root = tmp_path / "artifacts"
    entered = threading.Event()
    release = threading.Event()
    first_error: list[BaseException] = []
    first_calls: list[tuple[str, str]] = []

    def first_worker() -> None:
        service = PersistenceService(tmp_path / "state.sqlite3")
        try:
            adapters = _adapters(service, root, first_calls)
            oos_adapter = adapters[RunStage.OOS]

            def held_oos(context):
                entered.set()
                assert release.wait(timeout=10)
                return oos_adapter(context)

            adapters[RunStage.OOS] = held_oos
            FactoryFilterChainService(service, artifact_root=root).run(
                screening_run_id="screening-run",
                stage_adapters=adapters,
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            first_error.append(exc)
        finally:
            service.close()

    worker = threading.Thread(target=first_worker)
    worker.start()
    assert entered.wait(timeout=10)
    second = PersistenceService(tmp_path / "state.sqlite3")
    second_calls: list[tuple[str, str]] = []
    try:
        with pytest.raises(ValueError, match="persisted run identity"):
            FactoryFilterChainService(second, artifact_root=root).run(
                screening_run_id="screening-run",
                stage_adapters=_adapters(second, root, second_calls),
            )
        assert second_calls == []
    finally:
        second.close()
        release.set()
        worker.join(timeout=20)
    assert not worker.is_alive()
    assert first_error == []
    assert tuple(stage for stage, _ in first_calls) == tuple(
        stage.value for stage in VALIDATION_STAGE_ORDER
    )


def test_adapter_failure_is_durable_unknown_and_never_reinvoked(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts"
    calls = 0

    def failing_adapter(_context):
        nonlocal calls
        calls += 1
        raise RuntimeError("controlled adapter failure")

    adapters = {stage: failing_adapter for stage in VALIDATION_STAGE_ORDER}
    coordinator = FactoryFilterChainService(service, artifact_root=root)
    try:
        with pytest.raises(FilterStageInvocationUnknownError, match="owner investigation"):
            coordinator.run(
                screening_run_id="screening-run",
                stage_adapters=adapters,
            )
        run_id = FactoryFilterChainService._handoff_run_id(
            screening_run_id="screening-run",
            source_run_id="screening-run",
            stage=RunStage.OOS,
        )
        failed = service.runs.get(run_id)
        assert failed is not None
        assert failed.status == RunStatus.FAILED
        assert failed.error_summary == (
            "Filter-stage adapter outcome is unknown; automatic rerun is blocked "
            "pending owner investigation."
        )
        events = service.events.list_for_run(run_id)
        assert tuple(event.event_type for event in events) == (RunEventType.RUN_FAILED,)
        assert "automatic rerun is blocked" in events[0].message

        with pytest.raises(ValueError, match="persisted run identity"):
            coordinator.run(
                screening_run_id="screening-run",
                stage_adapters=adapters,
            )
        assert calls == 1
    finally:
        service.close()
