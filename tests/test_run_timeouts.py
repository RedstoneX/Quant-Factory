"""Focused Slice 18C-2a tests for bounded terminal fixture timeouts."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from persistence import PersistenceService, RunStatus
from prefect_spike.fixture_flow import (
    PrefectFixtureResult,
    PrefectRunReference,
    _create_or_reference_run,
    _persist_fixture_result,
    reconcile_quant_factory_run_status,
)
from tests.test_run_service import _configuration, _launcher


def test_invalid_timeout_fails_before_run_creation_or_fixture_launch(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    called = False

    def launcher(**kwargs):
        nonlocal called
        called = True
        return _launcher(**kwargs)

    service = FixtureRunService(database=database, fixture_launcher=launcher)

    with pytest.raises(ValueError, match="timeout_seconds"):
        service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-invalid-timeout",
            timeout_seconds=0,
        )

    assert not called
    assert service.get_run("qf-invalid-timeout") is None


def test_timeout_fails_terminally_with_one_timeout_event_in_order(tmp_path: Path) -> None:
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
                prefect_reference=PrefectRunReference(flow_run_id="prefect-timeout-run"),
                reference_source="controlled_timeout_test",
                frozen_runtime_lineage=kwargs["frozen_runtime_lineage"],
            )
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
            reconcile_quant_factory_run_status(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                prefect_state="Running",
            )
            started.set()
            assert release.wait(timeout=5)
            _persist_fixture_result(
                persistence,
                quant_factory_run_id=kwargs["quant_factory_run_id"],
                configuration_id=kwargs["configuration_id"],
                prefect_flow_run_id="prefect-timeout-run",
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
                prefect_flow_run_id="prefect-timeout-run",
                configuration_id=kwargs["configuration_id"],
                deterministic_value=1729,
                attempt_count=1,
            )
        finally:
            persistence.close()
            finished.set()

    service = FixtureRunService(database=database, fixture_launcher=blocking_launcher)
    try:
        result = service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-timeout",
            timeout_seconds=0.01,
        )
        assert started.is_set()
        assert result.prefect_result is None
        assert result.run.status == RunStatus.FAILED.value
        assert result.run.error_summary == "Fixture execution timed out after 0.01 seconds."
        assert result.run.attempt_count == 1
        assert result.run.prefect_flow_run_id == "prefect-timeout-run"
        assert result.run.prefect_flow_run_id != result.run.run_id

        events = service.events_for_run("qf-timeout")
        assert [event.event_type for event in events] == [
            "run_created",
            "run_started",
            "run_timed_out",
            "run_failed",
        ]
        assert [event.event_type for event in events].count("run_timed_out") == 1
        assert [event.event_type for event in events].count("run_failed") == 1
        assert events[-2].message == "Fixture execution exceeded its 0.01-second timeout."
        assert "Prefect" not in events[-2].message
    finally:
        release.set()

    assert finished.wait(timeout=5)
    persisted = PersistenceService(database)
    try:
        run = persisted.runs.get("qf-timeout")
        assert run is not None
        assert run.status == RunStatus.FAILED
        assert run.error_summary == "Fixture execution timed out after 0.01 seconds."
        assert persisted.results.list_parameter_results("qf-timeout") == ()
        assert persisted.results.list_artifacts("qf-timeout") == ()
    finally:
        persisted.close()
    events = service.events_for_run("qf-timeout")
    assert [event.event_type for event in events].count("run_timed_out") == 1
    assert [event.event_type for event in events].count("run_failed") == 1
    assert "run_succeeded" not in [event.event_type for event in events]


def test_ordinary_success_failure_and_retry_remain_unchanged(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    success = service.launch_fixture(configuration_id=configuration_id, run_id="qf-no-timeout-success")
    failure = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-no-timeout-failure",
        fail_after_run_start=True,
    )

    assert success.run.status == RunStatus.SUCCEEDED.value
    assert failure.run.status == RunStatus.FAILED.value
    assert [event.event_type for event in service.events_for_run("qf-no-timeout-success")] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]
    assert [event.event_type for event in service.events_for_run("qf-no-timeout-failure")] == [
        "run_created",
        "run_started",
        "run_failed",
    ]
