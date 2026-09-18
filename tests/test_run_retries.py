"""Focused Slice 18C-1 tests for bounded fixture retry behavior."""

from __future__ import annotations

import json
from pathlib import Path

from orchestration import FixtureRunService
from orchestration.run_service import FixtureRetryPolicy
from persistence import PersistenceService, RunStatus
from prefect_spike.fixture_flow import deterministic_fixture_body
from tests.test_run_service import _configuration


def _retry_launcher(**kwargs):
    kwargs.pop("attempt_marker_path", None)
    return deterministic_fixture_body(
        **kwargs,
        prefect_flow_run_id=f"prefect-{kwargs['quant_factory_run_id']}",
        prefect_api_url="http://127.0.0.1:4200/api",
    )


def test_transient_failure_retries_once_then_succeeds_with_authoritative_count(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_retry_launcher)

    result = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-retry-success",
        retry_policy=FixtureRetryPolicy(max_attempts=2),
        controlled_transient_failures=1,
    )

    assert result.run.status == RunStatus.SUCCEEDED.value
    assert result.run.attempt_count == 2
    assert result.prefect_result is not None
    assert result.prefect_result.attempt_count == 2
    assert result.prefect_result.prefect_flow_run_id != result.run.run_id
    assert [event.event_type for event in service.events_for_run("qf-retry-success")] == [
        "run_created",
        "run_started",
        "run_retry_scheduled",
        "run_succeeded",
    ]

    persistence = PersistenceService(database)
    try:
        persisted = persistence.runs.get("qf-retry-success")
        assert persisted is not None
        assert persisted.attempt_count == 2
        result_row = persistence.results.list_parameter_results("qf-retry-success")[0]
        assert json.loads(result_row.metrics_json)["attempt_count"] == 2
    finally:
        persistence.close()


def test_retry_exhaustion_ends_failed_without_duplicate_lifecycle_events(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)
    service = FixtureRunService(database=database, fixture_launcher=_retry_launcher)

    result = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-retry-exhausted",
        retry_policy=FixtureRetryPolicy(max_attempts=2),
        controlled_transient_failures=2,
    )

    assert result.prefect_result is None
    assert result.run.status == RunStatus.FAILED.value
    assert result.run.attempt_count == 2
    assert [event.event_type for event in service.events_for_run("qf-retry-exhausted")] == [
        "run_created",
        "run_started",
        "run_retry_scheduled",
        "run_failed",
    ]
    assert [event.event_type for event in service.events_for_run("qf-retry-exhausted")].count(
        "run_created"
    ) == 1
    assert [event.event_type for event in service.events_for_run("qf-retry-exhausted")].count(
        "run_started"
    ) == 1
