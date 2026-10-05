"""Focused regressions for route- and disclosure-gated dashboard history."""

from pathlib import Path

import pytest
from dash.exceptions import PreventUpdate

from dashboard.app import create_app
from tests.test_dashboard import (
    _DashboardRunService,
    _callback_function,
    _resolved_layout,
    _saved_configuration,
    _walk_components,
)


class _HistoryCountingRunService(_DashboardRunService):
    def __init__(self) -> None:
        super().__init__()
        self.all_runs_queries = 0
        self.all_history_queries = 0

    def all_runs(self):
        self.all_runs_queries += 1
        return super().all_runs()

    def all_history(self, *, artifact_root: Path | None = None):
        self.all_history_queries += 1
        return super().all_history(artifact_root=artifact_root)


def test_dashboard_defers_full_history_until_results_history_is_open(tmp_path: Path) -> None:
    service = _HistoryCountingRunService()
    app = create_app(review_database=tmp_path / "lazy-history.sqlite3", run_service=service)

    app.layout()
    assert service.all_runs_queries == 0
    assert service.all_history_queries == 0

    refresh_history = _callback_function(app, "run-history-grid.rowData")
    with pytest.raises(PreventUpdate):
        refresh_history(True, 0, 0, 0, 0, 0, 0, 0, "/research/ideas")
    with pytest.raises(PreventUpdate):
        refresh_history(False, 0, 0, 0, 0, 0, 0, 0, "/research/backtest-results")
    assert service.all_history_queries == 0

    rows = refresh_history(True, 0, 0, 0, 0, 0, 0, 0, "/research/backtest-results")
    assert rows[0]["run_id"] == "run_dashboard_fixture"
    assert service.all_history_queries == 1


def test_results_history_grid_mounts_empty_then_hydrates_on_open(
    tmp_path: Path,
    monkeypatch,
) -> None:
    configuration = _saved_configuration()
    monkeypatch.setattr(
        "dashboard.app.list_saved_configurations",
        lambda database=None: (configuration,),
    )
    service = _DashboardRunService(
        initial_runs=tuple(
            _DashboardRunService()._summary(
                f"history_grid_run_{index:02d}",
                configuration.configuration_id,
                "succeeded",
            )
            for index in range(21)
        )
    )
    app = create_app(review_database=tmp_path / "reviews.json", run_service=service)

    grid = next(
        component
        for component in _walk_components(_resolved_layout(app))
        if getattr(component, "id", None) == "run-history-grid"
    )
    columns = {column["field"]: column for column in grid.columnDefs}
    rows = _callback_function(app, "run-history-grid.rowData")(
        True, 0, 0, 0, 0, 0, 0, 0, "/research/backtest-results"
    )

    assert grid.rowData == []
    assert len(rows) == 21
    assert rows[-1]["run_id"] == "history_grid_run_20"
    assert rows[0]["stage"] == "Fixture backtest"
    assert rows[0]["status"] == "Succeeded"
    assert columns["run_id"]["hide"] is True
    assert columns["instrument"]["filter"] == "agTextColumnFilter"
    assert columns["total_return"]["filter"] == "agNumberColumnFilter"
    assert grid.getRowId == "params.data.run_id"
    assert grid.selectedRows == []
