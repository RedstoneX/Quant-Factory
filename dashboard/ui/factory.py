"""Production Factory runs workspace."""

from __future__ import annotations

from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash_iconify import DashIconify
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import quote


from dashboard.factory_projection import OUTCOME_WORDS, load_factory_overview, load_factory_page, load_factory_summary
from dashboard.ui.idea_report import AMBER, BG, FAINT, GREEN, HOLD, INDIGO, LINE, MONO, REPORT_THEME, RED, SANS, TEXT
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




# ---------------------------------------------------------------------------------------------------------------------
# Factory oversight page: read-only, refreshes itself every 10 s. All numbers come from factory_projection.load_factory_overview.
# Export layout() and register_callbacks(app); the route and nav are wired in app.py by the caller.
# ---------------------------------------------------------------------------------------------------------------------
REFRESH_MS = 10_000
OUTCOME_COLOR = {"failed": "#2E3340", "close": AMBER, "passed": GREEN, "crashed": RED, "running": INDIGO}
TONE_COLOR = {"green": GREEN, "amber": AMBER, "red": RED, "grey": HOLD, "indigo": INDIGO, "text": TEXT}
ICON = {"green": "✓", "amber": "!", "red": "×"}
STEP_CLASS = {"done": "done", "current": "current", "slow": "slow", "todo": "todo"}
NEUTRAL_FIGURE = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family=MONO, color=FAINT, size=11))
GRAPH_CONFIG = {"displayModeBar": False}
OUTPUTS = ("fo-pill", "fo-date", "fo-headline", "fo-tiles", "fo-running", "fo-alerts", "fo-old-title", "fo-old-items", "fo-old-wrap", "fo-needs",
           "fo-queue-head", "fo-queue", "fo-timeline", "fo-hourly", "fo-health", "fo-health-checked", "fo-log")


def _report_href(candidate_id: str | None) -> str | None:
    return f"/report?candidate_id={quote(str(candidate_id), safe='')}" if candidate_id else None


def _link(text: Any, candidate_id: str | None, **props: Any) -> Any:
    href = _report_href(candidate_id)
    return html.A(text, href=href, **props) if href else html.Span(text, **props)


def sparkline(values: list[float], color: str) -> dcc.Graph:
    figure = go.Figure(go.Scatter(y=values, mode="lines", line=dict(color=TONE_COLOR.get(color, TEXT), width=1.5, shape="spline", smoothing=0.6), hoverinfo="skip"))
    figure.update_layout(height=28, width=88, margin=dict(l=0, r=0, t=2, b=2), xaxis=dict(visible=False), yaxis=dict(visible=False, rangemode="tozero"), showlegend=False, **NEUTRAL_FIGURE)
    return dcc.Graph(figure=figure, config={**GRAPH_CONFIG, "staticPlot": True}, className="fo-spark", style={"height": 28, "width": 88})


def tiles(data: dict[str, Any]) -> list[Any]:
    out = []
    for tile in data["tiles"]:
        title = "Each tile's line shows the last 24 hours"
        out.append(html.Div([html.Span(tile["label"], className="fo-tile-label"),
                             html.Div([html.Span(tile["value"], className="fo-tile-value", style={"color": TONE_COLOR[tile["color"]]}), sparkline(tile["spark"], tile["color"])], className="fo-tile-row"),
                             html.Span(tile["sub"], className="fo-tile-sub")], className="fo-tile", title=title))
    return out


def running_cards(data: dict[str, Any]) -> list[Any]:
    if not data["running"]:
        return [html.Div("Nothing is running. The next waiting test starts on its own.", className="fo-empty")]
    return [html.Div([
        html.Div([_link(card["name"], card["candidate_id"], className="fo-name"), html.Span(card["elapsed"], className="fo-mono" + (" fo-amber" if card["slow"] else ""))], className="fo-between"),
        html.Div([html.Div(className=f"fo-step {STEP_CLASS[step]}") for step in card["steps"]], className="fo-steps"),
        html.Div([html.Span(card["where"]), html.Span(card["note"])], className="fo-between fo-muted")], className="fo-inner") for card in data["running"]]


