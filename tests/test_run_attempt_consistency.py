"""Regression coverage for the authoritative Slice 18C-1 attempt count."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

from orchestration import FixtureRunService
from persistence import PersistenceService
from tests.test_run_service import _configuration, _launcher


def test_live_style_task_retry_count_is_reconciled_to_run_attempt_count(
    tmp_path: Path,
) -> None:
    database, configuration_id = _configuration(tmp_path)

    def task_retry_style_launcher(**kwargs):
        result = _launcher(**kwargs)
        return replace(result, attempt_count=2)

    service = FixtureRunService(database=database, fixture_launcher=task_retry_style_launcher)
    result = service.launch_fixture(
        configuration_id=configuration_id,
        run_id="qf-attempt-consistency",
    )

    assert result.run.attempt_count == 1
    assert result.prefect_result is not None
    assert result.prefect_result.attempt_count == 1

    persistence = PersistenceService(database)
    try:
        run = persistence.runs.get("qf-attempt-consistency")
        assert run is not None
        assert run.attempt_count == 1
        row = persistence.results.list_parameter_results("qf-attempt-consistency")[0]
        assert json.loads(row.metrics_json)["attempt_count"] == 1
    finally:
        persistence.close()
