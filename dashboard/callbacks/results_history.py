"""Deferred persisted-run history hydration."""

from __future__ import annotations

from typing import Any, Callable

from dash import Dash, Input, Output, State
from dash.exceptions import PreventUpdate


def register_results_history_callbacks(
    app: Dash,
    *,
    runs: Any,
    artifact_root: Any,
    active_route: Callable[[str | None, str], bool],
    fallback_rows: Callable[[Any], Any],
    grid: Callable[[tuple[dict[str, object], ...]], Any],
) -> None:
    @app.callback(
        Output("run-history-grid-host", "children"),
        Input("results-run-history-toggle", "n_clicks"),
        Input("refresh-runs", "n_clicks"),
        Input("launch-message", "children", allow_optional=True),
        Input("historical-launch-message", "children", allow_optional=True),
        Input("reproduction-message", "children", allow_optional=True),
        Input("review-message", "children", allow_optional=True),
        Input("cancellation-message", "children", allow_optional=True),
        Input("stale-recovery-message", "children"),
        State("url", "pathname"),
    )
    def refresh_run_history(toggle_clicks: int | None, *values: object):
        pathname = values[-1] if values else None
        if (
            not active_route(
                pathname if isinstance(pathname, str) else None,
                "/research/backtest-results",
            )
            or not toggle_clicks
            or toggle_clicks % 2 == 0
        ):
            raise PreventUpdate
        rows = (
            runs.all_history(artifact_root=artifact_root)
            if hasattr(runs, "all_history")
            else fallback_rows(runs)
        )
        return grid(tuple(rows))