def alert_cards(data: dict[str, Any]) -> list[Any]:
    out = []
    for alert in data["alerts"]:
        link = _report_href(alert["candidate_id"])
        out.append(html.Div([html.Span(className=f"fo-dot {alert['tone']}"), html.Div([
            html.Div([html.Span(alert["title"], className="fo-name"), html.Span(alert["when"], className="fo-mono fo-muted")], className="fo-between"),
            html.Span(alert["body"], className="fo-body"),
            html.Span([alert["next"], " ", html.A("Open report →", href=link)] if link else alert["next"], className="fo-muted")], className="fo-col")], className=f"fo-alert {alert['tone']}"))
    return out


def old_run_items(data: dict[str, Any]) -> list[Any]:
    old = data["old_runs"]
    return [html.Div([_link(item["name"], item["candidate_id"]), html.Span(item["when"], className="fo-mono fo-muted")], className="fo-between fo-old-row") for item in (old["items"] if old else [])]


def queue_rows(data: dict[str, Any]) -> list[Any]:
    rows = [html.Div([html.Span([html.Span(str(row["n"]), className="fo-mono fo-muted fo-n"), _link(row["name"], row["candidate_id"])]), html.Span(f"{row['who']} · {row['when']}", className="fo-muted")], className="fo-between fo-row") for row in data["queue"]["next"]]
    return rows or [html.Div("Nothing is waiting.", className="fo-empty")]


def queue_head(data: dict[str, Any]) -> list[Any]:
    queue = data["queue"]
    if not queue["total"]:
        return [html.Span("Waiting in line", className="fo-h"), html.Span("0", className="fo-muted")]
    start = html.Span(f"next starts in {queue['next_start']}", title="estimate: typical test time x position in line") if queue["next_start"] else None
    return [html.Span("Waiting in line", className="fo-h"), html.Span([f"{queue['total']}", " · " if start else "", start] if start else [f"{queue['total']}"], className="fo-muted")]


def timeline_figure(rows: list[dict[str, Any]], now: Any) -> go.Figure:
    now = pd.Timestamp(now)
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["name", "start", "end", "minutes", "outcome", "candidate_id"])
    if rows:
        frame["Lane"] = "Factory"
        frame["Outcome"] = frame["outcome"].map(OUTCOME_WORDS)
        frame["Took"] = frame["minutes"].map(lambda m: f"{int(m)} min {int(round((m - int(m)) * 60)):02d} s" if m >= 1 else f"{int(round(m * 60))} s")
        figure = px.timeline(frame, x_start="start", x_end="end", y="Lane", color="Outcome", color_discrete_map={OUTCOME_WORDS[k]: v for k, v in OUTCOME_COLOR.items()}, custom_data=["name", "Took", "Outcome", "candidate_id"])
        figure.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]}<extra></extra>", width=0.9)
        for trace in figure.data:
            trace.marker.line = dict(width=1, color=trace.marker.color)  # a one-second test still shows as a hairline
    else:
        figure = go.Figure()
        figure.add_annotation(text="No tests in the last 12 hours", showarrow=False, font=dict(color=FAINT, size=12), xref="paper", yref="paper", x=0.5, y=0.5)
    window = [now - pd.Timedelta(hours=12), now]
    figure.add_shape(type="line", x0=now, x1=now, y0=-0.25, y1=1.25, yref="paper", line=dict(color="rgba(236,237,238,0.55)", width=1, dash="dash"))
    figure.update_layout(height=76, margin=dict(l=0, r=0, t=6, b=26), showlegend=False, hoverlabel=dict(font_family=SANS, bgcolor="#131519", bordercolor=LINE),
                         xaxis=dict(range=window, gridcolor="#1A1C21", tickformat="%H:%M", dtick=7200000, showline=False), yaxis=dict(visible=False), bargap=0, **NEUTRAL_FIGURE)
    return figure


def hourly_figure(rows: list[dict[str, Any]]) -> go.Figure:
    figure = go.Figure()
    hours = [row["hour"] for row in rows]
    for key in ("failed", "close", "passed", "crashed"):
        figure.add_trace(go.Bar(x=hours, y=[row[key] for row in rows], name=OUTCOME_WORDS[key], marker_color=OUTCOME_COLOR[key], hovertemplate="%{x|%a %H:%M}: %{y} " + OUTCOME_WORDS[key].lower() + "<extra></extra>"))
    figure.update_layout(barmode="stack", bargap=0.15, height=190, margin=dict(l=28, r=0, t=6, b=24), showlegend=False, hoverlabel=dict(font_family=SANS, bgcolor="#131519", bordercolor=LINE),
                         xaxis=dict(gridcolor="#1A1C21", tickformat="%a %H:%M", showline=False), yaxis=dict(gridcolor="#1A1C21", zeroline=False, rangemode="tozero"), **NEUTRAL_FIGURE)
    return figure


