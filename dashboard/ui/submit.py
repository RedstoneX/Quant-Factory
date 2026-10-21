"""Production Submit Strategies validation workspace."""

from __future__ import annotations

import json
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, dcc, html, no_update
from dash_iconify import DashIconify

from dashboard.candidates_projection import load_candidate_detail
from dashboard.plain_labels import plain_status
from dashboard.ui.layout import page_header
from dashboard.ui.theme import COLUMN_DEFAULTS, grid_options, hide_when_narrow
from dashboard.ui.gateway_client import gateway_status, submit_candidate
from research_intake.starter_kit import starter_kit
from dashboard.submit_projection import candidate_example, validate_candidate_text, validate_upload


SUBMIT_COLUMNS = [
    {"field": "title", "headerName": "Idea", "minWidth": 140, "flex": 1.5},
    {"field": "filename", "headerName": "File", "minWidth": 120, "flex": 1},
    {"field": "market", "headerName": "Market", "flex": .6},
    {"field": "validation", "headerName": "Check", "minWidth": 110, "flex": .8},
    {"field": "variations", "headerName": "Variations", "type": "numericColumn", "flex": .6},
]


def starter_kit_json() -> str:
    """The starter kit (schema, example, guide) as one JSON document."""
    return json.dumps(starter_kit(), indent=2, ensure_ascii=False)


def idea_link(candidate_id: Any) -> str:
    return f"/report?candidate_id={candidate_id}"


def _latest_state(candidate_id: Any) -> tuple[str, str]:
    """Latest tester status for an idea; the gateway reply does not carry it."""
    detail = load_candidate_detail(str(candidate_id)) if candidate_id else None
    state = (detail or {}).get("campaign_state")
    if not state or state == "not_admitted":
        return "Received", "Saved. Waiting for the tester to pick it up"
    return plain_status(state, (detail or {}).get("campaign_reason_code"))


def submitted_notice(result: dict[str, Any], *, status: tuple[str, str] | None = None) -> html.Div:
    """Status and link shown after an idea is accepted."""
    label, why = status or _latest_state(result.get("candidate_id"))
    heading = f"Already submitted · {label}" if result.get("duplicate") else f"Submitted · {label}"
    return html.Div([html.Strong(heading), html.P(why), dcc.Link("Open this idea", href=idea_link(result.get("candidate_id")), refresh=False)], className="submit-issue")


def not_submittable_reason(row: dict[str, Any]) -> str:
    """Plain words for a file that reads as valid but cannot be submitted."""
    if row.get("review_ready") and row.get("canonical_json"):
        return ""
    problems = [i for i in (row.get("issues") or []) if i.get("severity") in {"error", "warning"}]
    detail = f" First problem: {problems[0].get('message')}" if problems else ""
    if row.get("valid"):
        return "The file is well formed, but it is not ready to submit yet: it has warnings or is missing something the tester needs." + detail
    return "The file has errors, so it cannot be submitted." + detail


def _line(label: str, value: Any, suffix: Any = "") -> html.Div:
    return html.Div([html.Span(label), html.Strong(value), html.Span(suffix)], className="candidate-evidence-item")


def _head(title: str, subtitle: str, *extra: Any) -> html.Div:
    return html.Div([html.Div([html.H3(title), html.P(subtitle)]), *extra], className="panel-head")


def _batch_panel(*, gateway_ready: bool) -> html.Div:
    upload = dcc.Upload(
        id="submit-upload",
        children=dmc.Stack([DashIconify(icon="tabler:upload", width=22), dmc.Text("Drop a file here, or click to choose one", size="sm"), dmc.Text("JSON, JSONL, YAML or ZIP · up to 5 MB · checked here, not saved", size="xs", c="dimmed")], align="center", gap=4, py="lg"),
        accept=".json,.jsonl,.yaml,.yml,.zip", multiple=False, className="submit-upload-zone",
    )
    summary = html.Div([html.Div([html.Span(label), html.Strong("0", id=item_id, className=tone)]) for label,item_id,tone in [("Ideas","submit-count",""),("Valid","submit-valid","positive"),("Need fixing","submit-attention","warning"),("Ready to submit","submit-ready","positive")]], className="submit-summary-grid")
    budget = dmc.Stack([dmc.Group([dmc.Text("Variations to test", size="xs", c="dimmed"), dmc.Text("0 / 250,000", id="submit-variations", size="xs")], justify="space-between"), dmc.Progress(id="submit-budget", value=0, size="sm")], gap=4, p="md")
    grid = dag.AgGrid(id="submit-grid", columnDefs=SUBMIT_COLUMNS, rowData=[], defaultColDef=COLUMN_DEFAULTS, eventListeners=hide_when_narrow("filename", "market", "variations"), dashGridOptions=grid_options("Choose a file to list its ideas here.", rowSelection={"mode":"singleRow","enableClickSelection":True,"checkboxes":False}), className="submit-grid", columnSize="responsiveSizeToFit")
    left = dmc.Paper([_head("Upload a file", "Ideas written in the QF Candidate v1 format"), upload, summary, budget, grid], className="panel submit-package")
    right = dmc.Paper([_head("Checks", "What happens when you press Submit"), html.Div([
        _line("File format", "QF Candidate v1", "Supported"),
        _line("Submission service", "Available" if gateway_ready else "Unavailable", "" if gateway_ready else "Try again later"),
        _line("Testing", "Not running"),
        dmc.Alert("Submitting saves your ideas. Testing starts only when a test campaign is switched on.", variant="light", color="gray", my="sm"),
        dmc.Title("Problems found", order=5),
        dmc.Text("Choose a file to check it.", id="submit-issues", size="xs", c="dimmed"),
        html.Div(id="submit-canonical-result"),
    ], className="side-body")], className="panel submit-policy")
    return html.Div([left,right],id="submit-batch",className="submit-workspace")


