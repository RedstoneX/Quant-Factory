"""New idea page: check ideas, see where they will go in the factory's line, submit them.

Thin Dash Mantine layer. Checking is submit_projection (same parser and validator as the old Submit page), submitting is the
gateway client (same readiness check and call), the line and typical time are factory_overview (same as /factory). Exports
layout() and register_callbacks(app); the route is wired in app.py by the caller.
"""

from __future__ import annotations

from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update

from dashboard.factory_overview import load_factory_overview
from dashboard.new_idea_projection import NEXT_STEPS, bar_text, button, review_batch, submitted_state, typical_text, where_they_go
from dashboard.submit_projection import candidate_example, validate_candidate_text, validate_upload
from dashboard.ui.gateway_client import gateway_status, submit_candidate
from dashboard.ui.idea_report import BG, MONO, REPORT_THEME, SANS, TEXT
from dashboard.ui.submit import not_submittable_reason, starter_kit_json

REFRESH_MS = 30_000
MODES = [{"value": "upload", "label": "Upload a file"}, {"value": "paste", "label": "Paste one"}, {"value": "program", "label": "From a program"}]
HIDDEN = {"display": "none"}


def _overview() -> dict[str, Any]:
    return load_factory_overview()


def token_sentence(tokens: list[dict[str, str]]) -> html.Div:
    return html.Div([html.Span(token["text"], className=f"ni-{token['kind']}") for token in tokens], className="ni-sentence")


def idea_card(card: dict[str, Any]) -> html.Div:
    chip = html.Span("READY" if card["ready"] else "NEEDS FIXING", className="ni-chip " + ("ok" if card["ready"] else "bad"))
    body = [html.Div([html.Div([html.Span(card["name"], className="ni-name"), html.Span(card["meta"], className="ni-muted") if card["meta"] else None], className="ni-col"), chip], className="ni-between")]
    if card["tokens"]:
        body.append(token_sentence(card["tokens"]))
    body.append(html.Div([html.Span(["Combinations ", html.B(card["combinations"], className="ni-mono")]), html.Span(["Data ", html.B(card["data"])])], className="ni-foot"))
    if card["problem"]:
        body.append(html.Div(card["problem"], className="ni-problem"))
    return html.Div(body, className="ni-card" + ("" if card["ready"] else " bad"))


def check_panel(review: dict[str, Any], overview: dict[str, Any]) -> list[Any]:
    counts = html.Div([html.Div([html.Div("Ready", className="ni-stat-label"), html.Div(str(review["ready"]), className="ni-stat-value", style={"color": "#5EEAB0"})], className="ni-stat"),
                       html.Div([html.Div("Need fixing", className="ni-stat-label"), html.Div(str(review["left_out"]), className="ni-stat-value", style={"color": "#F2545B" if review["left_out"] else "#9BA1AB"})], className="ni-stat")], className="ni-stats")
    bar = html.Div([html.Div([html.Span("Combinations in this batch"), html.Span(review["budget_text"], className="ni-mono ni-text")], className="ni-between ni-small"),
                    dmc.Progress(value=max(review["budget_percent"], 1 if review["combinations"] else 0), size="sm", color="red" if review["over_budget"] else "indigo")], className="ni-col")
    return [html.H2("Check", className="ni-h"), counts, bar,
            html.Div(["Typical test time ", html.B(typical_text(overview.get("typical_minutes")), className="ni-mono ni-text"), " (median of recent tests)" if overview.get("typical_minutes") else ""], className="ni-small ni-muted"),
            html.Div("Ideas that need fixing are left out.", className="ni-muted")]


def line_rows(rows: list[dict[str, str]]) -> list[Any]:
    return [html.Div([html.Span([html.Span(row["n"], className="ni-n"), html.Span(row["name"])]), html.Span(row["when"], className="ni-mono ni-muted2")], className=f"ni-row {row['kind']}") for row in rows] or [html.Div("Nothing in line.", className="ni-muted")]


