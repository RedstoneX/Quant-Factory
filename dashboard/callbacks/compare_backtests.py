"""Compare Backtests page callback ownership."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from dash import Dash, Input, Output, State, no_update
from dash.exceptions import PreventUpdate

from dashboard.application import _active_route
from dashboard.compare_adapter import CompareDashboardAdapter
from dashboard.compare_query import compare_query_href, parse_compare_search
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
        Input("url", "search"),
    )
    def refresh_comparison_selector_options(
        _: int,
        pathname: str | None = "/research/compare-backtests",
        search: str | None = None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        options = comparison_selector_options(runs.recent_runs(limit=20))
        request = parse_compare_search(search)
        if not request.valid:
            return options
        existing = {str(option["value"]) for option in options}
        requested_options = [
            {"label": f"Requested exact test · Test {run_id}", "value": run_id}
            for run_id in request.run_ids
            if run_id not in existing
        ]
        return [*requested_options, *options]

    @app.callback(
        Output("comparison-run-selector", "value"),
        Output("comparison-query-message", "children"),
        Output("comparison-query-message", "className"),
        Output("comparison-exact-link", "href"),
        Output("comparison-exact-link", "style"),
        Input("url", "search"),
        Input("url", "pathname"),
        Input("compare-selected-runs", "n_clicks"),
        State("comparison-run-selector", "value"),
    )
    def hydrate_exact_comparison(
        search: str | None,
        pathname: str | None,
        _compare_clicks: int,
        run_ids: list[str] | tuple[str, ...] | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        request = parse_compare_search(search)
        if request.requested and not request.valid:
            return (
                [],
                request.error,
                "field-help compact-field-help error-state",
                None,
                {"display": "none"},
            )
        if request.valid:
            href = compare_query_href(request.run_ids)
            return (
                list(request.run_ids),
                "This URL controls the exact persisted tests shown below.",
                "field-help compact-field-help",
                href,
                {},
            )

        selected = tuple(str(run_id) for run_id in (run_ids or ()))
        href = compare_query_href(selected)
        return (
            no_update,
            (
                "The exact-comparison link now matches this selection."
                if href
                else "Select two to four distinct tests to create an exact link."
            ),
            "field-help compact-field-help",
            href,
            {} if href else {"display": "none"},
        )

    @app.callback(
        Output("run-comparison-output", "children"),
        Output("run-comparison-output", "className"),
        Input("compare-selected-runs", "n_clicks"),
        Input("refresh-comparisons", "n_clicks"),
        Input("url", "pathname"),
        Input("url", "search"),
        State("comparison-run-selector", "value"),
    )
    def compare_selected_runs(
        _compare_clicks: int,
        _refresh_clicks: int,
        pathname: str | None,
        search: str | None,
        run_ids: list[str] | tuple[str, ...] | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        request = parse_compare_search(search)
        if request.requested and not request.valid:
            return (
                compare_failure(
                    request.visible_tokens,
                    request.error or "Invalid query.",
                ),
                "run-comparison-output",
            )
        selected = (
            request.run_ids
            if request.valid
            else tuple(str(run_id) for run_id in (run_ids or ()))
        )
        if not selected:
            return compare_empty(), "run-comparison-output"
        try:
            comparison = persisted_compare.compare(selected)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            return compare_failure(selected, str(exc)), "run-comparison-output"
        return compare_results(comparison), "run-comparison-output"