def health_rows(data: dict[str, Any]) -> list[Any]:
    return [html.Div([html.Span(ICON.get(item["tone"], "!"), className=f"fo-icon {item['tone']}"), html.Span(item["label"], className="fo-grow"), html.Span(item["value"], className="fo-muted fo-right")], className="fo-health-row") for item in data["health"]] \
        or [html.Div("Health checks are unavailable.", className="fo-empty")]


def log_rows(data: dict[str, Any]) -> list[Any]:
    return [html.Div([html.Span(item["t"], className="fo-mono fo-muted fo-time"), html.Span(className=f"fo-dot small {item['tone']}"), html.Span(item["text"], className="fo-body")], className="fo-log-row") for item in data["log"]] \
        or [html.Div("Nothing has happened yet.", className="fo-empty")]


def render(data: dict[str, Any]) -> dict[str, Any]:
    """Every refreshable piece, keyed by component id, in OUTPUTS order (the layout and the 10 s callback both use it)."""
    pill = data["pill"]
    old = data["old_runs"]
    show_needs = bool(data["alerts"] or old)
    return {
        "fo-pill": [html.Span(className="fo-pill-dot"), pill["label"]],
        "fo-date": data["now_label"],
        "fo-headline": data["headline"] if data["available"] else f"{data['headline']}. {data.get('message') or ''}".strip(),
        "fo-tiles": tiles(data), "fo-running": running_cards(data), "fo-alerts": alert_cards(data),
        "fo-old-title": old["title"] if old else "", "fo-old-items": old_run_items(data), "fo-old-wrap": {"display": "block" if old else "none"},
        "fo-needs": {"display": "flex" if show_needs else "none"},
        "fo-queue-head": queue_head(data), "fo-queue": queue_rows(data),
        "fo-timeline": timeline_figure(data["timeline"], data["now_et"]), "fo-hourly": hourly_figure(data["hourly"]) if data["hourly"] else go.Figure().update_layout(height=190, **NEUTRAL_FIGURE),
        "fo-health": health_rows(data), "fo-health-checked": f"Checked {data['checked']}", "fo-log": log_rows(data),
    }


def _pill_class(data: dict[str, Any]) -> str:
    return f"fo-pill {data['pill']['tone']}"


def _card(title: str, hint: str | None, *children: Any, **props: Any) -> html.Div:
    head = html.Div([html.Span(title, className="fo-h"), html.Span(hint, className="fo-muted")], className="fo-between") if hint is not None else None
    return html.Div([head, *children] if head else list(children), className="fo-card", **props)