def _next_steps() -> list[Any]:
    return [html.Div([html.Span(str(step["n"]), className="ni-step-n"), html.Span(step["name"], className="ni-grow"), html.Span(step["what"], className="ni-muted")], className="ni-step") for step in NEXT_STEPS]


def _upload() -> dcc.Upload:
    icon = html.Span("↑", className="ni-up-icon")
    text = html.Div([html.Div("Drop a file here, or click to choose one", id="ni-file-line", className="ni-name"), html.Div("JSON, JSONL, YAML or ZIP · up to 5 MB · checked here, not saved", id="ni-file-sub", className="ni-muted")], className="ni-grow")
    return dcc.Upload(id="ni-upload", children=html.Div([icon, text], className="ni-upload-row"), accept=".json,.jsonl,.yaml,.yml,.zip", multiple=False, className="ni-upload")


def _paste() -> html.Div:
    return html.Div([
        html.Div([html.Span("Paste one idea", className="ni-name"), dmc.SegmentedControl(id="ni-paste-format", value="yaml", size="xs", data=[{"value": "yaml", "label": "YAML"}, {"value": "json", "label": "JSON"}])], className="ni-between"),
        dmc.Textarea(id="ni-paste-text", value="", placeholder="Paste one idea as YAML or JSON in the QF Candidate v1 format…", autosize=False, minRows=10, className="ni-editor"),
        dmc.Group([dmc.Button("Load example", id="ni-paste-example", variant="default"), dmc.Button("Check", id="ni-paste-check", variant="default")], gap=8),
    ], id="ni-pane-paste", className="ni-pane", style=HIDDEN)


def _program(status_ok: bool) -> html.Div:
    return html.Div([
        html.Div([html.Span("Send from a program", className="ni-name"), html.Span("Service ready" if status_ok else "Service unavailable", className="ni-chip " + ("ok" if status_ok else "bad"))], className="ni-between"),
        html.Div("Programs and AI assistants use the same format and checks, and each has its own sign-in. Sending the same idea twice is ignored. Ideas they send join the same line.", className="ni-muted"),
        html.A("Download the starter kit", id="ni-kit-link", href="#", className="ni-small"),
        dcc.Download(id="ni-kit-file"),
    ], id="ni-pane-program", className="ni-pane", style=HIDDEN)


