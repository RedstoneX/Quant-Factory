"""Secondary Results charts rendered through the composition root."""

from __future__ import annotations

from typing import Any, Callable

from dash import html


def results_supporting_charts_host(*, available: bool) -> html.Details:
    message = (
        "Open this section to load its saved equity, benchmark and drawdown charts."
        if available
        else "Select a completed run before loading supporting charts."
    )
    return html.Details(
        [
            html.Summary(
                "Equity, benchmark and drawdown",
                id="results-supporting-charts-toggle",
                n_clicks=0,
            ),
            html.Div(
                html.P(message, className="empty-state-copy"),
                id="results-supporting-charts-content",
            ),
        ],
        id="results-supporting-charts",
        hidden=not available,
        className="operator-details results-supporting-charts",
    )


def render_results_supporting_charts(
    detail: Any,
    *,
    detail_subsection: Callable[..., Any],
    portfolio_value_panel: Callable[[Any], Any],
    curve_graph: Callable[..., Any],
    trade_pnl_chart: Callable[..., Any],
) -> html.Div:
    """Build charts only after the operator opens their disclosure."""
    return html.Div(
        [
            detail_subsection(
                "Portfolio value and buy-and-hold comparison",
                portfolio_value_panel(detail),
            ),
            detail_subsection(
                "Drawdown over time",
                curve_graph(
                    detail.evidence.drawdown_curve,
                    y_field="drawdown",
                    title="Drawdown over time",
                    color="#ef4444",
                    empty="No persisted drawdown artifact is available for this run.",
                    percent=True,
                    markers=True,
                    emphasize_min=True,
                ),
            ),
            detail_subsection(
                "Cumulative trade P&L",
                trade_pnl_chart(detail.evidence.trades, mode="cumulative"),
            ),
        ]
    )
