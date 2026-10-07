"""Lazy Results report tab shell."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dash import dcc, html


def results_report_tabs(*, active_tab: str, initial_content: Any, tab_factory: Callable[..., Any]) -> html.Div:
    tabs = dcc.Tabs(
        [
            tab_factory(label=label, value=value, children=None)
            for label, value in (
                ("Overview", "metrics"),
                ("Trades", "trades"),
                ("Variants", "variants"),
                ("Evidence & review", "evidence"),
                ("Assumptions & lineage", "assumptions"),
            )
        ],
        id="run-detail-analysis-tabs",
        value=active_tab,
        className="run-analysis-tabs results-workspace-tabs",
        persistence=True,
        persistence_type="session",
        parent_style={"display": "flex", "gap": "8px"},
    )
    return html.Div(
        [tabs, html.Div(initial_content, id="results-report-tab-content")],
        className="results-report-tabs-host",
    )
