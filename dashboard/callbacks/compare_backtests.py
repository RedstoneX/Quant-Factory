"""Compare Backtests page callback ownership."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from dash import Dash, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate

from dashboard.application import (
    _active_route,
    _run_comparison_panel,
)
from dashboard.compare_adapter import CompareDashboardAdapter
from dashboard.components.compare_results import (
    compare_empty,
    compare_failure,
    compare_results,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from dashboard.pages.compare_backtests import comparison_selector_options
from orchestration import FixtureRunService, RunServiceError


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
        Input("refresh-runs", "n_clicks"),
        Input("url", "pathname"),
    )
    def refresh_comparison_selector_options(
        _: int,
        __: int,
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
        Input("review-message", "children"),
        State("comparison-run-selector", "value"),
    )
    def compare_selected_runs(
        _compare_clicks: int,
        _refresh_clicks: int,
        pathname: str | None,
        _review_message: object,
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

    # Transitional Results ownership: preserve this accepted mutating callback
    # unchanged until its separately owned module migration is authorized.
    @app.callback(
        Output("reproduction-message", "children"),
        Output("reproduction-message", "className"),
        Output("run-comparison-output", "children", allow_duplicate=True),
        Output("run-comparison-output", "className", allow_duplicate=True),
        Output("comparison-run-selector", "value", allow_duplicate=True),
        Input("reproduce-selected-run", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def reproduce_selected_run(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None = "/research/backtest-results",
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        if not run_id:
            return (
                "No persisted run is selected for reproduction.",
                "reproduction-message error-state",
                html.Div(
                    "Run reproduction failed: no persisted run is selected.",
                    className="error-state",
                ),
                "run-comparison-output",
                no_update,
            )

        try:
            result = runs.reproduce_fixture_run(
                run_id,
                artifact_root=artifact_root,
            )
        except (KeyError, ValueError, RuntimeError, RunServiceError) as exc:
            return (
                f"Run reproduction failed: {exc}",
                "reproduction-message error-state",
                html.Div(
                    f"Run reproduction failed: {exc}",
                    className="error-state",
                ),
                "run-comparison-output",
                no_update,
            )

        notes = html.Ul([html.Li(note) for note in result.notes])
        return (
            html.Div(
                [
                    html.Strong(
                        (
                            f"Reproduced {result.original.run_id} as "
                            f"{result.reproduction.run_id}."
                        )
                    ),
                    notes,
                ],
                **{"data-run-id": result.reproduction.run_id},
            ),
            "reproduction-message reproduction-message-success",
            _run_comparison_panel(result.comparison),
            "run-comparison-output",
            [result.original.run_id, result.reproduction.run_id],
        )
