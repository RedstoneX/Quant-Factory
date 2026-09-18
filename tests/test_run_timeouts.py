"""Focused ADR 0011 tests for bounded request-timeout ambiguity."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from orchestration import FixtureRunService
from orchestration.research_launch_claims import ResearchLaunchInvocationError
from persistence import PersistenceService, RunStatus
from prefect_spike.fixture_flow import (
    PrefectFixtureResult,
    PrefectRunReference,
    _persist_fixture_result,
    _validated_claim_boundary,
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


def test_timeout_after_ack_is_typed_and_does_not_falsely_fail_run(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    def blocking_launcher(**kwargs):
        _validated_claim_boundary(
            database_path=kwargs["database_path"],
            idempotency_key=kwargs["idempotency_key"],
            configuration_id=kwargs["configuration_id"],
            quant_factory_run_id=kwargs["quant_factory_run_id"],
            canonical_request_json=kwargs["canonical_request_json"],
            request_fingerprint=kwargs["request_fingerprint"],
            operation_kind=kwargs["operation_kind"],
            source_run_id=kwargs["source_run_id"],
            source_lineage=kwargs["source_lineage"],
            prefect_reference=PrefectRunReference(flow_run_id="prefect-timeout-run"),
        )
        persistence = PersistenceService(kwargs["database_path"])
        try:
            persistence.increment_run_attempt(kwargs["quant_factory_run_id"])
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
        with pytest.raises(ResearchLaunchInvocationError):
            service.launch_fixture(
                configuration_id=configuration_id,
                run_id="qf-timeout",
                timeout_seconds=0.01,
            )
        assert started.is_set()
        result = service.get_run("qf-timeout")
        assert result is not None
        assert result.status == RunStatus.RUNNING.value
        assert result.error_summary is None
        assert result.prefect_flow_run_id == "prefect-timeout-run"
        events = service.events_for_run("qf-timeout")
        assert [event.event_type for event in events] == ["run_created", "run_started"]
    finally:
        release.set()

    assert finished.wait(timeout=5)
    persisted = PersistenceService(database)
    try:
        run = persisted.runs.get("qf-timeout")
        assert run is not None
        assert run.status == RunStatus.SUCCEEDED
        assert run.error_summary is None
        assert len(persisted.results.list_parameter_results("qf-timeout")) == 1
        assert persisted.results.list_artifacts("qf-timeout") == ()
    finally:
        persisted.close()
    events = service.events_for_run("qf-timeout")
    assert [event.event_type for event in events] == [
        "run_created",
        "run_started",
        "run_succeeded",
    ]


def test_ordinary_success_and_acknowledged_failure_remain_truthful(tmp_path: Path) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_launcher)

    success = service.launch_fixture(configuration_id=configuration_id, run_id="qf-no-timeout-success")
    with pytest.raises(ResearchLaunchInvocationError):
        service.launch_fixture(
            configuration_id=configuration_id,
            run_id="qf-no-timeout-failure",
            fail_after_run_start=True,
        )

    assert success.run.status == RunStatus.SUCCEEDED.value
    failure = service.get_run("qf-no-timeout-failure")
    assert failure is not None and failure.status == RunStatus.FAILED.value
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
