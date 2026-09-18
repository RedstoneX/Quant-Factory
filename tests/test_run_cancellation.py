"""Focused Slice 18C-2b tests for cooperative fixture cancellation."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from persistence import PersistenceService, RunStatus
from persistence.service import RunCompletionRejectedError
from prefect_spike.fixture_flow import (
    ControlledFixtureCancellation,
    PrefectFixtureResult,
    PrefectRunReference,
    _create_or_reference_run,
    _persist_fixture_result,
    acknowledge_fixture_cancellation,
    reconcile_quant_factory_run_status,
)
from tests.test_run_service import _configuration


def test_active_fixture_cooperatively_cancels_and_blocks_late_completion(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_launcher(**kwargs):
        persistence = PersistenceService(kwargs["database_path"])
        try:
            _create_or_reference_run(
                persistence,
                configuration_id=kwargs["configuration_id"],
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_reference=PrefectRunReference(flow_run_id="prefect-cancel-run"),
                reference_source="controlled_cancellation_test",
            )
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Running",
            )
            started.set()
            assert release.wait(timeout=5)
            try:
                acknowledge_fixture_cancellation(
                    persistence,
                    quant_factory_run_id=kwargs["quant_factory_run_id"],
                )
            except ControlledFixtureCancellation:
                with pytest.raises(RunCompletionRejectedError, match="cannot accept completion"):
                    _persist_fixture_result(
                        persistence,
                        quant_factory_run_id=kwargs["quant_factory_run_id"],
                        configuration_id=kwargs["configuration_id"],
                        prefect_flow_run_id="prefect-cancel-run",
                        deterministic_value=1729,
                        attempt_count=1,
                    )
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Completed",
            )
            return PrefectFixtureResult(
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_flow_run_id="prefect-cancel-run",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()
            finished.set()

    service = FixtureRunService(database=database, fixture_launcher=blocking_launcher)
    launch_errors: list[BaseException] = []

    def launch() -> None:
        try:
            service.launch_fixture(configuration_id=configuration_id, run_id="qf-cancel")
        except BaseException as exc:  # assertion follows below
            launch_errors.append(exc)

    worker = threading.Thread(target=launch)
    worker.start()
    assert started.wait(timeout=5)

    requested = service.request_fixture_cancellation("qf-cancel")
    repeated = service.request_fixture_cancellation("qf-cancel")
    assert requested.status == RunStatus.RUNNING.value
    assert repeated.status == RunStatus.RUNNING.value
    assert [event.event_type for event in service.events_for_run("qf-cancel")] == [
        "run_created",
        "run_started",
        "run_cancellation_requested",
    ]

    release.set()
    assert finished.wait(timeout=5)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert launch_errors == []

    run = service.get_run("qf-cancel")
    assert run is not None
    assert run.status == RunStatus.CANCELLED.value
    assert run.attempt_count == 1
    assert run.prefect_flow_run_id == "prefect-cancel-run"
    assert run.prefect_flow_run_id != run.run_id
    assert [event.event_type for event in service.events_for_run("qf-cancel")] == [
        "run_created",
        "run_started",
        "run_cancellation_requested",
        "run_cancelled",
    ]

    persistence = PersistenceService(database)
    try:
        assert persistence.results.list_parameter_results("qf-cancel") == ()
        assert persistence.results.list_artifacts("qf-cancel") == ()
    finally:
        persistence.close()
    events = service.events_for_run("qf-cancel")
    assert [event.event_type for event in events].count("run_cancellation_requested") == 1
    assert [event.event_type for event in events].count("run_cancelled") == 1
    assert "run_succeeded" not in [event.event_type for event in events]


def test_cancellation_of_unknown_or_terminal_run_is_safe(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database)

    with pytest.raises(KeyError, match="unknown run"):
        service.request_fixture_cancellation("missing-run")

    from tests.test_run_service import _launcher

    service = FixtureRunService(database=database, fixture_launcher=_launcher)
    service.launch_fixture(configuration_id=configuration_id, run_id="qf-cancel-terminal")
    before = service.events_for_run("qf-cancel-terminal")
    terminal = service.request_fixture_cancellation("qf-cancel-terminal")

    assert terminal.status == RunStatus.SUCCEEDED.value
    assert service.events_for_run("qf-cancel-terminal") == before