def layout() -> html.Div:
    ready = bool(gateway_status().get("ok"))
    review = review_batch(None)
    overview = _overview()
    top = html.Section([html.Div([html.H1("New idea", className="ni-title"), html.P("Add one idea or a file of them. Each one is checked here first. Submitted ideas join the line and are tested automatically, one at a time.", className="ni-lede")]),
                        dmc.SegmentedControl(id="ni-mode", value="upload", data=MODES, className="ni-tabs")], className="ni-top")
    left = html.Div([html.Div(_upload(), id="ni-pane-upload"), _paste(), _program(ready), html.Div(id="ni-cards", className="ni-cards")], className="ni-left")
    check = html.Div(check_panel(review, overview), id="ni-check", className="ni-panel ni-check")
    line = html.Div([html.Div([html.H2("Where they'll go", className="ni-h"), html.A("Open Factory →", href="/factory", className="ni-small")], className="ni-between"),
                     html.Div(line_rows(where_they_go(overview, 0)), id="ni-line", className="ni-col"),
                     html.Div("Start times are estimates: typical test time × place in line.", className="ni-muted")], className="ni-panel ni-line")
    steps = html.Div([html.H2("What happens next", className="ni-h"), *_next_steps()], className="ni-panel ni-steps")
    bar = html.Div(html.Div([html.Span(bar_text(review, overview), id="ni-bar-text", className="ni-bar-text"),
                             html.Div([html.A("Watch on Factory →", id="ni-watch", href="/factory", style=HIDDEN, className="ni-watch"),
                                       dmc.Button("Submit and test ideas", id="ni-submit", disabled=True, className="ni-submit")], className="ni-bar-actions")], className="ni-bar-in"), className="ni-bar")
    page = html.Div([top, html.Section([left, check, line, steps], className="ni-grid"), bar, html.Div(id="ni-notes", className="ni-notes")], className="ni-page")
    return html.Div([dcc.Interval(id="ni-tick", interval=REFRESH_MS), dcc.Store(id="ni-batch"), dcc.Store(id="ni-result"), dcc.Store(id="ni-gateway-ready", data=ready),
                     dmc.MantineProvider(page, theme=REPORT_THEME, forceColorScheme="dark")], className="ni-root", style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_callbacks(app: Any) -> None:
    @app.callback(Output("ni-pane-upload", "style"), Output("ni-pane-paste", "style"), Output("ni-pane-program", "style"), Input("ni-mode", "value"))
    def show_mode(mode):
        return tuple({} if mode == name else HIDDEN for name in ("upload", "paste", "program"))

    @app.callback(Output("ni-paste-text", "value"), Input("ni-paste-example", "n_clicks"), prevent_initial_call=True)
    def load_example(clicks):
        return candidate_example() if clicks else no_update

    @app.callback(Output("ni-kit-file", "data"), Input("ni-kit-link", "n_clicks"), prevent_initial_call=True)
    def kit(clicks):
        return dcc.send_string(starter_kit_json(), "qf-candidate-v1-starter-kit.json") if clicks else no_update

    @app.callback(Output("ni-batch", "data"), Output("ni-result", "data"), Input("ni-upload", "contents"), Input("ni-paste-check", "n_clicks"),
                  State("ni-upload", "filename"), State("ni-paste-text", "value"), State("ni-paste-format", "value"), prevent_initial_call=True)
    def check(contents, clicks, filename, text, format_name):
        if ctx.triggered_id == "ni-paste-check":
            row = validate_candidate_text(text or "", filename=f"candidate.{format_name or 'yaml'}")
            batch = {"package": "Pasted idea", "rows": [row], "definitions": 1}
        else:
            batch = validate_upload(contents, filename)
        return batch, None

    @app.callback(Output("ni-result", "data", allow_duplicate=True), Input("ni-submit", "n_clicks"), State("ni-batch", "data"), State("ni-result", "data"), prevent_initial_call=True)
    def submit(clicks, batch, result):
        if not clicks or result:
            return no_update
        review = review_batch(batch, reason=not_submittable_reason)
        if not review["ready"]:
            return no_update
        before = _overview()  # place in line is measured before our ideas join it
        responses = [submit_candidate(str(row["canonical_json"])) for row in review["submit_rows"]]
        return submitted_state(responses, before)

    @app.callback(Output("ni-cards", "children"), Output("ni-check", "children"), Output("ni-line", "children"), Output("ni-bar-text", "children"),
                  Output("ni-submit", "children"), Output("ni-submit", "disabled"), Output("ni-watch", "style"), Output("ni-notes", "children"),
                  Output("ni-file-line", "children"), Output("ni-file-sub", "children"),
                  Input("ni-batch", "data"), Input("ni-result", "data"), Input("ni-tick", "n_intervals"), Input("ni-gateway-ready", "data"), State("ni-upload", "filename"))
    def render(batch, result, _tick, gateway_ready, filename):
        review = review_batch(batch, reason=not_submittable_reason)
        overview = _overview()
        if result:
            text, disabled, label = result["text"], True, ("Queued" if result.get("queued") else "Nothing queued")
            watch, notes = {}, [html.Div(note, className="ni-note") for note in result.get("notes") or []]
            rows = where_they_go(overview, 0)
        else:
            label, disabled = button(review, bool(gateway_ready))
            text, watch, notes = bar_text(review, overview), HIDDEN, []
            rows = where_they_go(overview, review["ready"])
        name = (batch or {}).get("package") or "Drop a file here, or click to choose one"
        sub = f"{review['total']} idea{'s' if review['total'] != 1 else ''} · checked here, nothing saved until you submit" if review["total"] else "JSON, JSONL, YAML or ZIP · up to 5 MB · checked here, not saved"
        return [idea_card(card) for card in review["cards"]], check_panel(review, overview), line_rows(rows), text, label, disabled, watch, notes, name, sub
