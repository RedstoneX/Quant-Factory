"""Route- and disclosure-gated Compare history hydration."""

from __future__ import annotations

from pathlib import Path

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate

from dashboard.compare_query import parse_compare_search
from dashboard.routing import active_route
from orchestration import FixtureRunService


def register_compare_history_callback(
    app: Dash,
    *,
    runs: FixtureRunService,
    artifact_root: Path,
) -> None:
    @app.callback(
        Output("find-compare-grid", "rowData"),
        Input("compare-run-finder-disclosure", "open"),
        Input("refresh-comparisons", "n_clicks"),
        State("url", "pathname"),
        Input("url", "search"),
    )
    def refresh_find_compare_rows(
        finder_is_open: bool,
        _: int,
        pathname: str | None,
        search: str | None,
    ):
        if not active_route(pathname, "/research/compare-backtests") or not finder_is_open:
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