def _manual_panel(*, gateway_ready: bool) -> html.Div:
    editor = dmc.Paper([_head("Paste one idea", "YAML or JSON in the QF Candidate v1 format", dmc.SegmentedControl(id="submit-manual-format",value="yaml",data=[{"value":"yaml","label":"YAML"},{"value":"json","label":"JSON"}],size="xs")),dmc.Textarea(id="submit-manual-text",value="",placeholder="Paste one idea as YAML or JSON…",autosize=False,className="submit-editor"),dmc.Group([dmc.Button("Load example",id="submit-load-example",variant="default"),dmc.Button("Check",id="submit-manual-validate",variant="default"),dmc.Button("Submit",id="submit-manual-canonical",disabled=not gateway_ready)],gap=8,className="submit-editor-actions"),html.Div(id="submit-manual-submit-result",className="submit-api-result")],className="panel")
    parsed = dmc.Paper([_head("What the idea says", "Check this before you submit", dmc.Badge("Draft",id="submit-manual-state",color="yellow")),html.Div(id="submit-manual-result",children=[dmc.Text("Nothing checked yet.",size="xs",c="dimmed")],className="side-body")],className="panel")
    return html.Div([editor,parsed],id="submit-manual",className="submit-workspace",style={"display":"none"})


def _api_panel(status: dict[str, Any]) -> html.Div:
    gateway_ready = bool(status.get("ok"))
    info = dmc.Paper([_head("Send from a program", "Programs and AI assistants use the same format and checks", dmc.Badge("Service ready" if gateway_ready else "Service unavailable",color="green" if gateway_ready else "red")),html.Div([_line("Service","Private research gateway","Signed in" if gateway_ready else "Unavailable"),_line("Format","qf_candidate_v1",dcc.Clipboard(id="submit-copy-schema",content="qf_candidate_v1")),_line("Sign-in","Each program has its own identity","Required"),_line("Duplicates","Sending the same idea twice is ignored"),_line("Testing","Not running")],className="side-body")],className="panel")
    recent = dmc.Paper([_head("Try it", "Check the example idea that ships with the code"),html.Div([dmc.Text("Programs send ideas through the gateway client.",size="xs",c="dimmed"),dmc.Button("Check the example",id="submit-api-validate"),html.Div(id="submit-api-result",className="submit-api-result")],className="side-body")],className="panel")
    return html.Div([info,recent],id="submit-api",className="submit-workspace",style={"display":"none"})


def submit_layout() -> html.Div:
    status=gateway_status(); gateway_ready=bool(status.get("ok"))
    header=page_header("Submit ideas","Upload a file, paste one idea, or send them from a program",dmc.Button("Download starter kit",id="submit-download",variant="default"),dmc.Button("Submit",id="submit-canonical",disabled=True))
    modes=dmc.SegmentedControl(id="submit-mode",value="batch",size="xs",mb="sm",data=[{"value":"manual","label":"Paste one"},{"value":"batch","label":"Upload a file"},{"value":"api","label":"From a program"}])
    body=html.Div([modes,_batch_panel(gateway_ready=gateway_ready),_manual_panel(gateway_ready=gateway_ready),_api_panel(status)],className="body submit-body")
    return html.Div([dcc.Store(id="submit-batch-data"),dcc.Store(id="submit-gateway-ready",data=gateway_ready),dcc.Download(id="submit-download-file"),header,body],className="submit-app")

