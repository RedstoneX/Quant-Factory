"""Find & Compare callback ownership."""

from __future__ import annotations

from pathlib import Path
import sqlite3

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from dashboard.application import _active_route
from dashboard.compare_adapter import CompareDashboardAdapter
from dashboard.compare_query import compare_query_href, parse_compare_search
from dashboard.components.compare_results import compare_empty, compare_failure, compare_results
from dashboard.pages.compare_backtests import results_query_href
from dashboard.run_detail_adapter import RunDetailDashboardAdapter
from orchestration import FixtureRunService


OWNED_STATE = {"comparison_selection": "find-compare-grid.selectedRows"}


def _requested_rows(
    rows: list[dict[str, object]] | None,
    run_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    by_id = {str(row.get("run_id")): row for row in (rows or ())}
    return [by_id[run_id] for run_id in run_ids if run_id in by_id]


def _secondary_selection_details(
    selected_rows: list[dict[str, object]] | None,
) -> str:
    rows = selected_rows or []
    statuses = sorted({str(row.get("status")) for row in rows if row.get("status")})
    reviews = sorted({str(row.get("review")) for row in rows if row.get("review")})
    metric_bases = sorted(
        {str(row.get("metric_basis")) for row in rows if row.get("metric_basis")}
    )
    details: list[str] = []
    if statuses:
        details.append(f"Status: {', '.join(statuses)}")
    if reviews:
        details.append(f"Review: {', '.join(reviews)}")
    if metric_bases:
        details.append(f"Metric basis: {', '.join(metric_bases)}")
    return f" · {' · '.join(details)}" if details else ""


def register_compare_backtests_callbacks(
    app: Dash,
    *,
    runs: FixtureRunService,
    detail_adapter: RunDetailDashboardAdapter,
    dashboard_database: str | Path,
    artifact_root: Path,
    compare_adapter: CompareDashboardAdapter | None = None,
) -> None:
    """Register callbacks owned by the Find & Compare route."""

    persisted_compare = compare_adapter or CompareDashboardAdapter(
        database=dashboard_database,
        artifact_root=artifact_root,
        detail_adapter=detail_adapter,
    )

    app.clientside_callback(
        """
        function (value, options) {
            const next = Object.assign({}, options || {});
            next.quickFilterText = value || '';
            return next;
        }
        """,
        Output("find-compare-grid", "dashGridOptions"),
        Input("find-compare-search", "value"),
        State("find-compare-grid", "dashGridOptions"),
        prevent_initial_call=False,
    )

    @app.callback(
        Output("find-compare-search", "value"),
        Output("find-compare-grid", "filterModel"),
        Output("find-compare-grid", "resetColumnState"),
        Input("find-compare-reset-view", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_find_compare_view(_clicks: int):
        return "", {}, True

    @app.callback(
        Output("find-compare-grid-count", "children"),
        Input("find-compare-grid", "virtualRowData"),
        Input("find-compare-grid", "rowData"),
        Input("find-compare-grid", "selectedRows"),
    )
    def find_compare_counts(
        visible_rows: list[dict[str, object]] | None,
        all_rows: list[dict[str, object]] | None,
        selected_rows: list[dict[str, object]] | None,
    ) -> str:
        matched = len(visible_rows) if visible_rows is not None else len(all_rows or ())
        selected = len(selected_rows or ())
        return f"{matched:,} matched · {selected:,} selected"

    @app.callback(
        Output("find-compare-grid", "rowData"),
        Input("refresh-comparisons", "n_clicks"),
        Input("url", "pathname"),
        Input("url", "search"),
    )
    def refresh_find_compare_rows(
        _: int,
        pathname: str | None,
        search: str | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        rows = list(runs.all_history(artifact_root=artifact_root))
        request = parse_compare_search(search)
        if request.valid:
            existing = {str(row.get("run_id")) for row in rows}
            rows = [
                *(
                    {
                        "run_id": run_id,
                        "created_at": "Unavailable",
                        "instrument": "Unavailable",
                        "interval": "Unavailable",
                        "strategy": "Unavailable",
                        "status": "Unavailable",
                        "review": "Unavailable",
                        "evidence": "Persisted test unavailable",
                        "metric_basis": "Top-ranked variation unavailable",
                    }
                    for run_id in request.run_ids
                    if run_id not in existing
                ),
                *rows,
            ]
        return rows

    @app.callback(
        Output("find-compare-grid", "selectedRows"),
        Input("url", "search"),
        Input("url", "pathname"),
        State("find-compare-grid", "rowData"),
    )
    def hydrate_exact_selection(
        search: str | None,
        pathname: str | None,
        rows: list[dict[str, object]] | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        request = parse_compare_search(search)
        if request.requested and not request.valid:
            return []
        if request.valid:
            return _requested_rows(rows, request.run_ids)
        raise PreventUpdate

    @app.callback(
        Output("find-compare-selection-message", "children"),
        Output("find-compare-selection-message", "className"),
        Output("find-compare-results-link", "href"),
        Output("find-compare-results-link", "style"),
        Output("find-compare-exact-link", "href"),
        Output("find-compare-exact-link", "style"),
        Input("find-compare-grid", "selectedRows"),
        Input("url", "search"),
        State("url", "pathname"),
    )
    def selection_actions(
        selected_rows: list[dict[str, object]] | None,
        search: str | None,
        pathname: str | None,
    ):
        if not _active_route(pathname, "/research/compare-backtests"):
            raise PreventUpdate
        request = parse_compare_search(search)
        hidden = {"display": "none"}
        if request.requested and not request.valid:
            return (
                request.error,
                "field-help compact-field-help error-state",
                None,
                hidden,
                None,
                hidden,
            )
        run_ids = tuple(
            str(row["run_id"])
            for row in (selected_rows or ())
            if row.get("run_id") is not None
        )
        if (
            request.valid
            and len(run_ids) == len(request.run_ids)
            and set(run_ids) == set(request.run_ids)
        ):
            run_ids = request.run_ids
        details = _secondary_selection_details(selected_rows)
        if len(run_ids) == 1:
            return (
                "One saved test selected. Open its exact Results page when ready."
                f"{details}",
                "field-help compact-field-help",
                results_query_href(run_ids[0]),
                {},
                None,
                hidden,
            )
        if 2 <= len(run_ids) <= 4:
            href = compare_query_href(run_ids)
            return (
                f"{len(run_ids)} saved tests selected. Open their exact comparison "
                f"when ready.{details}",
                "field-help compact-field-help",
                None,
                hidden,
                href,
                {},
            )
        if not run_ids:
            reason = "Select one saved test to open Results, or two to four to compare."
        else:
            reason = (
                f"{len(run_ids)} saved tests are selected. Compare accepts two to "
                "four; reduce the selection."
            )
        return reason, "field-help compact-field-help", None, hidden, None, hidden

    @app.callback(
        Output("run-comparison-output", "children"),
        Output("run-comparison-output", "className"),
        Input("refresh-comparisons", "n_clicks"),
        Input("url", "pathname"),
        Input("url", "search"),
    )
    def render_exact_comparison(
        _refresh_clicks: int,
        pathname: str | None,
        search: str | None,
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
        if not request.valid:
            return compare_empty(), "run-comparison-output"
        try:
            comparison = persisted_compare.compare(request.run_ids)
        except (KeyError, OSError, RuntimeError, TypeError, ValueError, sqlite3.Error) as exc:
            return compare_failure(request.run_ids, str(exc)), "run-comparison-output"
        return compare_results(comparison), "run-comparison-output"
