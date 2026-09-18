"""Focused Slice 18C-3 tests for deterministic stale fixture-run recovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from persistence import EventSeverity, PersistenceService, RunEventType, RunStage, RunStatus
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

def test_stale_created_and_running_runs_recover_once_with_ordered_events(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(database, configuration_id, run_id="qf-stale-created", status=RunStatus.CREATED, old=True)
    _create_run(
        database,
        configuration_id,
        run_id="qf-stale-running",
        status=RunStatus.RUNNING,
        old=True,
        attempts=2,
    )
    service = FixtureRunService(database=database)

    recovered = service.recover_stale_fixture_runs(stale_before=STALE_BEFORE)

    assert {run.run_id for run in recovered} == {"qf-stale-created", "qf-stale-running"}
    created = service.get_run("qf-stale-created")
    running = service.get_run("qf-stale-running")
    assert created is not None and running is not None
    assert created.status == RunStatus.FAILED.value
    assert running.status == RunStatus.FAILED.value
    assert created.error_summary == "Fixture run remained created beyond the stale recovery cutoff."
    assert running.error_summary == "Fixture run remained running beyond the stale recovery cutoff."
    assert created.started_at is None
    assert running.started_at == OLD
    assert running.attempt_count == 2
    persistence = PersistenceService(database)
    try:
        persisted_running = persistence.runs.get("qf-stale-running")
        assert persisted_running is not None
        assert json.loads(persisted_running.environment_json)["prefect_flow_run_id"] == "prefect-qf-stale-running"
    finally:
        persistence.close()

    assert [event.event_type for event in service.events_for_run("qf-stale-created")] == [
        "run_created",
        "run_stale_recovered",
        "run_failed",
    ]
    assert [event.event_type for event in service.events_for_run("qf-stale-running")] == [
        "run_created",
        "run_started",
        "run_stale_recovered",
        "run_failed",
    ]
    assert service.recover_stale_fixture_runs(stale_before=STALE_BEFORE) == ()


def test_fresh_and_terminal_runs_are_unchanged_by_recovery(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    _create_run(database, configuration_id, run_id="qf-fresh-created", status=RunStatus.CREATED, old=False)
    _create_run(database, configuration_id, run_id="qf-fresh-running", status=RunStatus.RUNNING, old=False)
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
    assert service.recover_stale_fixture_runs(stale_before=STALE_BEFORE) == ()

    persistence = PersistenceService(database)
    try:
        for run_id, expected in before.items():
            assert persistence.runs.get(run_id) == expected
            assert persistence.events.list_for_run(run_id) == before_events[run_id]
            assert persistence.results.list_parameter_results(run_id) == ()
            assert persistence.results.list_artifacts(run_id) == ()
    finally:
        persistence.close()


def test_recovery_requires_an_explicit_utc_cutoff(tmp_path: Path) -> None:
    database, _ = _configuration(tmp_path)
    service = FixtureRunService(database=database)

    with pytest.raises(ValueError, match="stale_before"):
        service.recover_stale_fixture_runs(stale_before="not-a-timestamp")