def register_submit_callbacks(application: Any) -> None:
    @application.callback(Output("submit-batch","style"),Output("submit-manual","style"),Output("submit-api","style"),Input("submit-mode","value"))
    def mode(value): return ({}, {"display":"none"}, {"display":"none"}) if value=="batch" else ({"display":"none"},{},{"display":"none"}) if value=="manual" else ({"display":"none"},{"display":"none"},{})

    @application.callback(Output("submit-batch-data","data"),Input("submit-upload","contents"),State("submit-upload","filename"))
    def upload(contents,filename): return validate_upload(contents,filename)

    @application.callback(Output("submit-grid","rowData"),Output("submit-count","children"),Output("submit-valid","children"),Output("submit-attention","children"),Output("submit-ready","children"),Output("submit-variations","children"),Output("submit-budget","value"),Output("submit-issues","children"),Input("submit-batch-data","data"))
    def batch(data):
        data=data or {}; rows=data.get("rows") or []
        grid=[{**row,"validation":("Valid" if row.get("review_ready") else "Valid, cannot submit yet") if row.get("valid") else "Needs attention"} for row in rows]
        issues=[issue for row in rows for issue in row.get("issues",[]) if issue.get("severity") in {"error","warning"}]
        detail=[html.Div([html.Strong(not_submittable_reason(row) or row.get("title",""))],className="submit-issue") for row in rows if row.get("valid") and not row.get("review_ready")][:4]+[html.Div([html.Strong(f"{issue['path']} · {issue['severity'].title()}"),html.P(issue["message"])],className="submit-issue") for issue in issues[:8]] or dmc.Text("No validation issues." if rows else "Choose a file to check it. Nothing is saved until you press Submit.",size="xs",c="dimmed")
        variations=int(data.get("variations") or 0)
        return grid,str(data.get("definitions",0)),str(data.get("valid",0)),str(data.get("needs_attention",0)),str(data.get("ready",0)),f"{variations:,} / 250,000",min(100,variations/2500),detail

    @application.callback(Output("submit-canonical","disabled"),Output("submit-canonical","children"),Input("submit-batch-data","data"),Input("submit-gateway-ready","data"))
    def canonical_button(data,gateway_ready):
        ready=int((data or {}).get("ready") or 0)
        if not gateway_ready or ready == 0: return True,"Submit"
        return False, f"Submit {ready:,} idea" + ("s" if ready != 1 else "")

    @application.callback(Output("submit-canonical-result","children"),Input("submit-canonical","n_clicks"),State("submit-batch-data","data"),prevent_initial_call=True)
    def submit_batch(clicks,data):
        if not clicks: return no_update
        rows=[row for row in ((data or {}).get("rows") or []) if row.get("review_ready") and row.get("canonical_json")]
        responses=[submit_candidate(str(row["canonical_json"])) for row in rows]
        accepted=[item for item in responses if item.get("ok")]
        identities=[str((item.get("result") or {}).get("candidate_id")) for item in accepted]
        failures=[str((item.get("error") or {}).get("message") or "Submission failed") for item in responses if not item.get("ok")]
        children=[]
        children.extend(submitted_notice(item.get("result") or {}) for item in accepted)
        children.extend(html.Div(message,className="submit-issue") for message in failures)
        return children or "No idea was ready to submit."

    @application.callback(Output("submit-manual-text","value"),Input("submit-load-example","n_clicks"),prevent_initial_call=True)
    def example(clicks): return candidate_example() if clicks else no_update

    @application.callback(Output("submit-manual-state","children"),Output("submit-manual-state","color"),Output("submit-manual-result","children"),Input("submit-manual-validate","n_clicks"),State("submit-manual-text","value"),State("submit-manual-format","value"),prevent_initial_call=True)
    def validate_manual(clicks,text,format_name):
        if not clicks: return no_update,no_update,no_update
        row=validate_candidate_text(text or "",filename=f"candidate.{format_name or 'yaml'}")
        issues=row.get("issues") or []
        children=[_line("Idea",row.get("title"),""),_line("Markets",row.get("market"),""),_line("Variations",f"{int(row.get('variations') or 0):,}",""),_line("Ready to submit","Yes" if row.get("review_ready") else "Needs fixing","")]
        children += [html.Div([html.Strong(f"{item['path']} · {item['severity'].title()}"),html.P(item["message"])],className="submit-issue") for item in issues[:6]]
        return ("Valid" if row.get("valid") else "Invalid"),("green" if row.get("valid") else "red"),children

    @application.callback(Output("submit-manual-submit-result","children"),Input("submit-manual-canonical","n_clicks"),State("submit-manual-text","value"),State("submit-manual-format","value"),prevent_initial_call=True)
    def submit_manual(clicks,text,format_name):
        if not clicks: return no_update
        row=validate_candidate_text(text or "",filename=f"candidate.{format_name or 'yaml'}")
        if not row.get("review_ready") or not row.get("canonical_json"):
            return not_submittable_reason(row) or "This idea cannot be submitted yet."
        response=submit_candidate(str(row["canonical_json"]))
        if not response.get("ok"):
            return str((response.get("error") or {}).get("message") or "Canonical submission failed.")
        result=response.get("result") or {}
        return submitted_notice(result)

    @application.callback(Output("submit-api-result","children"),Input("submit-api-validate","n_clicks"),prevent_initial_call=True)
    def api_example(clicks):
        if not clicks: return no_update
        row=validate_candidate_text(candidate_example(),filename="repository-example.json")
        return f"Example checked: {'valid and ready to submit' if row.get('review_ready') else 'needs fixing'} · {int(row.get('variations') or 0):,} variations. Nothing was saved."

    @application.callback(Output("submit-download-file","data"),Input("submit-download","n_clicks"),prevent_initial_call=True)
    def download(clicks): return dcc.send_string(starter_kit_json(),"qf-candidate-v1-starter-kit.json") if clicks else no_update


__all__=["submit_layout","register_submit_callbacks","starter_kit_json","submitted_notice","not_submittable_reason"]
