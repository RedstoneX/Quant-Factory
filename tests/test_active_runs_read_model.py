"""Focused proof for the bounded current-operations query."""

from types import SimpleNamespace

import orchestration.active_runs_read_model as active_read_model
from persistence import RunStatus


def test_active_run_read_model_queries_only_active_statuses(monkeypatch) -> None:
    calls: list[RunStatus] = []
    closed: list[bool] = []
    records = {
        RunStatus.CREATED: (SimpleNamespace(run_id="queued", created_at="2026-10-08T10:00:00Z"),),
        RunStatus.RUNNING: (SimpleNamespace(run_id="running", created_at="2026-10-08T11:00:00Z"),),
    }

    class FakeRuns:
        def list(self, *, status):
            calls.append(status)
            return records[status]

    class FakePersistenceService:
        runs = FakeRuns()

        def __init__(self, _database):
            pass

        def close(self):
            closed.append(True)

    monkeypatch.setattr(active_read_model, "PersistenceService", FakePersistenceService)
    monkeypatch.setattr(active_read_model, "_summary", lambda record: record)

    result = active_read_model.active_run_summaries("unused.sqlite")

    assert [record.run_id for record in result] == ["running", "queued"]
    assert calls == [RunStatus.CREATED, RunStatus.RUNNING]
    assert closed == [True]
