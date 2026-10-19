"""Production Factory runs workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash_iconify import DashIconify

from dashboard.factory_projection import load_factory_page, load_factory_summary
from dashboard.plain_labels import FAILED_TESTING
from dashboard.ui.layout import copy_id, page_header, stat_card
from dashboard.ui.theme import COLUMN_DEFAULTS, grid_options, hide_when_narrow


RUN_COLUMNS = [
    {"field": "title", "headerName": "Run", "minWidth": 200, "flex": 2, "filter": "agTextColumnFilter", "tooltipField": "run_id"},
    {"field": "symbol", "headerName": "Market", "minWidth": 80, "flex": .6, "filter": "agTextColumnFilter"},
    {"field": "status", "headerName": "Outcome", "minWidth": 110, "flex": .9, "filter": "agTextColumnFilter", "cellStyle": {"styleConditions": [{"condition": "params.data && params.data.display_outcome === 'screened_out'", "style": {"color": "#7d8590"}}, {"condition": "params.value === 'failed'", "style": {"color": "#ef5350"}}]}, "valueFormatter": {"function": "params.data && params.data.display_outcome === 'screened_out' ? '" + FAILED_TESTING + "' : params.value ? params.value.charAt(0).toUpperCase()+params.value.slice(1) : '—'"}},
    {"field": "variation_count", "headerName": "Results", "type": "numericColumn", "flex": .6},
    {"field": "survivor_count", "headerName": "Passed", "type": "numericColumn", "flex": .6},
    {"field": "completed_display", "colId": "completed_at", "headerName": "Finished", "minWidth": 120, "flex": 1},
]


STAGE_WORDS = {"screening": "First check", "oos": "Unseen-data test", "walk_forward": "Rolling test", "monte_carlo": "Shuffle test"}


def _stage_word(stage: Any) -> str:
    return STAGE_WORDS.get(str(stage), str(stage or "unavailable").replace("_", " ").title())


def factory_layout() -> html.Div:
    summary = load_factory_summary(); counts = summary.get("counts", {})
    initial_page = load_factory_page(cohort="completed", start=0, end=1)
    initial_selection = (initial_page.get("rowData") or [None])[0]
    header = page_header("Factory runs", "Every test run: what is running, waiting, finished or failed", dmc.Badge(f"{counts.get('running',0):,} running", color="blue"), dmc.Badge(f"{counts.get('queued',0):,} waiting", color="gray"), dmc.Badge(f"{counts.get('failed',0):,} failed", color="red"))
    tabs = dmc.SegmentedControl(id="factory-cohort", value="completed", size="xs", data=[{"value": "open", "label": f"Open · {counts.get('open',0):,}"}, {"value": "completed", "label": f"Finished · {counts.get('completed',0):,}"}, {"value": "failed", "label": f"Failed · {counts.get('failed',0):,}"}], persistence=True, persistence_type="local")
    markets = [{"value": "all", "label": "All markets"}] + [{"value": x, "label": x} for x in summary.get("markets", [])]
    stages = [{"value": "all", "label": "All stages"}] + [{"value": x, "label": str(x).replace("_", " ").title()} for x in summary.get("stages", [])]
    toolbar = dmc.Group([
        tabs, dmc.TextInput(id="factory-search", placeholder="Search runs…", leftSection=DashIconify(icon="tabler:search", width=14), debounce=True, size="xs", w=200),
        dmc.Select(id="factory-market", data=markets, value="all", allowDeselect=False, size="xs", w=130),
        dmc.Select(id="factory-stage", data=stages, value="all", allowDeselect=False, size="xs", w=150),
        dmc.Select(id="factory-resource", data=[{"value": "all", "label": "Any machine state"}, {"value": "unavailable", "label": "Machine state not recorded"}], value="all", allowDeselect=False, size="xs", w=200),
    ], gap="xs", mb="sm", wrap="wrap")
    median = summary.get("median_minutes")
    stats = [
        stat_card("Tested in the last 24 hours", f"{summary.get('throughput_24h',0):,}", "results", color="white"),
        *([stat_card("Typical run time", f"{median:.0f} min", "finished runs", color="white")] if median is not None else []),
        stat_card("Running", f"{counts.get('running',0):,}", "right now", color="blue.4"),
        stat_card("Waiting", f"{counts.get('queued',0):,}", "in line", color="white"),
    ]
    cards = dmc.SimpleGrid(stats, cols={"base": 2, "md": len(stats)}, spacing="sm", mb="sm")
    grid = dag.AgGrid(id="factory-grid", columnDefs=RUN_COLUMNS, rowModelType="infinite", style={"height": "calc(100dvh - 330px)", "minHeight": 360}, defaultColDef={**COLUMN_DEFAULTS, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True}, dashGridOptions=grid_options("No runs match these filters.", rowSelection={"mode": "singleRow", "enableClickSelection": True, "checkboxes": False}, cacheBlockSize=50, maxBlocksInCache=4, animateRows=False, suppressHorizontalScroll=True), getRowId="params.data.run_id", columnSize="responsiveSizeToFit", eventListeners=hide_when_narrow("symbol", "variation_count", "survivor_count", "completed_at"))
    detail = dmc.Drawer(dmc.Stack([
        dmc.Stack([dmc.Badge("No selection", id="factory-detail-state", color="gray"), dmc.Title("Pick a run", id="factory-detail-title", order=5, lineClamp=2), dmc.Text("Choose a row to see what it found.", id="factory-detail-meta", size="xs", c="dimmed")], gap=6),
        html.Div(id="factory-detail-stages", className="factory-stage-list"), html.Div(id="factory-detail-body", className="candidate-detail-body"),
    ], gap="md"), id="factory-detail-drawer", opened=False, position="right", size="min(100%, 420px)", withOverlay=False, lockScroll=False, title="Run details")
    workspace = dmc.Stack([grid, dmc.Group([dmc.Text(id="factory-page-count", size="xs", c="dimmed"), dmc.Text(id="factory-total-count", size="xs", c="dimmed")], justify="space-between")], gap="xs")
    stores = [dcc.Store(id="factory-query", data={"cohort": "completed", "search": "", "market": "all", "stage": "all", "resource": "all"}), dcc.Store(id="factory-selected", data=initial_selection), dcc.Store(id="factory-cache-reset")]
    return html.Div([*stores, detail, header, dmc.Box([toolbar, cards, workspace], p="lg")])


def register_factory_callbacks(application: Any) -> None:
    application.clientside_callback(
        """async function(query) {
            const api = await dash_ag_grid.getApiAsync('factory-grid');
            api.purgeInfiniteCache();
            return Date.now();
        }""",
        Output("factory-cache-reset","data"), Input("factory-query","data"),
        prevent_initial_call=True,
    )

    @application.callback(Output("factory-query","data"),Input("factory-cohort","value"),Input("factory-search","value"),Input("factory-market","value"),Input("factory-stage","value"),Input("factory-resource","value"))
    def query(cohort,search,market,stage,resource): return {"cohort":cohort or "completed","search":search or "","market":market or "all","stage":stage or "all","resource":resource or "all"}

    @application.callback(Output("factory-grid","getRowsResponse"),Output("factory-page-count","children"),Output("factory-total-count","children"),Input("factory-grid","getRowsRequest"),Input("factory-query","data"))
    def page(request,query):
        # Do not seal AG Grid's infinite cache as empty while the first request
        # races the query-store hydration. The populated store will trigger the
        # one authoritative response.
        if not request or not query: return no_update,no_update,no_update
        result=load_factory_page(start=int(request.get("startRow") or 0),end=int(request.get("endRow") or 50),sort_model=request.get("sortModel"),filter_model=request.get("filterModel"),**query)
        total=int(result["rowCount"]); return result,"" if total else "No runs match these filters.",f"{total:,} runs" if total else ""

    application.clientside_callback("(rows) => rows && rows.length ? true : window.dash_clientside.no_update", Output("factory-detail-drawer", "opened"), Input("factory-grid", "selectedRows"), prevent_initial_call=True)

    @application.callback(Output("factory-selected","data"),Input("factory-grid","selectedRows"),Input("factory-grid","getRowsResponse"),State("factory-selected","data"),prevent_initial_call=True)
    def select(rows,response,current):
        if rows: return rows[-1]
        if current: return current
        loaded=(response or {}).get("rowData") or []; return loaded[0] if loaded else None

    @application.callback(Output("factory-detail-state","children"),Output("factory-detail-state","color"),Output("factory-detail-title","children"),Output("factory-detail-meta","children"),Output("factory-detail-stages","children"),Output("factory-detail-body","children"),Input("factory-selected","data"))
    def detail(row):
        if not row: return "No selection", "gray", "Pick a run", "Choose a row to see what it found.", [], []
        status = str(row.get("status") or "unavailable").replace("_", " ").title(); stage = _stage_word(row.get("stage"))
        stages = [html.Div([html.Span(className=f"candidate-dot{' failed' if row.get('status')=='failed' else ''}"), html.Div([html.Strong(stage), html.P(row.get("results_note") or f"{row.get('variation_count',0):,} results")]), html.Time(status)], className="candidate-stage-row")]
        screened_out = int(row.get("screened_out_count") or 0)
        variations = int(row.get("variation_count") or 0)
        all_out = bool(screened_out and screened_out == variations)
        outcome = row.get("error_summary") or (
            f"All {variations:,} settings failed the first check"
            if all_out
            else f"{row.get('survivor_count',0):,} ideas passed" if row.get("variation_count") and row.get("status") == "succeeded"
            else row.get("results_note") if row.get("status") == "succeeded"
            else status
        )
        item = lambda label, value: html.Div([html.Span(label), value, html.Span()], className="candidate-evidence-item")
        body = [html.Div([html.Span("Outcome"), html.Strong(outcome), html.Small("No idea moved on from this run." if all_out else "")], className=f"factory-outcome-card{' screened-out' if all_out else ''}"), dmc.Group([dmc.Button("Open its ideas", id="factory-open-candidates"), dmc.Button("Open run results", id="factory-open-results", variant="default")], gap=8, className="candidate-detail-actions"), dmc.Title("Details", order=5, className="candidate-progression-title"), item("Run ID", copy_id(row.get("run_id"))), item("Machine", html.Strong(row.get("worker") or "Not recorded")), item("Machine state", html.Strong(row.get("resource_state") or "Not recorded"))]
        color = "gray" if all_out else "red" if row.get("status") == "failed" else "teal" if row.get("status") == "succeeded" else "blue"
        return FAILED_TESTING if all_out else status, color, row.get("title"), stage, stages, body


__all__=["factory_layout","register_factory_callbacks"]
