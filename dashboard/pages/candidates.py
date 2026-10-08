"""High-density Candidate Universe for persisted factory records."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import dash_ag_grid as dag
from dash import dcc, html


def candidate_population(row: Mapping[str, object]) -> str:
    """Classify only explicit persisted evidence; never infer a survivor."""

    status = str(row.get("status") or "").lower()
    evidence = str(row.get("evidence") or "").strip().lower()
    support = " ".join(
        str(row.get(field) or "").lower() for field in ("review", "reproducibility")
    )
    if row.get("rejection_reasons") or any(
        token in evidence for token in ("screened out", "rejected")
    ):
        return "Rejected"
    if status in {"created", "queued", "running", "retrying", "submission unknown"}:
        return "Advancing"
    if status in {"failed", "timed out"} or any(
        token in f"{evidence} {support}" for token in ("invalid", "missing", "corrupt")
    ):
        return "Needs review"
    if status == "succeeded" and row.get("factory_outcome") == "ready_for_protected_test":
        return "Survivor"
    return "Needs review"


def candidate_rows(
    history_rows: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for source in history_rows:
        population = candidate_population(source)
        rows.append(
            {
                "run_id": str(source.get("run_id") or ""),
                "candidate": str(source.get("strategy") or "Unavailable"),
                "market": str(source.get("instrument") or "Unavailable"),
                "bars": str(source.get("interval") or "Unavailable"),
                "population": population,
                "stage": str(source.get("stage") or "Unavailable"),
                "status": str(source.get("status") or "Unavailable"),
                "net_return": source.get("total_return"),
                "sharpe": source.get("sharpe_ratio"),
                "max_drawdown": source.get("max_drawdown"),
                "oos_retention": source.get("oos_retention"),
                "robustness": source.get("robustness"),
                "trades": source.get("number_of_trades"),
                "paper_eligibility": (
                    "Lane inactive" if population == "Survivor" else "Ineligible"
                ),
                "updated": str(source.get("created_at") or "Unavailable"),
            }
        )
    return tuple(rows)


def candidate_columns() -> list[dict[str, Any]]:
    percent = {
        "function": "params.value == null ? 'Unavailable' : (params.value * 100).toFixed(2) + '%'"
    }
    decimal = {
        "function": "params.value == null ? 'Unavailable' : Number(params.value).toFixed(2)"
    }
    return [
        {"field": "run_id", "headerName": "Run ID", "hide": True},
        {"field": "candidate", "headerName": "Candidate", "minWidth": 180, "pinned": "left"},
        {"field": "market", "headerName": "Market", "minWidth": 88},
        {"field": "bars", "headerName": "Bars", "minWidth": 72},
        {"field": "population", "headerName": "Population", "minWidth": 110},
        {"field": "stage", "headerName": "Stage", "minWidth": 110},
        {"field": "status", "headerName": "State", "minWidth": 100},
        {"field": "sharpe", "headerName": "Sharpe", "valueFormatter": decimal, "minWidth": 88},
        {"field": "net_return", "headerName": "Net return", "valueFormatter": percent, "minWidth": 110},
        {"field": "max_drawdown", "headerName": "Max drawdown", "valueFormatter": percent, "minWidth": 120},
        {"field": "oos_retention", "headerName": "OOS retention", "valueFormatter": percent, "minWidth": 118},
        {"field": "robustness", "headerName": "Robustness", "valueFormatter": decimal, "minWidth": 108},
        {"field": "trades", "headerName": "Trades", "minWidth": 82},
        {"field": "paper_eligibility", "headerName": "Paper eligibility", "minWidth": 130},
        {"field": "updated", "headerName": "Updated", "minWidth": 150},
    ]


def layout(*, history_rows: tuple[dict[str, object], ...] = ()) -> html.Div:
    all_rows = candidate_rows(history_rows)
    survivors = [row for row in all_rows if row["population"] == "Survivor"]
    counts = {
        name: sum(row["population"] == name for row in all_rows)
        for name in ("Survivor", "Advancing", "Needs review", "Rejected")
    }
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / CANDIDATES", className="page-eyebrow"),
                            html.H1("Candidate Universe"),
                            html.P(
                                "Find the gold, rank it by evidence, then open the exact record.",
                                className="candidate-subtitle",
                            ),
                        ]
                    ),
                    dcc.Link("Import Candidate", href="/research/ideas", className="secondary-action"),
                ],
                className="candidate-header",
            ),
            html.Div(
                [
                    html.Div([html.Strong(f"{counts['Survivor']:,}"), html.Span("Survivors")]),
                    html.Div([html.Strong(f"{counts['Advancing']:,}"), html.Span("Advancing")]),
                    html.Div([html.Strong(f"{counts['Needs review']:,}"), html.Span("Needs review")]),
                    html.Div([html.Strong(f"{counts['Rejected']:,}"), html.Span("Rejected")]),
                ],
                className="candidate-stat-strip",
            ),
            dcc.Store(id="candidate-universe-records", data=list(all_rows)),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H2("Survivors", id="candidate-population-title"),
                                    html.P(
                                        "Explicit survivors only. Missing evidence remains unavailable.",
                                        id="candidate-population-description",
                                    ),
                                ]
                            ),
                            html.Div(
                                [
                                    dcc.Dropdown(
                                        id="candidate-population",
                                        options=[
                                            {"label": f"Survivors ({counts['Survivor']})", "value": "Survivor"},
                                            {"label": "All candidates", "value": "All"},
                                            {"label": f"Advancing ({counts['Advancing']})", "value": "Advancing"},
                                            {"label": f"Needs review ({counts['Needs review']})", "value": "Needs review"},
                                            {"label": f"Rejected ({counts['Rejected']})", "value": "Rejected"},
                                        ],
                                        value="Survivor",
                                        clearable=False,
                                        className="candidate-population",
                                    ),
                                    dcc.Input(
                                        id="candidate-search",
                                        type="search",
                                        placeholder="Search candidates",
                                        debounce=True,
                                        className="text-input",
                                    ),
                                ],
                                className="candidate-controls",
                            ),
                        ],
                        className="candidate-panel-heading",
                    ),
                    dag.AgGrid(
                        id="candidate-universe-grid",
                        rowData=survivors,
                        columnDefs=candidate_columns(),
                        defaultColDef={"sortable": True, "filter": True, "resizable": True},
                        dashGridOptions={
                            "pagination": True,
                            "paginationPageSize": 50,
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
                        className="ag-theme-quartz qf-data-grid candidate-grid",
                        style={"height": "560px", "width": "100%"},
                    ),
                    html.Div(
                        [
                            html.P(
                                "No survivor selected. Select one for exact Results or two to four for comparison.",
                                id="candidate-selection-message",
                                className="field-help",
                            ),
                            html.Div(
                                [
                                    dcc.Link("Open exact Results", id="candidate-results-link", href=None, className="primary-action", style={"display": "none"}),
                                    dcc.Link("Compare selected", id="candidate-compare-link", href=None, className="secondary-action", style={"display": "none"}),
                                ],
                                className="page-actions",
                            ),
                        ],
                        className="candidate-selection-bar",
                    ),
                ],
                className="candidate-panel",
            ),
        ],
        className="page-container candidates-page",
    )


__all__ = ["candidate_columns", "candidate_population", "candidate_rows", "layout"]
