"""Deferred Results report tab hydration."""

from __future__ import annotations

from typing import Any, Callable

from dash import Dash, Input, Output, State, html
from dash.exceptions import PreventUpdate


def register_results_tab_callbacks(
    app: Dash,
    *,
    detail_adapter: Any,
    active_route: Callable[[str | None, str], bool],
    selected_run_id: Callable[[str | None], str | None],
    requested_parameter_row_id: Callable[[str | None], tuple[bool, str | None]],
    tab_content: Callable[..., Any],
) -> None:
    overview = getattr(
        detail_adapter,
        "selected_run_overview",
        detail_adapter.selected_run_detail,
    )

    @app.callback(
        Output("results-report-tab-content", "children"),
        Input("run-detail-analysis-tabs", "value"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        State("url", "search"),
        prevent_initial_call=True,
    )
    def load_results_report_tab(
        active_tab: str | None,
        run_id: str | None,
        pathname: str | None,
        search: str | None,
    ):
        if not active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        run_id = selected_run_id(run_id)
        detail = None
        if run_id:
            try:
                detail = overview(run_id)
            except (KeyError, RuntimeError, ValueError) as exc:
                return html.P(
                    f"Run detail retrieval failed: {exc}",
                    className="error-state",
                )
        _, parameter_row_id = requested_parameter_row_id(search)
        return tab_content(
            active_tab,
            detail,
            selected_parameter_row_id=parameter_row_id,
        )
