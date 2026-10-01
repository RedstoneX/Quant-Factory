"""Reusable strategy-research navigation path."""

from __future__ import annotations

from typing import Any

from dash import dcc, html


RESEARCH_PATH_STYLE = {
    "alignItems": "stretch",
    "display": "flex",
    "flexWrap": "wrap",
    "gap": "10px",
}
RESEARCH_PATH_CARD_STYLE = {
    "alignItems": "center",
    "backgroundColor": "#ffffff",
    "border": "1px solid #bfdbfe",
    "borderRadius": "8px",
    "boxShadow": "0 8px 20px rgba(15, 23, 42, 0.08)",
    "display": "flex",
    "flex": "1 1 180px",
    "gap": "10px",
    "minHeight": "64px",
    "padding": "12px 14px",
}
RESEARCH_PATH_STEP_STYLE = {
    "alignItems": "center",
    "backgroundColor": "#2357d9",
    "borderRadius": "999px",
    "color": "#ffffff",
    "display": "inline-flex",
    "fontSize": "0.8rem",
    "fontWeight": 800,
    "height": "28px",
    "justifyContent": "center",
    "minWidth": "28px",
}
RESEARCH_PATH_CONNECTOR_STYLE = {
    "alignItems": "center",
    "color": "#2357d9",
    "display": "inline-flex",
    "fontWeight": 800,
    "padding": "0 2px",
}


def strategy_research_path(current_path: str = "/") -> html.Div:
    stages = (
        ("Home", "/"),
        ("Ideas", "/research/ideas"),
        ("Set up", "/research/setup"),
        ("Run test", "/research/run-test"),
        ("Results", "/research/backtest-results"),
        ("Compare", "/research/compare-backtests"),
    )
    children: list[Any] = []
    for index, (stage, href) in enumerate(stages):
        if index:
            children.append(
                html.Span(
                    "->",
                    className="research-path-connector",
                    style=RESEARCH_PATH_CONNECTOR_STYLE,
                )
            )
        children.append(
            dcc.Link(
                [
                    html.Span(
                        str(index + 1),
                        className="research-path-step",
                        style=RESEARCH_PATH_STEP_STYLE,
                    ),
                    html.Strong(stage),
                ],
                href=href,
                className=(
                    "research-path-card research-path-card-active"
                    if href == current_path
                    else "research-path-card"
                ),
                style=RESEARCH_PATH_CARD_STYLE,
                title=(f"Current step: {stage}" if href == current_path else stage),
            )
        )
    return html.Div(
        children,
        className="strategy-research-path",
        style=RESEARCH_PATH_STYLE,
    )
