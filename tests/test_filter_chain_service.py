"""Focused application-service proof for connected filter handoffs."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestration.filter_chain import (
    FactoryFilterChainService,
    FilterStageHandoff,
    ProtectedTestGate,
    VALIDATION_STAGE_ORDER,
)
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
from persistence.models import normalized_configuration_document


def _service(tmp_path: Path, *, screening_status: str = "passed") -> PersistenceService:
    service = PersistenceService(tmp_path / "state.sqlite3")
    service.register_strategy(
        strategy_id="connected_fixture",
        strategy_version="1.0.0",
        display_name="Connected fixture",
        description="Mechanics evidence only",
        lifecycle=StrategyLifecycle.INFRASTRUCTURE_FIXTURE,
    )
    configuration = service.upsert_configuration(
        normalized_configuration_document(
            experiment_id="connected-filter-chain",
            strategy_id="connected_fixture",
            strategy_version="1.0.0",
            market_data={"provider": "fixture", "symbol": "SYNTHETIC"},
            parameters={"window": 14},
            execution={"kind": "fixture"},
            ranking={"columns": ("total_return",), "ascending": (False,)},
            screening={"kind": "fixed"},
        )
    )
    screening = service.create_run(
        configuration_id=configuration.configuration_id,
        strategy_id="connected_fixture",
        strategy_version="1.0.0",
        stage=RunStage.SCREENING,
        run_id="screening-run",
    )
    service.transition_run(screening.run_id, RunStatus.RUNNING)
    with transaction(service.connection):
        service.results.add_parameter_result(
            run_id=screening.run_id,
            row_id="screening-row",
            normalized_parameters={"window": 14},
            metrics={"total_return": 0.01},
            ranking_position=1,
            screening_status=screening_status,
            rejection_reasons=(
                "minimum return not met" if screening_status != "passed" else ""
            ),
        )
    service.transition_run(screening.run_id, RunStatus.SUCCEEDED)
    return service


def _persist_stage(
    service: PersistenceService,
    root: Path,
    stage: RunStage,
    *,
    eligible: bool = True,
) -> FilterStageHandoff:
    source = service.runs.get("screening-run")
    assert source is not None
    run_id = f"{stage.value}-run"
    service.create_run(
        configuration_id=source.configuration_id,
        strategy_id=source.strategy_id,
        strategy_version=source.strategy_version,
        stage=stage,
        run_id=run_id,
        status=RunStatus.RUNNING,
    )
    execution = {"kind": "fixture"}
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
                assumptions_json=canonical_json(execution),
            )
        )
    content = canonical_json(
        {"stage": stage.value, "eligible_to_progress": eligible}
    ).encode("utf-8")
    location = f"artifacts/{run_id}/evidence.json"
    target = root / location
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    service.register_artifact(
        run_id=run_id,
        artifact_type=ArtifactType.VALIDATION_EVIDENCE,
        logical_name=f"{stage.value}_evidence",
        media_type="application/json",
        format="json",
        location=location,
        content=content,
    )
    service.persist_run_manifest(service.build_run_manifest(run_id))
    service.transition_run(run_id, RunStatus.SUCCEEDED)
    return FilterStageHandoff(
        stage=stage,
        run_id=run_id,
        status="passed" if eligible else "failed",
        eligible_to_progress=eligible,
        evidence_identity=f"evidence-{stage.value}",
        reasons=() if eligible else (f"{stage.value} failed",),
    )


def test_screened_out_run_stops_without_invoking_later_filters(tmp_path: Path) -> None:
    service = _service(tmp_path, screening_status="screened_out")
    called = False

    def should_not_run(_context):
        nonlocal called
        called = True
        raise AssertionError("downstream filter must not run")

    adapters = {stage: should_not_run for stage in VALIDATION_STAGE_ORDER}
    outcome = FactoryFilterChainService(service).run(
        screening_run_id="screening-run",
        stage_adapters=adapters,
        protected_test_gate=lambda _context: (_ for _ in ()).throw(
            AssertionError("protected gate must not run")
        ),
    )

    assert outcome.status == "screened_out"
    assert outcome.stopped_at == "screening"
    assert outcome.reasons == ("minimum return not met",)
    assert called is False
    service.close()


def test_survivor_advances_in_fixed_order_using_only_persisted_handoffs(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts-root"
    calls: list[tuple[str, str]] = []

    def adapter(stage: RunStage):
        def execute(context):
            calls.append((stage.value, context.previous_run_id))
            return _persist_stage(service, root, stage)

        return execute

    outcome = FactoryFilterChainService(service).run(
        screening_run_id="screening-run",
        stage_adapters={stage: adapter(stage) for stage in VALIDATION_STAGE_ORDER},
        protected_test_gate=lambda context: ProtectedTestGate(
            status="passed",
            eligible_to_execute=True,
            evidence_identity="lockbox-prerequisites",
            reasons=(),
        ),
    )

    assert calls == [
        ("oos", "screening-run"),
        ("walk_forward", "oos-run"),
        ("robustness", "walk_forward-run"),
        ("monte_carlo", "robustness-run"),
    ]
    assert outcome.status == "ready_for_protected_test"
    assert tuple(item.stage for item in outcome.completed) == VALIDATION_STAGE_ORDER
    assert "separate authority" in outcome.reasons[0]
    service.close()


def test_failure_stops_before_the_next_stage_and_gate(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = tmp_path / "artifacts-root"
    called: list[str] = []

    def adapter(stage: RunStage, *, eligible: bool = True):
        def execute(_context):
            called.append(stage.value)
            return _persist_stage(service, root, stage, eligible=eligible)

        return execute

    adapters = {
        RunStage.OOS: adapter(RunStage.OOS),
        RunStage.WALK_FORWARD: adapter(RunStage.WALK_FORWARD, eligible=False),
        RunStage.ROBUSTNESS: adapter(RunStage.ROBUSTNESS),
        RunStage.MONTE_CARLO: adapter(RunStage.MONTE_CARLO),
    }
    outcome = FactoryFilterChainService(service).run(
        screening_run_id="screening-run",
        stage_adapters=adapters,
        protected_test_gate=lambda _context: (_ for _ in ()).throw(
            AssertionError("protected gate must not run")
        ),
    )

    assert called == ["oos", "walk_forward"]
    assert outcome.status == "stopped"
    assert outcome.stopped_at == "walk_forward"
    assert outcome.reasons == ("walk_forward failed",)
    service.close()


def test_unpersisted_or_mismatched_handoff_fails_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def missing(_context):
        return FilterStageHandoff(
            stage=RunStage.OOS,
            run_id="not-persisted",
            status="passed",
            eligible_to_progress=True,
            evidence_identity="claimed-evidence",
        )

    adapters = {stage: missing for stage in VALIDATION_STAGE_ORDER}
    with pytest.raises(ValueError, match="handoff run is not persisted"):
        FactoryFilterChainService(service).run(
            screening_run_id="screening-run",
            stage_adapters=adapters,
            protected_test_gate=lambda _context: ProtectedTestGate(
                status="failed",
                eligible_to_execute=False,
                evidence_identity="gate",
            ),
        )
    service.close()
