"""Production Candidates workspace in the accepted Quant Factory shell."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update

from dashboard.candidates_projection import (
    load_candidate_detail,
    load_candidates_page,
    load_candidates_summary,
)


GLYPHS = {"dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷", "chart": "⌁", "external": "↗", "bookmark": "◇", "columns": "▥", "search": "⌕"}

HUMAN_LABELS = {
    "needs_review": "Needs review",
    "not_run": "Not run",
    "oos": "Out of sample",
    "walk_forward": "Walk-forward",
    "monte_carlo": "Monte Carlo",
}


def _human_label(value: Any) -> str:
    text = str(value or "not_run")
    return HUMAN_LABELS.get(text, text.replace("_", " ").title())


def _icon(name: str) -> html.Span:
    return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})


def _rail(name: str, label: str, item_id: str, *, active: bool = False, disabled: bool = False) -> dmc.ActionIcon:
    return dmc.ActionIcon(_icon(name), id=item_id, className=f"rail-item{' active' if active else ''}", variant="subtle", disabled=disabled, **{"aria-label": label})


CANDIDATE_COLUMNS = [
    {"field": "title", "headerName": "Candidate", "width": 190, "pinned": "left", "filter": "agTextColumnFilter"},
    {"field": "symbol", "headerName": "Market", "width": 72, "pinned": "left", "filter": "agTextColumnFilter"},
    {"field": "lifecycle", "headerName": "Lifecycle", "minWidth": 92, "flex": .85, "filter": "agTextColumnFilter", "valueFormatter": {"function": "params.value === 'needs_review' ? 'Needs review' : params.value ? params.value.charAt(0).toUpperCase() + params.value.slice(1) : '—'"}},
    {"field": "sharpe", "headerName": "OOS Sharpe", "type": "numericColumn", "minWidth": 112, "flex": 1, "filter": "agNumberColumnFilter", "sort": "desc", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Max DD", "type": "numericColumn", "minWidth": 76, "flex": .7, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "retained", "headerName": "OOS retain", "type": "numericColumn", "minWidth": 82, "flex": .75, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "net_return", "headerName": "Net return", "type": "numericColumn", "minWidth": 82, "flex": .75, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : (params.value > 0 ? '+' : '') + params.value.toFixed(1) + '%'"}},
    {"field": "robustness", "headerName": "Robustness", "minWidth": 84, "flex": .78, "filter": "agTextColumnFilter"},
    {"field": "paper", "headerName": "Paper", "minWidth": 86, "flex": .8, "filter": "agTextColumnFilter"},
]


def candidates_layout() -> dmc.MantineProvider:
    summary = load_candidates_summary()
    counts = summary.get("counts", {})
    family_options = [{"value": "all", "label": "All families"}] + [{"value": family, "label": family} for family in summary.get("families", [])]
    nav = dmc.Stack([
        dmc.Paper("Q", className="logo", radius="md"),
        _rail("dashboard", "Dashboard", "candidates-nav-dashboard"),
        _rail("file", "Submit strategies unavailable", "candidates-nav-submit", disabled=True),
        _rail("flow", "Factory runs", "candidates-nav-factory"),
        _rail("list", "Candidates", "candidates-nav-candidates", active=True),
        _rail("chart", "Results", "candidates-nav-results"),
        html.Div(className="rail-spacer"), _rail("external", "Paper Trading unavailable", "candidates-nav-paper", disabled=True),
        dmc.Avatar("TO", className="avatar", radius="xl"),
    ], gap=7, align="center", className="rail")

    saved_views = dmc.Menu([
        dmc.MenuTarget(dmc.Button("Saved views", leftSection=_icon("bookmark"), className="ghost", variant="default")),
        dmc.MenuDropdown([
            dmc.MenuLabel("Workspace views"),
            dmc.MenuItem("Survivor leaders", id="view-survivors"),
            dmc.MenuItem("Complete universe", id="view-all"),
            dmc.MenuItem("Rejected history", id="view-rejected"),
        ]),
    ], position="bottom-end")
    header = dmc.Group([
        html.Div([dmc.Title("Candidate universe", order=1), dmc.Text("Every lifecycle population · one ranked workspace", className="eyebrow")]),
        html.Div(className="top-spacer"), saved_views,
        dmc.Button("Columns", id="candidate-columns", leftSection=_icon("columns"), className="ghost", variant="default"),
        dmc.Button("Submit strategy unavailable", className="primary", disabled=True),
    ], gap=9, className="topbar candidates-topbar")

    lifecycle = dmc.SegmentedControl(
        id="candidate-lifecycle", value="survivor",
        data=[{"value": key, "label": f"{label} · {int(counts.get(key, 0)):,}"} for key, label in [("survivor", "Survivors"), ("advancing", "Advancing"), ("needs_review", "Needs review"), ("rejected", "Rejected"), ("all", "All")]],
        className="candidate-tabs", fullWidth=False, persistence=True, persistence_type="local",
    )
    filters = dmc.Group([
        dmc.TextInput(id="candidate-search", placeholder="Search Candidate, market, family…", leftSection=_icon("search"), className="candidate-search", debounce=True, persistence=True, persistence_type="local", **{"aria-label": "Search Candidates"}),
        dmc.Select(id="candidate-market", data=[{"value": "all", "label": "All markets"}, {"value": "futures", "label": "Futures"}, {"value": "equities", "label": "Equities"}, {"value": "crypto", "label": "Crypto"}, {"value": "unclassified", "label": "Unclassified"}], value="all", allowDeselect=False, className="candidate-select", persistence=True, persistence_type="local", **{"aria-label": "Candidate market"}),
        dmc.Select(id="candidate-family", data=family_options, value="all", allowDeselect=False, className="candidate-select family", persistence=True, persistence_type="local", **{"aria-label": "Candidate family"}),
        dmc.Select(id="candidate-evidence", data=[{"value": "any", "label": "Any evidence state"}, {"value": "all_gates", "label": "All gates passed"}, {"value": "failed_oos", "label": "Failed OOS"}, {"value": "semantic_exception", "label": "Semantic exception"}], value="any", allowDeselect=False, className="candidate-select evidence", persistence=True, persistence_type="local", **{"aria-label": "Candidate evidence state"}),
        dmc.Badge("OOS Sharpe descending", className="filter-chip", leftSection=html.Span("⇣")),
        html.Div(className="top-spacer"),
        dmc.Button("Compare selected · 0", id="compare-selected", className="ghost", variant="default", disabled=True),
    ], gap=8, className="candidate-filters")

    grid = dag.AgGrid(
        id="candidate-grid", columnDefs=CANDIDATE_COLUMNS, rowModelType="infinite",
        defaultColDef={"sortable": True, "resizable": True, "filter": True, "floatingFilter": False},
        dashGridOptions={
            "rowSelection": {"mode": "multiRow", "checkboxes": True, "headerCheckbox": False, "enableClickSelection": True},
            "selectionColumnDef": {"pinned": "left", "width": 38, "minWidth": 38, "maxWidth": 38, "resizable": False, "sortable": False},
            "cacheBlockSize": 50, "maxBlocksInCache": 4, "rowBuffer": 10, "animateRows": False,
            "suppressCellFocus": False, "enableCellTextSelection": True, "suppressPropertyNamesCheck": True,
        },
        getRowId="params.data.candidate_id", className="ag-theme-quartz-dark candidates-grid",
        persistence=True, persisted_props=["filterModel"], persistence_type="local",
    )
    detail = dmc.Paper([
        html.Div([
            dmc.Badge("No selection", id="candidate-detail-state", className="candidate-state"),
            dmc.Title("No Candidate selected", id="candidate-detail-name", order=2),
            dmc.Text("Choose an exact Candidate record from the ranked universe.", id="candidate-detail-meta", className="candidate-detail-meta"),
        ], className="candidate-detail-head"),
        dmc.Tabs([
            dmc.TabsList([dmc.TabsTab("Overview", value="overview"), dmc.TabsTab("Evidence", value="evidence"), dmc.TabsTab("History", value="history"), dmc.TabsTab("Lineage", value="lineage")]),
        ], id="candidate-detail-tab", value="overview", className="candidate-detail-tabs"),
        html.Div(id="candidate-detail-body", className="candidate-detail-body"),
    ], className="candidate-detail", radius=0, withBorder=False)
    workspace = dmc.Paper([
        html.Div([grid, html.Footer([html.Span("0 loaded", id="candidate-page-count"), html.Span("•"), html.Span("0 total · infinite row loading", id="candidate-total-count"), html.Span(className="top-spacer"), html.Span("Selection and filters persist")], className="candidate-grid-footer")], className="candidate-grid-region"),
        detail,
    ], className="candidate-workspace", radius="md", withBorder=True)

    stores = [
        dcc.Store(id="candidate-summary", data=summary), dcc.Store(id="candidate-query"),
        dcc.Store(id="candidate-selection", storage_type="local"),
        dcc.Store(id="candidate-compare-selection", storage_type="local"),
        dcc.Store(id="candidate-detail-record"),
    ]
    body = html.Div([
        dmc.Group([lifecycle, html.Div(className="top-spacer"), dmc.Text("Virtualized universe · persisted selection", className="candidate-context")], className="candidate-lifecycle-row"),
        filters, workspace,
    ], className="candidates-body")
    return dmc.MantineProvider(html.Div([*stores, html.Div([nav, html.Main([header, body], className="main")], className="app candidates-app")]), forceColorScheme="dark", theme={"fontFamily": "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", "primaryColor": "blue"})


def _fmt(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1f}%" if percent else f"{float(value):.2f}"


def _outcome(record: dict[str, Any]) -> tuple[str, str]:
    lifecycle = record.get("lifecycle")
    if lifecycle == "survivor":
        return "Qualified survivor marker persisted", "Paper lane inactive; no broker or capital authority"
    if lifecycle == "advancing":
        return f"{_human_label(record.get('stage'))} · {_human_label(record.get('run_status'))}", "Continues automatically inside existing authority"
    if lifecycle == "needs_review":
        return "Semantic exception recorded", "Resolve the exact recorded ambiguity"
    if lifecycle == "rejected":
        return f"Closed · {record.get('screening_status') or record.get('run_status')}", "Evidence and lineage retained"
    return "Candidate received", "Next eligibility is not recorded"


def _detail_body(record: dict[str, Any] | None, tab: str) -> list[Any]:
    if not record:
        return [dmc.Text("No persisted Candidate is selected.", className="candidate-empty")]
    outcome, next_state = _outcome(record)
    progression = record.get("progression") or []
    if tab == "evidence":
        return [
            dmc.Title("Recorded evidence", order=3),
            html.Div([html.Span("OOS Sharpe"), html.Strong(_fmt(record.get("sharpe"))), html.Span("Exact" if record.get("sharpe") is not None else "Unavailable")], className="candidate-evidence-item"),
            html.Div([html.Span("Maximum drawdown"), html.Strong(_fmt(record.get("max_drawdown"), percent=True)), html.Span("Persisted")], className="candidate-evidence-item"),
            html.Div([html.Span("Net return"), html.Strong(_fmt(record.get("net_return"), percent=True)), html.Span("Net of configured costs")], className="candidate-evidence-item"),
            html.Div([html.Span("OOS retention"), html.Strong(_fmt(record.get("retained"), percent=True)), html.Span("Unavailable" if record.get("retained") is None else "Persisted")], className="candidate-evidence-item"),
            html.Div([html.Span("Robustness"), html.Strong(str(record.get("robustness"))), html.Span("Recorded stage")], className="candidate-evidence-item"),
        ]
    if tab == "history":
        return [dmc.Title("Evidence progression", order=3), *[
            html.Div([html.Span(className=f"candidate-dot{' failed' if item.get('status') == 'failed' else ''}"), html.Div([html.Strong(_human_label(item.get("stage"))), html.P(str(item.get("run_id") or "No run identity"))]), html.Time(_human_label(item.get("status")))], className="candidate-stage-row")
            for item in progression
        ], *([] if progression else [dmc.Text("No persisted run history is linked to this Candidate.", className="candidate-empty")])]
    if tab == "lineage":
        return [
            dmc.Title("Persisted lineage", order=3),
            html.Div([html.Span("Candidate"), html.Strong(str(record.get("candidate_id"))), html.Span("Exact")], className="candidate-evidence-item"),
            html.Div([html.Span("Version"), html.Strong(str(record.get("candidate_version") or "Unavailable")[:16]), html.Span("Immutable digest")], className="candidate-evidence-item"),
            html.Div([html.Span("Configuration"), html.Strong(str(record.get("configuration_id") or "Unavailable")), html.Span("Bound")], className="candidate-evidence-item"),
            html.Div([html.Span("Latest run"), html.Strong(str(record.get("run_id") or "Unavailable")), html.Span(str(record.get("stage") or "not run"))], className="candidate-evidence-item"),
        ]
    return [
        html.Div([html.Span("Outcome"), html.Strong(outcome), html.Span("Exact")], className="candidate-evidence-item"),
        html.Div([html.Span("Next state"), html.Strong(next_state), html.Span()], className="candidate-evidence-item"),
        html.Div(record.get("error_summary") or record.get("description") or "No additional persisted explanation is available.", className=f"candidate-explanation {record.get('lifecycle') or ''}"),
        dmc.Group([dmc.Button("Open Results", id="candidate-open-results", className="primary", disabled=not record.get("run_id")), dmc.Button("View persisted sensitivity", id="candidate-open-evidence", className="ghost", variant="default")], gap=8, className="candidate-detail-actions"),
        dmc.Title("Evidence progression", order=3, className="candidate-progression-title"),
        *[html.Div([html.Span(_human_label(item.get("stage"))), html.Strong(_human_label(item.get("status"))), html.Span("✓" if item.get("status") == "succeeded" else "")], className="candidate-evidence-item") for item in progression],
        *([] if progression else [dmc.Text("No persisted evidence stages are linked.", className="candidate-empty")]),
    ]


def register_candidate_callbacks(application: Any) -> None:
    @application.callback(Output("candidate-lifecycle", "data"), Output("candidate-family", "data"), Input("candidate-summary", "data"))
    def render_summary(summary: dict[str, Any] | None):
        summary = summary or {}; counts = summary.get("counts", {})
        tabs = [{"value": key, "label": f"{label} · {int(counts.get(key, 0)):,}"} for key, label in [("survivor", "Survivors"), ("advancing", "Advancing"), ("needs_review", "Needs review"), ("rejected", "Rejected"), ("all", "All")]]
        families = [{"value": "all", "label": "All families"}] + [{"value": family, "label": family} for family in summary.get("families", [])]
        return tabs, families

    @application.callback(
        Output("candidate-lifecycle", "value"), Output("candidate-market", "value"), Output("candidate-family", "value"), Output("candidate-evidence", "value"), Output("candidate-search", "value"),
        Input("view-survivors", "n_clicks"), Input("view-all", "n_clicks"), Input("view-rejected", "n_clicks"), prevent_initial_call=True,
    )
    def apply_saved_view(*_clicks: Any):
        if ctx.triggered_id == "view-survivors":
            return "survivor", "all", "all", "all_gates", ""
        if ctx.triggered_id == "view-all":
            return "all", "all", "all", "any", ""
        if ctx.triggered_id == "view-rejected":
            return "rejected", "all", "all", "any", ""
        return no_update, no_update, no_update, no_update, no_update

    @application.callback(Output("candidate-query", "data"), Input("candidate-lifecycle", "value"), Input("candidate-market", "value"), Input("candidate-family", "value"), Input("candidate-evidence", "value"), Input("candidate-search", "value"))
    def update_query(lifecycle: str, market: str, family: str, evidence: str, search: str | None) -> dict[str, Any]:
        return {"lifecycle": lifecycle or "survivor", "market": market or "all", "family": family or "all", "evidence": evidence or "any", "search": search or ""}

    @application.callback(Output("candidate-grid", "getRowsResponse"), Output("candidate-page-count", "children"), Output("candidate-total-count", "children"), Input("candidate-grid", "getRowsRequest"), Input("candidate-query", "data"))
    def load_grid(request: dict[str, Any] | None, query: dict[str, Any] | None):
        if not request or not query:
            empty = {"rowData": [], "rowCount": 0}; return empty, "0 loaded", "0 total · infinite row loading"
        page = load_candidates_page(start=int(request.get("startRow") or 0), end=int(request.get("endRow") or 50), sort_model=request.get("sortModel"), filter_model=request.get("filterModel"), **query)
        return page, f"{len(page['rowData']):,} loaded", f"{int(page['rowCount']):,} total · infinite row loading"

    @application.callback(Output("candidate-selection", "data"), Input("candidate-grid", "selectedRows"), Input("candidate-grid", "getRowsResponse"), State("candidate-selection", "data"), prevent_initial_call=True)
    def persist_primary_selection(selected_rows: list[dict[str, Any]] | None, response: dict[str, Any] | None, current: dict[str, Any] | None):
        if "candidate-grid.selectedRows" in ctx.triggered_prop_ids and selected_rows:
            row = selected_rows[-1]; return {"candidate_id": row.get("candidate_id"), "run_id": row.get("run_id")}
        if current:
            return current
        rows = (response or {}).get("rowData") or []
        return {"candidate_id": rows[0].get("candidate_id"), "run_id": rows[0].get("run_id")} if rows else None

    @application.callback(Output("candidate-compare-selection", "data"), Input("candidate-grid", "selectedRows"), State("candidate-compare-selection", "data"), prevent_initial_call=True)
    def persist_compare_selection(rows: list[dict[str, Any]] | None, current: list[dict[str, Any]] | None):
        if rows is None:
            return current or []
        return [{"candidate_id": row.get("candidate_id"), "run_id": row.get("run_id"), "title": row.get("title")} for row in rows if row.get("lifecycle") == "survivor"]

    @application.callback(Output("compare-selected", "children"), Output("compare-selected", "disabled"), Input("candidate-compare-selection", "data"))
    def compare_state(rows: list[dict[str, Any]] | None):
        count = len(rows or [])
        return (f"Compare selected · {count} · unavailable" if count >= 2 else f"Compare selected · {count}"), True

    @application.callback(Output("candidate-detail-record", "data"), Input("candidate-selection", "data"))
    def load_detail(selection: dict[str, Any] | None):
        return load_candidate_detail((selection or {}).get("candidate_id"))

    @application.callback(Output("candidate-detail-state", "children"), Output("candidate-detail-name", "children"), Output("candidate-detail-meta", "children"), Output("candidate-detail-body", "children"), Input("candidate-detail-record", "data"), Input("candidate-detail-tab", "value"))
    def render_detail(record: dict[str, Any] | None, tab: str):
        if not record:
            return "No selection", "No Candidate selected", "Choose an exact Candidate record from the ranked universe.", _detail_body(None, tab)
        state = _human_label(record.get("lifecycle") or "received")
        rank = f"Rank {record.get('rank')}" if record.get("rank") else "Exact record"
        meta = f"{record.get('candidate_id')} · {record.get('symbol')} · {record.get('family')} · {rank}"
        return state, record.get("title") or "Untitled Candidate", meta, _detail_body(record, tab)

    @application.callback(Output("candidate-detail-tab", "value"), Input("candidate-open-evidence", "n_clicks", allow_optional=True), prevent_initial_call=True)
    def open_evidence(_clicks: int | None):
        return "evidence" if _clicks else no_update

    @application.callback(Output("candidate-grid", "columnDefs"), Input("candidate-columns", "n_clicks"), prevent_initial_call=True)
    def toggle_columns(clicks: int | None):
        compact = bool((clicks or 0) % 2)
        return [{**column, **({"hide": compact} if column["field"] in {"retained", "robustness", "paper"} else {})} for column in CANDIDATE_COLUMNS]


__all__ = ["candidates_layout", "register_candidate_callbacks"]