def layout() -> html.Div:
    data = load_factory_overview()
    part = render(data)
    legend = html.Div([html.Span([html.Span(className="fo-swatch", style={"background": OUTCOME_COLOR[key]}), OUTCOME_WORDS[key]]) for key in ("failed", "close", "passed", "crashed", "running")], className="fo-legend")
    body = html.Div([
        html.Section([html.Div([html.Div(part["fo-date"], id="fo-date", className="fo-muted"), html.H1(part["fo-headline"], id="fo-headline", className="fo-title")]),
                      html.Div([html.Span(part["fo-pill"], id="fo-pill", className=_pill_class(data)), html.Span("Refreshes every 10 s", className="fo-muted")], className="fo-top-right")], className="fo-top"),
        html.Section(part["fo-tiles"], id="fo-tiles", className="fo-tiles"),
        html.Section([
            _card("Running now", "One test at a time", html.Div(part["fo-running"], id="fo-running", className="fo-col")),
            html.Div([
                html.Div([html.Div([html.Span("Needs a look", className="fo-h"), html.Span("Newest first", className="fo-muted")], className="fo-between"),
                          html.Div(part["fo-alerts"], id="fo-alerts", className="fo-col"),
                          html.Div([html.Div([html.Span(className="fo-dot amber"), html.Span(part["fo-old-title"], id="fo-old-title", className="fo-name fo-grow"),
                                              dmc.Button("Show them", id="fo-old-toggle", variant="subtle", color="gray", size="compact-xs")], className="fo-old-head"),
                                    dmc.Collapse(html.Div(part["fo-old-items"], id="fo-old-items"), id="fo-old-collapse", opened=False)],
                                   id="fo-old-wrap", className="fo-alert amber fo-old", style=part["fo-old-wrap"])],
                         id="fo-needs", className="fo-card", style=part["fo-needs"]),
                _card("", None, html.Div(part["fo-queue-head"], id="fo-queue-head", className="fo-between"), html.Div(part["fo-queue"], id="fo-queue")),
            ], className="fo-col"),
        ], className="fo-two"),
        html.Section(html.Div([
            html.Div([html.Span("Last 12 hours", className="fo-h"), legend], className="fo-between fo-wrap"),
            html.Div(dcc.Graph(id="fo-timeline", figure=part["fo-timeline"], config=GRAPH_CONFIG, style={"height": 76}), className="fo-scroll"),
            html.Span("Each block is one test run, coloured by how it ended. Hover for the idea, how long it took and the outcome; click to open its report. A gap means the factory sat idle.", className="fo-muted")],
            className="fo-card")),
        html.Section([
            _card("Tests finished per hour", "Last 48 hours", dcc.Graph(id="fo-hourly", figure=part["fo-hourly"], config=GRAPH_CONFIG, style={"height": 190}),
                  html.Span("Flat stretches are nights and weekends with nothing queued, not faults.", className="fo-muted")),
            _card("Health checks", None, html.Div([html.Span("Health checks", className="fo-h"), html.Span(part["fo-health-checked"], id="fo-health-checked", className="fo-muted")], className="fo-between"),
                  html.Div(part["fo-health"], id="fo-health")),
            _card("What happened", "Plain-language log", html.Div(part["fo-log"], id="fo-log")),
        ], className="fo-three"),
    ], className="fo-page")
    return html.Div([dcc.Interval(id="fo-tick", interval=REFRESH_MS), dcc.Location(id="fo-nav", refresh=True),
                     dmc.MantineProvider(body, theme=REPORT_THEME, forceColorScheme="dark")], className="fo-root", style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_callbacks(application: Any) -> None:
    """Standard Dash callbacks only: the 10 s refresh, the old-runs toggle, and click-to-open-report."""
    properties = {"fo-date": "children", "fo-headline": "children", "fo-pill": "children", "fo-tiles": "children", "fo-running": "children", "fo-alerts": "children", "fo-old-title": "children",
                  "fo-old-items": "children", "fo-old-wrap": "style", "fo-needs": "style", "fo-queue-head": "children", "fo-queue": "children", "fo-timeline": "figure", "fo-hourly": "figure",
                  "fo-health": "children", "fo-health-checked": "children", "fo-log": "children"}

    @application.callback([Output(key, properties[key]) for key in OUTPUTS] + [Output("fo-pill", "className")], Input("fo-tick", "n_intervals"), prevent_initial_call=True)
    def refresh(_ticks: int | None):
        data = load_factory_overview()
        part = render(data)
        return [part[key] for key in OUTPUTS] + [_pill_class(data)]

    @application.callback(Output("fo-old-collapse", "opened"), Output("fo-old-toggle", "children"), Input("fo-old-toggle", "n_clicks"), State("fo-old-collapse", "opened"), prevent_initial_call=True)
    def toggle_old(_clicks: int | None, opened: bool):
        return (not opened), ("Show them" if opened else "Hide them")

    @application.callback(Output("fo-nav", "pathname"), Output("fo-nav", "search"), Input("fo-timeline", "clickData"), prevent_initial_call=True)
    def open_report(click: dict[str, Any] | None):
        point = ((click or {}).get("points") or [{}])[0]
        custom = point.get("customdata") or []
        if len(custom) < 4 or not custom[3]:
            return no_update, no_update
        return "/report", f"?candidate_id={quote(str(custom[3]), safe='')}"


__all__ = ["factory_layout", "layout", "register_callbacks", "register_factory_callbacks"]
