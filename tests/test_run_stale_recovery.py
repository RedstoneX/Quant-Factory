"""Fail-closed stale-run recovery tests for the ADR 0011 claim boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestration import (
    DurableResearchLaunchService,
    FixtureRunService,
    ResearchLaunchRequest,
    RunServiceError,
    new_dispatcher_instance_id,
)
from persistence import (
    EventSeverity,
    PersistenceService,
    ResearchLaunchOperation,
    ResearchSubmissionState,
    RunEventType,
    RunStage,
    RunStatus,
)
from tests.test_run_service import _configuration


STALE_BEFORE = "2025-01-01T00:00:00Z"
OLD = "2024-01-01T00:00:00Z"
FRESH = "2025-01-01T00:00:00Z"


def _create_run(
    database: Path,
    configuration_id: str,
    *,
    run_id: str,
    status: RunStatus,
    old: bool,
    attempts: int = 0,
) -> None:
    persistence = PersistenceService(database)
    try:
        configuration = persistence.configurations.get(configuration_id)
        assert configuration is not None
        persistence.create_run_with_operator_event(
            configuration_id=configuration_id,
            strategy_id=configuration.strategy_id,
            strategy_version=configuration.strategy_version,
            stage=RunStage.FIXTURE,
            run_id=run_id,
            status=RunStatus.CREATED,
            environment={"prefect_flow_run_id": f"prefect-{run_id}"},
            event_type=RunEventType.RUN_CREATED,
            severity=EventSeverity.INFO,
            message="Run created for stale recovery test.",
        )
        if status == RunStatus.SUCCEEDED:
            persistence.transition_run_with_operator_event(
                run_id=run_id,
                status=RunStatus.RUNNING,
                event_type=RunEventType.RUN_STARTED,
                severity=EventSeverity.INFO,
                message="Run entered running for stale recovery test.",
            )
        if status != RunStatus.CREATED:
            event_type = {
                RunStatus.RUNNING: RunEventType.RUN_STARTED,
                RunStatus.SUCCEEDED: RunEventType.RUN_SUCCEEDED,
                RunStatus.FAILED: RunEventType.RUN_FAILED,
                RunStatus.CANCELLED: RunEventType.RUN_CANCELLED,
            }[status]
            persistence.transition_run_with_operator_event(
                run_id=run_id,
                status=status,
                event_type=event_type,
                severity=EventSeverity.INFO,
                message=f"Run entered {status.value} for stale recovery test.",
            )
        for _ in range(attempts):
            persistence.increment_run_attempt(run_id)
        if old:
            persistence.connection.execute(
                "UPDATE experiment_runs SET created_at=?, started_at=CASE WHEN started_at IS NULL THEN NULL ELSE ? END WHERE run_id=?",
                (OLD, OLD, run_id),
            )
            persistence.connection.commit()
    finally:
        persistence.close()

def test_age_only_recovery_never_mutates_stale_created_or_running_runs(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(
        database,
        configuration_id,
        run_id="qf-stale-created",
        status=RunStatus.CREATED,
        old=True,
    )
    _create_run(
        database,
        configuration_id,
        run_id="qf-stale-running",
        status=RunStatus.RUNNING,
        old=True,
        attempts=2,
    )
    service = FixtureRunService(database=database)
    before = {
        run_id: (service.get_run(run_id), service.events_for_run(run_id))
        for run_id in ("qf-stale-created", "qf-stale-running")
    }

    with pytest.raises(RunServiceError, match="age-only fixture recovery is disabled"):
        service.recover_stale_fixture_runs(stale_before=STALE_BEFORE)

    for run_id, expected in before.items():
        assert (service.get_run(run_id), service.events_for_run(run_id)) == expected


def test_age_only_recovery_never_mutates_fresh_or_terminal_runs(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(
        database,
        configuration_id,
        run_id="qf-fresh-created",
        status=RunStatus.CREATED,
        old=False,
    )
    _create_run(
        database,
        configuration_id,
        run_id="qf-fresh-running",
        status=RunStatus.RUNNING,
        old=False,
    )
    for status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
        _create_run(
            database,
            configuration_id,
            run_id=f"qf-terminal-{status.value}",
            status=status,
            old=True,
        )
    persistence = PersistenceService(database)
    try:
        persistence.connection.execute(
            "UPDATE experiment_runs SET created_at=?, started_at=? WHERE run_id='qf-fresh-created'",
            (FRESH, None),
        )
        persistence.connection.execute(
            "UPDATE experiment_runs SET created_at=?, started_at=? WHERE run_id='qf-fresh-running'",
            (FRESH, FRESH),
        )
        persistence.connection.execute(
            "UPDATE experiment_runs SET error_summary=? WHERE run_id='qf-terminal-failed'",
            ("Fixture execution timed out after 1 seconds.",),
        )
        persistence.connection.execute(
            "UPDATE experiment_runs SET error_summary=? WHERE run_id='qf-terminal-cancelled'",
            ("Run cancelled after fixture acknowledgement.",),
        )
        persistence.events.append(
            run_id="qf-terminal-failed",
            event_type=RunEventType.RUN_TIMED_OUT,
            severity=EventSeverity.ERROR,
            message="Fixture execution exceeded its 1-second timeout.",
        )
        persistence.connection.commit()
        before = {run.run_id: run for run in persistence.runs.list()}
        before_events = {
            run_id: persistence.events.list_for_run(run_id) for run_id in before
        }
    finally:
        persistence.close()

    service = FixtureRunService(database=database)
    with pytest.raises(RunServiceError, match="age-only fixture recovery is disabled"):
        service.recover_stale_fixture_runs(stale_before=STALE_BEFORE)

    persistence = PersistenceService(database)
    try:
        for run_id, expected in before.items():
            assert persistence.runs.get(run_id) == expected
            assert persistence.events.list_for_run(run_id) == before_events[run_id]
            assert persistence.results.list_parameter_results(run_id) == ()
            assert persistence.results.list_artifacts(run_id) == ()
    finally:
        persistence.close()


def test_process_exit_evidence_recovers_only_the_exact_invoking_claim(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    launch_key = "launch_stale_claim_0001"
    dispatcher_id = new_dispatcher_instance_id()
    claims = DurableResearchLaunchService(database=database)
    claim = claims.claim(
        idempotency_key=launch_key,
        request=ResearchLaunchRequest(
            operation=ResearchLaunchOperation.RUN_TEST,
            configuration_id=configuration_id,
        ),
    )
    decision = claims.begin_dispatch(
        idempotency_key=launch_key,
        dispatcher_instance_id=dispatcher_id,
    )
    assert decision.should_invoke is True
    assert decision.submission.state == ResearchSubmissionState.INVOKING

    invocations: list[str] = []

    def forbidden_launcher(**_kwargs):
        invocations.append("invoked")
        pytest.fail("recovery must never launch replacement research work")

    service = FixtureRunService(database=database, fixture_launcher=forbidden_launcher)

    with pytest.raises(RunServiceError, match="age-only fixture recovery is disabled"):
        service.recover_stale_fixture_runs(stale_before="not-a-timestamp")
    still_invoking = claims.get(launch_key)
    assert still_invoking is not None
    assert still_invoking.state == ResearchSubmissionState.INVOKING

    recovered = service.recover_invoking_after_process_exit(
        idempotency_key=launch_key,
        departed_dispatcher_instance_id=dispatcher_id,
        process_exit_evidence_reference="process-exit-proof:stale-recovery-test",
    )

    assert recovered.state == ResearchSubmissionState.SUBMISSION_UNKNOWN
    assert recovered.unknown_evidence_reference == (
        "process-exit-proof:stale-recovery-test"
    )
    assert service.get_run(claim.run.run_id).status == RunStatus.CREATED.value
    assert [event.event_type for event in service.events_for_run(claim.run.run_id)] == [
        RunEventType.RUN_CREATED.value
    ]
    assert invocations == []

    replay = service.recover_invoking_after_process_exit(
        idempotency_key=launch_key,
        departed_dispatcher_instance_id=dispatcher_id,
        process_exit_evidence_reference="process-exit-proof:stale-recovery-test",
    )
    assert replay == recovered
    assert invocations == []
