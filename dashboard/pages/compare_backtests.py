"""Find & Compare page for the complete persisted research-run history."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import dash_ag_grid as dag
from dash import dcc, html

from dashboard.components.compare_results import compare_empty


def results_query_href(run_id: str) -> str:
    """Build the existing exact Results URL for one persisted run."""

    return f"/research/backtest-results?{urlencode({'run_id': str(run_id)})}"


def find_compare_columns() -> list[dict[str, Any]]:
    percent = {
        "function": "params.value == null ? '' : (params.value * 100).toFixed(2) + '%'"
    }
    return [
        {"field": "run_id", "headerName": "Run ID", "hide": True},
        {"field": "created_at", "headerName": "Date", "minWidth": 125},
        {"field": "instrument", "headerName": "Instrument", "minWidth": 80},
        {"field": "interval", "headerName": "Bars", "minWidth": 68},
        {
            "field": "strategy",
            "headerName": "Strategy",
            "filter": "agTextColumnFilter",
            "minWidth": 145,
        },
        {
            "field": "evidence",
            "headerName": "Screening / evidence",
            "filter": "agTextColumnFilter",
            "minWidth": 145,
        },
        {"field": "total_return", "headerName": "Total return", "valueFormatter": percent},
        {
            "field": "max_drawdown",
            "headerName": "Max drawdown",
            "valueFormatter": percent,
        },
        {"field": "win_rate", "headerName": "Win rate", "valueFormatter": percent},
        {
            "field": "sharpe_ratio",
            "headerName": "Sharpe",
            "valueFormatter": {
                "function": (
                    "params.value == null ? '' : Number(params.value).toFixed(2)"
                )
            },
            "minWidth": 74,
        },
        {"field": "number_of_trades", "headerName": "Trades", "minWidth": 78},
    ]


def _compact_research_path() -> html.Div:
    """Keep the six accepted workflow steps on one compact row on this page."""

    from dashboard.application import _strategy_research_path

    path = _strategy_research_path("/research/compare-backtests")
    path.style = {**(path.style or {}), "flexWrap": "wrap", "gap": "6px"}
    for child in path.children:
        if isinstance(child, dcc.Link):
            child.style = {
                **(child.style or {}),
                "flex": "1 1 110px",
                "minWidth": "90px",
                "padding": "10px",
            }
    return path


def layout(*, history_rows: tuple[dict[str, object], ...] = ()) -> html.Div:
    """Mount the full-history selector and existing comparison output."""

    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / FIND & COMPARE", className="page-eyebrow"),
                            html.H1("Find & Compare", className="page-title"),
                            html.P(
                                "Search, sort, and filter every saved test. Select one "
                                "row for its exact Results page, or two to four rows for "
                                "an exact comparison.",
                                className="page-description",
                            ),
                        ]
                    ),
                    html.Button(
                        "Refresh",
                        id="refresh-comparisons",
                        n_clicks=0,
                        className="secondary-action page-action",
                        title="Retry reading persisted history. No test will run or change.",
                        style={
                            "alignSelf": "flex-start",
                            "justifySelf": "end",
                            "maxWidth": "160px",
                            "minWidth": "120px",
                            "width": "auto",
                        },
                    ),
                ],
                className="page-heading page-heading-with-actions",
            ),
            _compact_research_path(),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("SAVED TESTS", className="section-kicker"),
                            html.H2("Find a test or build a comparison"),
                            html.P(
                                "Each row is one saved test. Metrics are from that test's "
                                "top-ranked variation; unavailable values remain blank.",
                                className="section-description",
                            ),
                        ],
                        className="section-heading-row",
                    ),
                    html.Div(
                        [
                            html.Label(
                                [
                                    html.Span("Quick search", className="field-label"),
                                    dcc.Input(
                                        id="find-compare-search",
                                        type="search",
                                        placeholder="Search saved tests",
                                        debounce=True,
                                        persistence=True,
                                        persistence_type="session",
                                        className="text-input",
                                    ),
                                ]
                            ),
                            html.Button(
                                "Reset view",
                                id="find-compare-reset-view",
                                n_clicks=0,
                                className="secondary-action",
                            ),
                            html.P(
                                f"{len(history_rows):,} matched · 0 selected",
                                id="find-compare-grid-count",
                                className="field-help compact-field-help",
                                **{"aria-live": "polite"},
                            ),
                        ],
                        className="page-actions",
                        style={"alignItems": "center", "marginBottom": "12px"},
                    ),
                    dag.AgGrid(
                        id="find-compare-grid",
                        rowData=list(history_rows),
                        columnDefs=find_compare_columns(),
                        defaultColDef={"sortable": True, "filter": True, "resizable": True},
                        dashGridOptions={
                            "pagination": True,
                            "paginationPageSize": 25,
                            "rowSelection": {
                                "mode": "multiRow",
                                "checkboxes": True,
                                "headerCheckbox": False,
                                "enableClickSelection": True,
                            },
                        },
                        getRowId="params.data.run_id",
                        selectedRows=[],
                        persistence=True,
                        persistence_type="session",
                        persisted_props=["filterModel", "columnState"],
                        columnSize="responsiveSizeToFit",
                        columnSizeOptions={"defaultMinWidth": 56},
                        style={"height": "520px", "width": "100%"},
                        className="ag-theme-alpine qf-data-grid",
                    ),
                    html.Div(
                        [
                            html.P(
                                "Select one saved test to open Results, or two to four to compare.",
                                id="find-compare-selection-message",
                                className="field-help compact-field-help",
                                **{"aria-live": "polite"},
                            ),
                            html.Div(
                                [
                                    dcc.Link(
                                        "Open exact Results",
                                        id="find-compare-results-link",
                                        href=None,
                                        className="secondary-action",
                                        style={"display": "none"},
                                    ),
                                    dcc.Link(
                                        "Compare selected tests",
                                        id="find-compare-exact-link",
                                        href=None,
                                        className="primary-action",
                                        style={"display": "none"},
                                    ),
                                ],
                                className="page-actions",
                            ),
                        ],
                        className="comparison-selector-control",
                    ),
                ],
                className="comparison-setup-panel",
            ),
            html.Div(
                dcc.Loading(
                    html.Div(
                        compare_empty(),
                        id="run-comparison-output",
                        className="run-comparison-output",
                    ),
                    id="comparison-loading",
                    type="circle",
                ),
                id="comparison-operator-contexts",
                className="comparison-operator-contexts",
            ),
        ],
        className="page-container comparison-page",
    )


__all__ = ["find_compare_columns", "layout", "results_query_href"]
