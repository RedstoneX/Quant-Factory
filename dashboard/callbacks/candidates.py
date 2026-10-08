"""Candidate Universe view-only controls."""

from __future__ import annotations

from dash import Dash, Input, Output, State

from dashboard.compare_query import compare_query_href
from dashboard.pages.compare_backtests import results_query_href


def register_candidates_callbacks(app: Dash) -> None:
    app.clientside_callback(
        """
        function (population, records) {
            const rows = records || [];
            return population === 'All' ? rows : rows.filter(row => row.population === population);
        }
        """,
        Output("candidate-universe-grid", "rowData"),
        Input("candidate-population", "value"),
        State("candidate-universe-records", "data"),
        prevent_initial_call=False,
    )
    app.clientside_callback(
        """
        function (value, options) {
            const next = Object.assign({}, options || {});
            next.quickFilterText = value || '';
            return next;
        }
        """,
        Output("candidate-universe-grid", "dashGridOptions"),
        Input("candidate-search", "value"),
        State("candidate-universe-grid", "dashGridOptions"),
        prevent_initial_call=False,
    )

    @app.callback(
        Output("candidate-selection-message", "children"),
        Output("candidate-results-link", "href"),
        Output("candidate-results-link", "style"),
        Output("candidate-compare-link", "href"),
        Output("candidate-compare-link", "style"),
        Input("candidate-universe-grid", "selectedRows"),
    )
    def selection_actions(selected_rows):
        hidden = {"display": "none"}
        run_ids = tuple(
            str(row["run_id"])
            for row in (selected_rows or ())
            if row.get("run_id")
        )
        all_survivors = bool(selected_rows) and all(
            row.get("population") == "Survivor" for row in selected_rows
        )
        if len(run_ids) == 1:
            return (
                (
                    "One survivor selected. Open its exact persisted Results record."
                    if all_survivors
                    else "One non-survivor selected. Its exact Results remain available for diagnosis."
                ),
                results_query_href(run_ids[0]),
                {},
                None,
                hidden,
            )
        if 2 <= len(run_ids) <= 4 and all_survivors:
            return (
                f"{len(run_ids)} Candidates selected. Comparison is optional and read-only.",
                None,
                hidden,
                compare_query_href(run_ids),
                {},
            )
        if 2 <= len(run_ids) <= 4:
            return (
                "Compare selected is available only when every selection is an explicit survivor.",
                None,
                hidden,
                None,
                hidden,
            )
        if len(run_ids) > 4:
            return (
                "Compare accepts two to four selections. Reduce the selection.",
                None,
                hidden,
                None,
                hidden,
            )
        return (
            "No survivor selected. Select one for exact Results or two to four for comparison.",
            None,
            hidden,
            None,
            hidden,
        )


__all__ = ["register_candidates_callbacks"]
