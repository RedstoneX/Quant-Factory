"""Backtest Results trade explorer callback ownership."""

from __future__ import annotations

from typing import Any

from dash import Dash, Input, Output, State, html
from dash.exceptions import PreventUpdate

from dashboard.application import _active_route
from dashboard.components.trade_explorer import (
    filter_trade_rows,
    normalize_trade_rows,
    no_trade_selected_message,
    selected_trade_detail,
)
from dashboard.run_detail_adapter import RunDetailDashboardAdapter


def register_trade_explorer_callbacks(
    app: Dash,
    *,
    detail_adapter: RunDetailDashboardAdapter,
) -> None:
    """Register callbacks owned by the Backtest Results trade explorer."""

    @app.callback(
        Output("selected-trade-grid", "rowData"),
        Output("trade-explorer-summary", "children"),
        Output("selected-trade-grid", "selectedRows"),
        Input("selected-run-state", "data"),
        Input("trade-outcome-filter", "value"),
        Input("trade-direction-filter", "value"),
        Input("trade-date-range", "start_date"),
        Input("trade-date-range", "end_date"),
        Input("refresh-runs", "n_clicks"),
        Input("url", "pathname"),
    )
    def refresh_trade_rows(
        run_id: str | None,
        outcome_filter: list[str] | None,
        direction_filter: list[str] | None,
        start_date: str | None,
        end_date: str | None,
        _: int | None,
        pathname: str | None,
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not run_id:
            return (
                [],
                "Select a persisted backtest to inspect trade rows.",
                [],
            )
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            return (
                [],
                html.Span(
                    f"Trade evidence could not be opened: {exc}",
                    className="error-state",
                ),
                [],
            )

        rows = normalize_trade_rows(detail.evidence.trades, run_id=run_id)
        if not rows:
            return (
                [],
                "No persisted trade artifact is available for this backtest.",
                [],
            )
        filtered, summary = filter_trade_rows(
            rows,
            outcomes=outcome_filter,
            directions=direction_filter,
            start_date=start_date,
            end_date=end_date,
        )
        return list(filtered), summary, []

    @app.callback(
        Output("selected-trade-detail", "children"),
        Input("selected-trade-grid", "selectedRows"),
        Input("selected-trade-grid", "rowData"),
        State("selected-run-state", "data"),
        State("url", "pathname"),
    )
    def focus_selected_trade(
        selected_rows: list[dict[str, Any]] | None,
        visible_rows: list[dict[str, Any]] | None,
        run_id: str | None,
        pathname: str | None,
    ):
        if not _active_route(pathname, "/research/backtest-results"):
            raise PreventUpdate
        if not run_id:
            return no_trade_selected_message()
        if selected_rows and selected_rows[0].get("__run_id") != run_id:
            return selected_trade_detail(
                selected_rows,
                run_id=run_id,
                execution_fields=(),
                visible_rows=visible_rows,
            )
        if not selected_rows:
            return selected_trade_detail(
                selected_rows,
                run_id=run_id,
                execution_fields=(),
                visible_rows=visible_rows,
            )
        try:
            detail = detail_adapter.selected_run_detail(run_id)
        except (KeyError, RuntimeError, ValueError) as exc:
            return html.P(
                f"Selected trade detail could not be opened: {exc}",
                className="error-state",
            )
        return selected_trade_detail(
            selected_rows,
            run_id=run_id,
            execution_fields=detail.execution,
            visible_rows=visible_rows,
        )
