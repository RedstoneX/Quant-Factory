"""Focused proof for the bounded current-operations query, against a real research database."""

from pathlib import Path

import orchestration.active_runs_read_model as active_read_model
from persistence import PersistenceService, RunStage, RunStatus
from tests.test_persistence import _document, _register_strategy


def _runs(tmp_path: Path) -> Path:
    database = tmp_path / "state" / "quant_factory.sqlite3"
    service = PersistenceService(database)
    try:
        strategy = _register_strategy(service)
        configuration = service.upsert_configuration(_document(tmp_path))
        for run_id, status in (("queued", None), ("running", RunStatus.RUNNING), ("done", RunStatus.SUCCEEDED),
                               ("broken", RunStatus.FAILED)):
            service.create_run(
                configuration_id=configuration.configuration_id, strategy_id=strategy.strategy_id,
                strategy_version=strategy.strategy_version, stage=RunStage.FIXTURE, run_id=run_id,
            )
            if status is not None:
                service.transition_run(run_id, RunStatus.RUNNING)
            if status in (RunStatus.SUCCEEDED, RunStatus.FAILED):
                service.transition_run(run_id, status, error_summary="x" if status is RunStatus.FAILED else None)
    finally:
        service.close()
    return database


def test_active_run_read_model_returns_only_created_and_running_runs(tmp_path: Path) -> None:
    result = active_read_model.active_run_summaries(_runs(tmp_path))

    assert sorted(run.run_id for run in result) == ["queued", "running"]
    assert {run.status for run in result} == {"created", "running"}
    newest_first = sorted(result, key=lambda run: (run.created_at, run.run_id), reverse=True)
    assert [run.run_id for run in result] == [run.run_id for run in newest_first]
