"""Production Factory runs workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update

from dashboard.factory_projection import load_factory_page, load_factory_summary


GLYPHS = {"dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷", "chart": "⌁", "external": "↗", "search": "⌕"}
RUN_COLUMNS = [
    {"field": "title", "headerName": "Run", "minWidth": 190, "flex": 1.5, "pinned": "left", "filter": "agTextColumnFilter"},
    {"field": "symbol", "headerName": "Market", "width": 78, "filter": "agTextColumnFilter"},
    {"field": "status", "headerName": "Outcome", "width": 92, "filter": "agTextColumnFilter", "valueFormatter": {"function": "params.value ? params.value.charAt(0).toUpperCase()+params.value.slice(1) : '—'"}},
    {"field": "variation_count", "headerName": "Results", "type": "numericColumn", "width": 86},
    {"field": "survivor_count", "headerName": "Survivors", "type": "numericColumn", "width": 88},
    {"field": "completed_at", "headerName": "Completed", "minWidth": 145, "flex": 1},
]


def _icon(name: str) -> html.Span: return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})
def _rail(name: str, label: str, item_id: str, *, active: bool=False, disabled: bool=False): return dmc.ActionIcon(_icon(name), id=item_id, className=f"rail-item{' active' if active else ''}", variant="subtle", disabled=disabled, **{"aria-label": label})


def factory_layout() -> dmc.MantineProvider:
    summary = load_factory_summary(); counts = summary.get("counts", {})
    nav = dmc.Stack([dmc.Paper("Q", className="logo", radius="md"), _rail("dashboard","Dashboard","factory-nav-dashboard"), _rail("file","Submit strategies","factory-nav-submit"), _rail("flow","Factory runs","factory-nav-factory",active=True), _rail("list","Candidates","factory-nav-candidates"), _rail("chart","Results","factory-nav-results"), html.Div(className="rail-spacer"), _rail("external","Paper Trading","factory-nav-paper"), dmc.Avatar("TO",className="avatar",radius="xl")],gap=7,align="center",className="rail")
    header = dmc.Group([html.Div([dmc.Title("Factory runs",order=1),dmc.Text("Open work and persisted outcomes",className="eyebrow")]),html.Div(className="top-spacer"),dmc.Badge(f"{counts.get('running',0):,} running",className="candidate-state"),dmc.Badge(f"{counts.get('queued',0):,} queued",className="filter-chip"),dmc.Badge(f"{counts.get('failed',0):,} failed",color="red",variant="light")],gap=9,className="topbar")
    tabs=dmc.SegmentedControl(id="factory-cohort",value="completed",data=[{"value":"open","label":f"Open · {counts.get('open',0):,}"},{"value":"completed","label":f"Completed · {counts.get('completed',0):,}"},{"value":"failed","label":f"Failed · {counts.get('failed',0):,}"}],className="candidate-tabs",persistence=True,persistence_type="local")
    markets=[{"value":"all","label":"All markets"}]+[{"value":x,"label":x} for x in summary.get("markets",[])]
    stages=[{"value":"all","label":"All stages"}]+[{"value":x,"label":str(x).replace("_"," ").title()} for x in summary.get("stages",[])]
    toolbar=dmc.Group([tabs,dmc.TextInput(id="factory-search",placeholder="Search run or campaign…",leftSection=_icon("search"),debounce=True,className="candidate-search"),dmc.Select(id="factory-market",data=markets,value="all",allowDeselect=False,className="candidate-select"),html.Div(className="top-spacer"),dmc.Text("Outcomes retained indefinitely",className="candidate-context")],gap=8,className="candidate-filters factory-toolbar")
    cards=html.Div([html.Div([html.Span("24h throughput"),html.Strong(f"{summary.get('throughput_24h',0):,}"),html.Small("persisted parameter results")],className="factory-summary"),html.Div([html.Span("Median runtime"),html.Strong(f"{summary['median_minutes']:.0f}m" if summary.get("median_minutes") is not None else "—"),html.Small("completed runs")],className="factory-summary"),html.Div([html.Span("Worker utilization"),html.Strong("—"),html.Small("not persisted")],className="factory-summary"),html.Div([html.Span("Running"),html.Strong(f"{counts.get('running',0):,}"),html.Small("exact run state")],className="factory-summary"),html.Div([html.Span("Queued"),html.Strong(f"{counts.get('queued',0):,}"),html.Small("exact run state")],className="factory-summary")],className="factory-summary-grid")
    filters=dmc.Group([dmc.Select(id="factory-stage",data=stages,value="all",allowDeselect=False,className="candidate-select evidence"),dmc.Select(id="factory-resource",data=[{"value":"all","label":"All resource states"},{"value":"unavailable","label":"Resource state unavailable"}],value="all",allowDeselect=False,className="candidate-select evidence"),html.Div(className="top-spacer"),dmc.Text("Elapsed time and resource use shown only when persisted",className="candidate-context")],gap=8,className="candidate-filters")
    grid=dag.AgGrid(id="factory-grid",columnDefs=RUN_COLUMNS,rowModelType="infinite",defaultColDef={"sortable":True,"resizable":True,"filter":True},dashGridOptions={"rowSelection":{"mode":"singleRow","enableClickSelection":True},"cacheBlockSize":50,"maxBlocksInCache":4,"animateRows":False},getRowId="params.data.run_id",className="ag-theme-quartz-dark factory-grid")
    detail=dmc.Paper([html.Div([dmc.Badge("No selection",id="factory-detail-state",className="candidate-state"),dmc.Title("No run selected",id="factory-detail-title",order=2),dmc.Text("Choose an exact persisted run.",id="factory-detail-meta",className="candidate-detail-meta")],className="candidate-detail-head"),html.Div(id="factory-detail-stages",className="factory-stage-list"),html.Div(id="factory-detail-body",className="candidate-detail-body")],className="candidate-detail",radius=0,withBorder=False)
    workspace=dmc.Paper([html.Div([grid,html.Footer([html.Span("0 loaded",id="factory-page-count"),html.Span("•"),html.Span("0 total",id="factory-total-count"),html.Div(className="top-spacer"),html.Span("Exact logs and outcomes retained")],className="candidate-grid-footer")],className="candidate-grid-region"),detail],className="factory-workspace",radius="md",withBorder=True)
    stores=[dcc.Store(id="factory-query"),dcc.Store(id="factory-selected")]
    body=html.Div([toolbar,cards,filters,workspace],className="body factory-body")
    return dmc.MantineProvider(html.Div([*stores,html.Div([nav,html.Main([header,body],className="main")],className="app factory-app")]),forceColorScheme="dark",theme={"fontFamily":"Inter, ui-sans-serif, sans-serif","primaryColor":"blue"})


def register_factory_callbacks(application: Any) -> None:
    @application.callback(Output("factory-query","data"),Input("factory-cohort","value"),Input("factory-search","value"),Input("factory-market","value"),Input("factory-stage","value"),Input("factory-resource","value"))
    def query(cohort,search,market,stage,resource): return {"cohort":cohort or "completed","search":search or "","market":market or "all","stage":stage or "all","resource":resource or "all"}

    @application.callback(Output("factory-grid","getRowsResponse"),Output("factory-page-count","children"),Output("factory-total-count","children"),Input("factory-grid","getRowsRequest"),Input("factory-query","data"))
    def page(request,query):
        if not request or not query: return {"rowData":[],"rowCount":0},"0 loaded","0 total"
        result=load_factory_page(start=int(request.get("startRow") or 0),end=int(request.get("endRow") or 50),sort_model=request.get("sortModel"),filter_model=request.get("filterModel"),**query)
        return result,f"{len(result['rowData']):,} loaded",f"{result['rowCount']:,} total · infinite row loading"

    @application.callback(Output("factory-selected","data"),Input("factory-grid","selectedRows"),Input("factory-grid","getRowsResponse"),State("factory-selected","data"),prevent_initial_call=True)
    def select(rows,response,current):
        if rows: return rows[-1]
        if current: return current
        loaded=(response or {}).get("rowData") or []; return loaded[0] if loaded else None

    @application.callback(Output("factory-detail-state","children"),Output("factory-detail-title","children"),Output("factory-detail-meta","children"),Output("factory-detail-stages","children"),Output("factory-detail-body","children"),Input("factory-selected","data"))
    def detail(row):
        if not row: return "No selection","No run selected","Choose an exact persisted run.",[],[dmc.Text("No persisted run selected.",className="candidate-empty")]
        status=str(row.get("status") or "unavailable").replace("_"," ").title(); stage=str(row.get("stage") or "unavailable").replace("_"," ").title()
        stages=[html.Div([html.Span(className=f"candidate-dot{' failed' if row.get('status')=='failed' else ''}"),html.Div([html.Strong(stage),html.P(f"{row.get('variation_count',0):,} persisted result rows")]),html.Time(status)],className="candidate-stage-row")]
        outcome=row.get("error_summary") or (f"{row.get('survivor_count',0):,} verified survivor markers" if row.get("status")=="succeeded" else status)
        body=[html.Div([html.Span("Persisted outcome"),html.Strong(outcome),html.Span("Exact")],className="candidate-evidence-item"),html.Div([html.Span("Owner action"),html.Strong("None · retained outcome"),html.Span()],className="candidate-evidence-item"),dmc.Group([dmc.Button("Open resulting Candidates",id="factory-open-candidates",className="primary"),dmc.Button("Open run Results",id="factory-open-results",className="ghost",variant="default")],gap=8,className="candidate-detail-actions"),dmc.Title("Diagnostics and lineage",order=3,className="candidate-progression-title"),html.Div([html.Span("Run identity"),html.Strong(row.get("run_id")),html.Span("Persisted")],className="candidate-evidence-item"),html.Div([html.Span("Worker"),html.Strong(row.get("worker") or "Unavailable"),html.Span()],className="candidate-evidence-item"),html.Div([html.Span("Resource state"),html.Strong(row.get("resource_state") or "Unavailable"),html.Span()],className="candidate-evidence-item")]
        return status,row.get("title"),f"{row.get('run_id')} · {stage}",stages,body


__all__=["factory_layout","register_factory_callbacks"]
