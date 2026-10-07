"""Progressive chart callbacks for the selected-run Results page."""

from __future__ import annotations

from typing import Any, Callable

from dash import Dash, Input, Output, State, html
from dash.exceptions import PreventUpdate

from dashboard.run_detail_adapter import RunDetailDashboardAdapter


def register_results_chart_callbacks(
    app: Dash,
    *,
    detail_adapter: RunDetailDashboardAdapter,
    active_route: Callable[[str | None, str], bool],
    selected_run_id: Callable[[str | None], str | None],
    empty_price_figure: Callable[[str], Any],
    price_figure: Callable[..., tuple[Any, str]],
    supporting_charts: Callable[[Any], Any],
) -> None:
    """Load large chart figures after the usable Overview is present."""

    @app.callback(
        Output("price-marker-chart", "figure"),
        Output("price-marker-summary", "children"),
        Input("price-chart-bars", "value"),
        Input("price-chart-view", "value"),
        Input("selected-trade-grid", "selectedRows"),
        Input("price-chart-load-trigger", "n_intervals"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def update_price_marker_chart(
        interval: str | None,
        view: str | None,
        selected_rows: list[dict[str, Any]] | None,
        _load_intervals: int,
        run_id: str | None,
        pathname: str | None,
    ):
        if not active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not interval or not view:
            raise PreventUpdate
        run_id = selected_run_id(run_id)
        if not run_id:
            message = "Select a completed run with persisted price evidence."
            return empty_price_figure(message), message
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            message = f"Saved chart evidence could not be opened: {exc}"
            return empty_price_figure(message), message
        if not detail.evidence.price_series:
            message = "This saved run has no persisted price series to chart."
            return empty_price_figure(message), message
        selected_trade_index: int | None = None
        if selected_rows and selected_rows[0].get("__run_id") == run_id:
            try:
                selected_trade_index = int(selected_rows[0]["__trade_index"])
            except (KeyError, TypeError, ValueError):
                selected_trade_index = None
        return price_figure(
            detail,
            interval=interval,
            view=view,
            selected_trade_index=selected_trade_index,
        )

    @app.callback(
        Output("results-supporting-charts-content", "children"),
        Input("results-supporting-charts-toggle", "n_clicks"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def load_results_supporting_charts(
        n_clicks: int | None,
        run_id: str | None,
        pathname: str | None,
    ):
        if not n_clicks or n_clicks % 2 == 0:
            raise PreventUpdate
        if not active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        run_id = selected_run_id(run_id)
        if not run_id:
            raise PreventUpdate
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            return html.P(
                f"Saved supporting charts could not be opened: {exc}",
                className="error-state",
            )
        return supporting_charts(detail)
