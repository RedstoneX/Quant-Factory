"""Production Submit Strategies validation workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update

from dashboard.submit_projection import candidate_example, validate_candidate_text, validate_upload


GLYPHS = {"dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷", "chart": "⌁", "external": "↗", "upload": "⇧"}
SUBMIT_COLUMNS = [
    {"field": "title", "headerName": "Definition", "minWidth": 220, "flex": 1.5},
    {"field": "filename", "headerName": "Source", "minWidth": 160, "flex": 1},
    {"field": "market", "headerName": "Market", "width": 100},
    {"field": "validation", "headerName": "Validation", "width": 110},
    {"field": "variations", "headerName": "Variations", "type": "numericColumn", "width": 105},
]


def _icon(name: str) -> html.Span: return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})
def _rail(name: str, label: str, item_id: str, *, active: bool=False, disabled: bool=False): return dmc.ActionIcon(_icon(name), id=item_id, className=f"rail-item{' active' if active else ''}", variant="subtle", disabled=disabled, **{"aria-label": label})


def _line(label: str, value: Any, suffix: Any = "") -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Span(suffix)], className="candidate-evidence-item")


def _batch_panel() -> html.Div:
    upload = dcc.Upload(
        id="submit-upload",
        children=html.Div([_icon("upload"), html.H3("Choose a Candidate package"), html.P("JSON, JSONL, YAML, or ZIP · validated in memory · 5 MB limit"), dmc.Button("Choose package", className="ghost", variant="default")]),
        accept=".json,.jsonl,.yaml,.yml,.zip", multiple=False, className="submit-upload-zone",
    )
    summary = html.Div([html.Div([html.Span(label), html.Strong("0", id=item_id, className=tone)]) for label,item_id,tone in [("Definitions","submit-count",""),("Valid","submit-valid","positive"),("Needs attention","submit-attention","warning"),("Review ready","submit-ready","positive")]], className="submit-summary-grid")
    grid = dag.AgGrid(id="submit-grid", columnDefs=SUBMIT_COLUMNS, rowData=[], defaultColDef={"sortable": True, "resizable": True, "filter": True}, dashGridOptions={"rowSelection":{"mode":"singleRow","enableClickSelection":True}}, className="ag-theme-quartz-dark submit-grid")
    left = dmc.Paper([html.Div([html.Div([html.H3("Batch package"),html.P("QF Candidate v1 packets using the published portable contract")])],className="panel-head"),upload,summary,html.Div([html.Div([html.Span("Projected variations"),html.Strong("0 / 250,000",id="submit-variations")],className="line"),dmc.Progress(id="submit-budget",value=0,color="blue",size="sm"),html.P("Valid definitions only · validation does not persist or launch research",className="muted tiny")],className="submit-budget"),grid],className="panel submit-package",radius="md")
    right = dmc.Paper([html.Div([html.Div([html.H3("Validation and batch policy"),html.P("Enforced mandates are not overridable")])],className="panel-head"),html.Div([_line("Intake contract","QF Candidate v1","Accepted"),_line("Packet ceiling","250 definitions","Enforced"),_line("Variation ceiling","250,000 / batch","Enforced"),html.Div([html.Strong("Enforced mandate · not overridable"),html.P("Positions must open and close in the same trading session.")],className="submit-mandate"),html.H3("Validation detail"),html.Div("Load a package to validate its definitions without changing canonical state.",id="submit-issues",className="submit-empty"),html.Div("Validated definitions remain local to this browser session. Canonical submission is unavailable in this read-only operator deployment.",className="candidate-explanation")],className="side-body")],className="panel submit-policy",radius="md")
    return html.Div([left,right],id="submit-batch",className="submit-workspace")


def _manual_panel() -> html.Div:
    editor = dmc.Paper([html.Div([html.Div([html.H3("Manual Candidate definition"),html.P("Paste one provider-neutral QF Candidate v1 packet")]),dmc.SegmentedControl(id="submit-manual-format",value="yaml",data=[{"value":"yaml","label":"YAML"},{"value":"json","label":"JSON"}],size="xs")],className="panel-head"),dmc.Textarea(id="submit-manual-text",value="",placeholder="Paste a QF Candidate v1 YAML or JSON packet…",autosize=False,className="submit-editor"),dmc.Group([dmc.Button("Load example",id="submit-load-example",className="ghost",variant="default"),dmc.Button("Validate definition",id="submit-manual-validate",className="primary")],gap=8,className="submit-editor-actions")],className="panel",radius="md")
    parsed = dmc.Paper([html.Div([html.Div([html.H3("Parsed research contract"),html.P("Review before anything enters the factory")]),dmc.Badge("Draft",id="submit-manual-state",color="yellow",variant="light")],className="panel-head"),html.Div(id="submit-manual-result",children=[html.Div("No definition validated.",className="submit-empty")],className="side-body")],className="panel",radius="md")
    return html.Div([editor,parsed],id="submit-manual",className="submit-workspace",style={"display":"none"})


def _api_panel() -> html.Div:
    info = dmc.Paper([html.Div([html.Div([html.H3("LLM and API intake"),html.P("Machine submissions use the same Candidate contract and validation gates")]),dmc.Badge("Contract ready",color="blue",variant="light")],className="panel-head"),html.Div([_line("Endpoint","Unavailable in read-only deployment","Not exposed"),_line("Schema","qf_candidate_v1",dcc.Clipboard(id="submit-copy-schema",content="qf_candidate_v1")),_line("Authentication","No machine intake credential loaded","Unavailable"),_line("Idempotency","Required when intake is activated","Enforced"),_line("Batch ceiling","250 definitions / 250,000 variations","")],className="side-body")],className="panel",radius="md")
    recent = dmc.Paper([html.Div([html.Div([html.H3("Recent machine submissions"),html.P("Exact source, validation, and resulting Candidate IDs")])],className="panel-head"),html.Div([html.Div("No machine submission audit is available in the canonical read-only state.",className="submit-empty"),dmc.Button("Validate repository example",id="submit-api-validate",className="primary"),html.Div(id="submit-api-result",className="submit-api-result")],className="side-body")],className="panel",radius="md")
    return html.Div([info,recent],id="submit-api",className="submit-workspace",style={"display":"none"})


def submit_layout() -> dmc.MantineProvider:
    nav=dmc.Stack([dmc.Paper("Q",className="logo",radius="md"),_rail("dashboard","Dashboard","submit-nav-dashboard"),_rail("file","Submit strategies","submit-nav-submit",active=True),_rail("flow","Factory runs","submit-nav-factory"),_rail("list","Candidates","submit-nav-candidates"),_rail("chart","Results","submit-nav-results"),html.Div(className="rail-spacer"),_rail("external","Paper Trading","submit-nav-paper"),dmc.Avatar("TO",className="avatar",radius="xl")],gap=7,align="center",className="rail")
    header=dmc.Group([html.Div([dmc.Title("Submit strategies",order=1),dmc.Text("Manual, batch, and machine intake",className="eyebrow")]),html.Div(className="top-spacer"),dmc.Button("Download schema",id="submit-download",className="ghost",variant="default"),dmc.Button("Canonical submission unavailable",disabled=True,className="primary")],gap=9,className="topbar")
    modes=dmc.Group([dmc.SegmentedControl(id="submit-mode",value="batch",data=[{"value":"manual","label":"Manual"},{"value":"batch","label":"Batch upload"},{"value":"api","label":"LLM / API"}],className="candidate-tabs"),html.Div(className="top-spacer"),dmc.Text("Validation is local and non-operational; canonical state is read-only",className="candidate-context")],className="candidate-filters submit-toolbar")
    body=html.Div([modes,_batch_panel(),_manual_panel(),_api_panel()],className="body submit-body")
    return dmc.MantineProvider(html.Div([dcc.Store(id="submit-batch-data"),dcc.Download(id="submit-download-file"),html.Div([nav,html.Main([header,body],className="main")],className="app submit-app")]),forceColorScheme="dark",theme={"fontFamily":"Inter, ui-sans-serif, sans-serif","primaryColor":"blue"})


def register_submit_callbacks(application: Any) -> None:
    @application.callback(Output("submit-batch","style"),Output("submit-manual","style"),Output("submit-api","style"),Input("submit-mode","value"))
    def mode(value): return ({}, {"display":"none"}, {"display":"none"}) if value=="batch" else ({"display":"none"},{},{"display":"none"}) if value=="manual" else ({"display":"none"},{"display":"none"},{})

    @application.callback(Output("submit-batch-data","data"),Input("submit-upload","contents"),State("submit-upload","filename"))
    def upload(contents,filename): return validate_upload(contents,filename)

    @application.callback(Output("submit-grid","rowData"),Output("submit-count","children"),Output("submit-valid","children"),Output("submit-attention","children"),Output("submit-ready","children"),Output("submit-variations","children"),Output("submit-budget","value"),Output("submit-issues","children"),Input("submit-batch-data","data"))
    def batch(data):
        data=data or {}; rows=data.get("rows") or []
        grid=[{**row,"validation":"Valid" if row.get("valid") else "Needs attention"} for row in rows]
        issues=[issue for row in rows for issue in row.get("issues",[]) if issue.get("severity") in {"error","warning"}]
        detail=[html.Div([html.Strong(f"{issue['path']} · {issue['severity'].title()}"),html.P(issue["message"])],className="submit-issue") for issue in issues[:8]] or html.Div("No validation issues." if rows else "Load a package to validate its definitions without changing canonical state.",className="submit-empty")
        variations=int(data.get("variations") or 0)
        return grid,str(data.get("definitions",0)),str(data.get("valid",0)),str(data.get("needs_attention",0)),str(data.get("ready",0)),f"{variations:,} / 250,000",min(100,variations/2500),detail

    @application.callback(Output("submit-manual-text","value"),Input("submit-load-example","n_clicks"),prevent_initial_call=True)
    def example(clicks): return candidate_example() if clicks else no_update

    @application.callback(Output("submit-manual-state","children"),Output("submit-manual-state","color"),Output("submit-manual-result","children"),Input("submit-manual-validate","n_clicks"),State("submit-manual-text","value"),State("submit-manual-format","value"),prevent_initial_call=True)
    def validate_manual(clicks,text,format_name):
        if not clicks: return no_update,no_update,no_update
        row=validate_candidate_text(text or "",filename=f"candidate.{format_name or 'yaml'}")
        issues=row.get("issues") or []
        children=[_line("Candidate",row.get("title"),"Parsed"),_line("Markets",row.get("market"),""),_line("Variations",f"{int(row.get('variations') or 0):,}","Bounded"),_line("Review readiness","Ready" if row.get("review_ready") else "Needs attention","")]
        children += [html.Div([html.Strong(f"{item['path']} · {item['severity'].title()}"),html.P(item["message"])],className="submit-issue") for item in issues[:6]]
        return ("Valid" if row.get("valid") else "Invalid"),("green" if row.get("valid") else "red"),children

    @application.callback(Output("submit-api-result","children"),Input("submit-api-validate","n_clicks"),prevent_initial_call=True)
    def api_example(clicks):
        if not clicks: return no_update
        row=validate_candidate_text(candidate_example(),filename="repository-example.json")
        return f"Repository example validated: {'valid and review ready' if row.get('review_ready') else 'attention required'} · {int(row.get('variations') or 0):,} variations. Nothing persisted."

    @application.callback(Output("submit-download-file","data"),Input("submit-download","n_clicks"),prevent_initial_call=True)
    def download(clicks): return dcc.send_string(candidate_example(),"qf-candidate-v1-example.json") if clicks else no_update


__all__=["submit_layout","register_submit_callbacks"]
