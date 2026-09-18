"""Compare Backtests page callback ownership."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from dashboard.application import _active_route
from dashboard.compare_adapter import CompareDashboardAdapter
from dashboard.components.compare_results import (
    compare_empty,
    compare_failure,
    compare_results,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from dashboard.pages.compare_backtests import comparison_selector_options
from orchestration import FixtureRunService


OWNED_STATE = {
    "comparison_selection": "comparison-run-selector.value",
}


def register_compare_backtests_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    dashboard_database: str | Path,
    artifact_root: Path,
    compare_adapter: CompareDashboardAdapter | None = None,
) -> None:
    """Register callbacks owned by the Compare Backtests route."""

    persisted_compare = compare_adapter or CompareDashboardAdapter(
        database=dashboard_database,
        artifact_root=artifact_root,
        detail_adapter=detail_adapter,
    )

    @app.callback(
        Output("comparison-run-selector", "options"),
        Input("refresh-comparisons", "n_clicks"),
        Input("url", "pathname"),
    )
    def refresh_comparison_selector_options(
        _: int,
        pathname: str | None = "/research/compare-backtests",
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        return comparison_selector_options(runs.recent_runs(limit=20))

    @app.callback(
        Output("run-comparison-output", "children"),
        Output("run-comparison-output", "className"),
        Input("compare-selected-runs", "n_clicks"),
        Input("refresh-comparisons", "n_clicks"),
        Input("url", "pathname"),
        State("comparison-run-selector", "value"),
    )
    def compare_selected_runs(
        _compare_clicks: int,
        _refresh_clicks: int,
        pathname: str | None,
        run_ids: list[str] | tuple[str, ...] | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        selected = tuple(str(run_id) for run_id in (run_ids or ()))
        if not selected:
            return compare_empty(), "run-comparison-output"
        try:
            comparison = persisted_compare.compare(selected)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            return compare_failure(selected, str(exc)), "run-comparison-output"
        return compare_results(comparison), "run-comparison-output"
