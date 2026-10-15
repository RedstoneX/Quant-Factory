"""Production read-only Quant Factory Dashboard."""

from __future__ import annotations

from datetime import datetime

import os
from pathlib import Path
import sys
from typing import Any
from urllib.parse import quote

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
from dash_iconify import DashIconify
from flask import jsonify, request
import plotly.graph_objects as go

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.overview_projection import load_dashboard_snapshot, load_drilldown_page
from dashboard.results_projection import oos_report_metrics
from dashboard.ui.candidates import candidates_layout, register_candidate_callbacks
from dashboard.ui.compare import compare_layout, register_compare_callbacks
from dashboard.ui.factory import factory_layout, register_factory_callbacks
from dashboard.ui.layout import app_shell, copy_id, page_content, page_header, stat_card
from dashboard.ui.paper import paper_layout
from dashboard.ui.results import register_results_callbacks, results_layout
from dashboard.ui.submit import register_submit_callbacks, submit_layout
from dashboard.plain_labels import FAILED_TESTING
from dashboard.score_projection import load_waiting_for_you, waiting_banner_text
from dashboard.time_display import eastern_time_label
from dashboard.ui.theme import ACCENT, COLUMN_DEFAULTS, FONT_URL, UP, grid_options, hide_when_narrow


def _application_revision() -> str:
    configured = os.environ.get("QF_REVISION", "").strip()
    if configured:
        return configured
    root = Path(__file__).resolve().parents[2]
    built = root / ".qf-build-revision"
    if built.is_file():
        return built.read_text(encoding="utf-8").strip()
    head = root / ".git" / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            return (root / ".git" / value[5:]).read_text(encoding="utf-8").strip()
        return value
    except OSError:
        return "revision-unavailable"


def kpi(title: str, value_id: str, detail_id: str, button_id: str, color: str) -> dmc.UnstyledButton:
    return dmc.UnstyledButton(stat_card(title, "0", "—", color=color, value_id=value_id, note_id=detail_id), id=button_id, className="kpi-button", **{"aria-label": f"Show {title.lower()}"})


def metric(label: str, value: str) -> dmc.Paper:
    return dmc.Paper([html.Span(label), html.Strong(value)], className="metric", radius="sm", withBorder=True)


def _format_number(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    number = float(value)
    return f"{number:.1f}%" if percent else f"{number:.2f}"


def _style_figure(figure: go.Figure) -> go.Figure:
    figure.update_layout(margin={"l": 48, "r": 16, "t": 18, "b": 42}, hovermode="closest", showlegend=False, uirevision="dashboard-ideas")
    return figure


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font={"size": 12})
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return _style_figure(figure)


def _candidate_figure(rows: list[dict[str, Any]]) -> go.Figure:
    if not rows:
        return _empty_figure("No ideas with test results match these filters yet.")
    colors = {"survivor": UP, "advancing": ACCENT, "closed": "#6e7681"}
    names = {"survivor": "Passed", "advancing": "Testing", "closed": "Stopped"}
    figure = go.Figure()
    for state in ("survivor", "advancing", "closed"):
        cohort = [row for row in rows if row["state"] == state]
        if not cohort:
            continue
        figure.add_trace(go.Scatter(
            x=[row["max_drawdown"] for row in cohort], y=[row["sharpe"] for row in cohort],
            mode="markers", name=names[state], text=[row["title"] for row in cohort],
            customdata=[[row["candidate_id"], row["run_id"]] for row in cohort],
            marker={"size": 9 if state != "survivor" else 11, "color": colors[state], "opacity": .92},
            hovertemplate="%{text}<br>Sharpe %{y:.2f}<br>Max drawdown %{x:.1f}%<extra></extra>",
        ))
    figure.update_xaxes(title="Max drawdown", rangemode="tozero", ticksuffix="%")
    figure.update_yaxes(title="Out-of-sample Sharpe", rangemode="tozero")
    return _style_figure(figure)


def _finding_content(item: dict[str, Any] | None, snapshot: dict[str, Any]) -> list[Any]:
    if item is None:
        return [
            dmc.Group([dmc.Badge("Nothing selected", color="gray"), dmc.Text("", className="rank")], justify="space-between", className="status-row"),
            dmc.Title("No passed idea yet", order=2),
            dmc.Text("Pick a point or a row to see an idea", className="finding-id"),
            dmc.Text(snapshot.get("message") if not snapshot.get("available") else "No passed idea matches these filters.", className="signal"),
            html.Div([metric("Out-of-sample Sharpe", "—"), metric("Max drawdown", "—"), metric("Kept out-of-sample", "—")], className="metrics"),
            html.Div(dmc.Text("Open Results to see its chart", className="mini-empty"), className="mini-equity"),
            dmc.Group([dmc.Button("Open Results", id="open-results", className="primary", disabled=True), dmc.Button("Open in Ideas", id="open-candidate", className="ghost", variant="default", disabled=True)], gap=7, className="finding-actions"),
        ]
    stage = str(item.get("stage") or "not_run").replace("_", " ").title()
    status = "Passed" if item.get("state") == "survivor" else str(item.get("run_status") or "Not run").replace("_", " ").title()
    if item.get("record_type") == "factory_study":
        outcome = str(item.get("outcome") or status).replace("_", " ").title()
        return [
            dmc.Group([dmc.Badge("Latest run", className="badge"), copy_id(item.get("run_id"))], justify="space-between", className="status-row"),
            dmc.Title(item.get("title") or "Test run", order=2),
            dmc.Text(f"{item.get('symbol')} · test run", className="finding-id"),
            dmc.Text(f"{stage} · {status} · {outcome}. A past test run, not a passed idea.", className="signal"),
            html.Div([metric("First-check Sharpe", _format_number(item.get("sharpe"))), metric("Max drawdown", _format_number(item.get("max_drawdown"), percent=True)), metric("Kept out-of-sample", "—")], className="metrics"),
            html.Div(dmc.Text("Open Results to see its chart", className="mini-empty"), className="mini-equity"),
            dmc.Group([dmc.Button("Open Results", id="open-results", className="primary", disabled=not item.get("run_id")), dmc.Button("Open in Ideas", id="open-candidate", className="ghost", variant="default", disabled=True)], gap=7, className="finding-actions"),
        ]
    screened_out = str(item.get("outcome") or "").lower() == "screened_out"
    status = FAILED_TESTING if screened_out else status
    return [
        dmc.Group([dmc.Badge(status, leftSection=DashIconify(icon="tabler:check", width=12) if item.get("state") == "survivor" else None, className=f"badge{' rejected' if screened_out else ''}"), copy_id(item.get("run_id"))], justify="space-between", className="status-row"),
        dmc.Title(item.get("title") or "Untitled idea", order=2),
        dmc.Text(str(item.get("symbol") or ""), className="finding-id"),
        dmc.Text(
            "Every setting failed the first check, so this idea stopped there."
            if screened_out else f"{stage} · {status}. Paper trading is off.",
            className=f"signal{' rejected' if screened_out else ''}",
        ),
        html.Div([metric("First-check Sharpe" if screened_out else "Out-of-sample Sharpe", _format_number(item.get("sharpe"))), metric("Max drawdown", _format_number(item.get("max_drawdown"), percent=True)), metric("Kept out-of-sample", _format_number(item.get("retained"), percent=True))], className="metrics"),
        html.Div(dmc.Text("Open Results to see its chart", className="mini-empty"), className="mini-equity"),
        dmc.Group([dmc.Button("Open Results", id="open-results", className="primary", disabled=not item.get("run_id")), dmc.Button("Open in Ideas", id="open-candidate", className="ghost", variant="default", disabled=not item.get("candidate_id"))], gap=7, className="finding-actions"),
    ]


STAGE_LABELS = {"submitted": "Received", "costs": "After costs", "oos": "Unseen data", "walk_forward": "Over time", "robustness": "Stress test", "survivors": "Passed"}
STAGE_TONES = {"submitted": "submitted", "costs": "costs", "oos": "oos", "walk_forward": "wf", "robustness": "robust", "survivors": "gold"}


def _factory_content(snapshot: dict[str, Any]) -> list[Any]:
    stages = snapshot.get("stages", {})
    operation = snapshot.get("operation", {})
    active = int(operation.get("active") or 0)
    terminal = int(operation.get("terminal") or 0)
    failed = int(snapshot.get("counts", {}).get("failed") or 0)
    median = operation.get("median_minutes")
    if active:
        detail = f"Slowest step: {operation.get('bottleneck', 'not recorded')}" + (f" · typical run {median:.0f} min" if median is not None else "")
    else:
        detail = f"{failed} failed · {terminal} finished"
    return [
        dmc.Group([dmc.Title("Where ideas are", order=2), dmc.Text(f"{snapshot.get('population_count', 0):,} ideas")], justify="space-between", className="flow-top"),
        html.Div([dmc.Button(f"{int(stages.get(key, 0)):,}", id=f"stage-{key}", className=f"stage {tone}", variant="subtle", **{"aria-label": f"Show ideas at {STAGE_LABELS[key]}"}) for key, tone in STAGE_TONES.items()], className="flow-track"),
        html.Div([html.Span(label) for label in STAGE_LABELS.values()], className="flow-labels"),
        dmc.Group([
            html.Div([html.Strong(f"{active} tests running"), html.Span(detail)], className="operation-copy"),
            dmc.Group([html.Span(className=f"health-dot{' muted' if active == 0 else ''}"), dmc.Text("Idle" if active == 0 else "Active")], gap=6, className="operation-pulse"),
        ], gap=10, justify="space-between", className="operation"),
    ]


SURVIVOR_COLUMNS = [
    {"field": "title", "headerName": "Idea", "flex": 2.2, "minWidth": 140, "filter": True, "tooltipField": "candidate_id"},
    {"field": "symbol", "headerName": "Market", "flex": .65, "minWidth": 80, "filter": True},
    {"field": "sharpe", "headerName": "Out-of-sample Sharpe", "type": "numericColumn", "flex": 1, "minWidth": 100, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Max drawdown", "type": "numericColumn", "flex": .8, "minWidth": 110, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "retained", "headerName": "Kept out-of-sample", "type": "numericColumn", "flex": .9, "minWidth": 140, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "paper", "headerName": "Paper", "flex": .65, "minWidth": 80},
]

DRILLDOWN_COLUMNS = [
    {"field": "title", "headerName": "Idea", "minWidth": 160, "flex": 1.6, "filter": True, "tooltipField": "candidate_id"},
    {"field": "symbol", "headerName": "Market", "minWidth": 75, "flex": .6, "filter": True},
    {"field": "stage", "headerName": "Stage", "minWidth": 95, "flex": .8, "filter": True},
    {"field": "status", "headerName": "Run", "minWidth": 80, "flex": .7, "filter": True, "tooltipField": "run_id"},
]


def dashboard_layout() -> html.Div:
    header = page_header(
        "Dashboard", "What the factory is doing right now",
        dmc.Select(id="time-window", data=[{"value": "90d", "label": "Last 90 days"}, {"value": "30d", "label": "Last 30 days"}, {"value": "ytd", "label": "Year to date"}], value="90d", allowDeselect=False, size="xs", w=130, **{"aria-label": "Time window"}),
        dmc.Select(id="market-filter", data=[{"value": "all", "label": "All markets"}, {"value": "futures", "label": "Futures"}, {"value": "equities", "label": "Equities"}, {"value": "crypto", "label": "Crypto"}], value="all", allowDeselect=False, size="xs", w=120, **{"aria-label": "Market"}),
        dmc.UnstyledButton(dmc.Group([html.Span(className="health-dot", id="health-indicator"), dmc.Text("Loading…", id="health-copy", size="xs", c="dimmed")], gap=7), id="refresh-state", className="health", **{"aria-label": "Refresh"}),
    )
    universe = dmc.Paper([
        dmc.Group([
            html.Div([dmc.Title("Ideas tested", order=2), dmc.Text("", id="universe-subtitle")], className="panel-title"),
            html.Div(className="head-spacer"), dmc.Button("Open ranked ideas", id="open-ranked", leftSection=DashIconify(icon="tabler:table", width=14), variant="default"),
        ], gap=10, className="panel-head"),
        html.Div(
            dcc.Graph(id="candidate-chart", figure=_empty_figure("Loading…"), config={"displayModeBar": False, "responsive": True}, className="chart-graph", clear_on_unhover=True),
            role="region", **{"aria-label": "Ideas by risk and return; the ranked list offers keyboard selection"},
        ),
        dmc.Group([html.Span([html.I(className="legend-dot green"), "passed"]), html.Span([html.I(className="legend-dot blue"), "testing"]), html.Span([html.I(className="legend-dot closed"), "stopped"]), html.Span("", id="universe-note", className="legend-note")], gap=14, className="chart-legend"),
    ], id="universe-panel", className="panel universe")

    finding = dmc.Paper(_finding_content(None, {"available": False, "message": "Loading…"}), id="finding-panel", className="panel finding")
    factory = dmc.Paper(_factory_content({"stages": {}, "operation": {}, "population_count": 0}), id="factory-panel", className="panel flow")
    survivors = dmc.Paper([
        dmc.Group([dmc.Title("Best passed ideas", order=2), dmc.Text("", id="survivor-note"), html.Div(className="head-spacer"), dmc.Button("Columns", id="toggle-columns", leftSection=DashIconify(icon="tabler:columns", width=14), variant="default")], gap=8, className="grid-head"),
        dag.AgGrid(id="survivor-grid", columnDefs=SURVIVOR_COLUMNS, rowData=[], defaultColDef={**COLUMN_DEFAULTS, "filter": True}, eventListeners=hide_when_narrow("symbol", "max_drawdown", "retained", "paper"), dashGridOptions=grid_options("No passed ideas yet.", rowSelection={"mode": "singleRow", "enableClickSelection": True, "checkboxes": False}, animateRows=False, suppressCellFocus=False), getRowId="params.data.candidate_id", className="qf-grid", columnSize="responsiveSizeToFit"),
    ], id="survivors-panel", className="panel survivors")

    body = html.Div([
        dmc.SimpleGrid([
            kpi("Passed", "survivor-value", "survivor-detail", "summary-survivors", "teal.5"),
            kpi("Needs you", "needs-value", "needs-detail", "summary-needs", "yellow.6"),
            kpi("Running now", "running-value", "running-detail", "summary-running", "blue.4"),
            kpi("Testing", "advancing-value", "advancing-detail", "summary-advancing", "blue.4"),
        ], cols={"base": 2, "md": 4}, spacing="sm", mb="md"),
        html.Section([universe, finding], className="workspace"), html.Section([factory, survivors], className="lower"),
    ], className="body")

    stores = [dcc.Location(id="location", refresh=False), dcc.Store(id="snapshot-store"), dcc.Store(id="selected-candidate"), dcc.Store(id="drawer-query")]
    drawer = dmc.Drawer(
        [
            dmc.Title("—", id="drawer-value", order=3, className="drawer-value"),
            dmc.Text("Click a number to see the ideas behind it.", id="drawer-copy", className="drawer-copy"),
            dag.AgGrid(
                id="drawer-grid", columnDefs=DRILLDOWN_COLUMNS, rowModelType="infinite",
                defaultColDef={**COLUMN_DEFAULTS, "filter": True}, eventListeners=hide_when_narrow("stage"),
                dashGridOptions=grid_options("Nothing here yet.", rowSelection={"mode": "singleRow", "enableClickSelection": True, "checkboxes": False}, cacheBlockSize=20, maxBlocksInCache=2, animateRows=False),
                getRowId="params.data.run_id || params.data.candidate_id", className="drawer-grid", columnSize="responsiveSizeToFit",
            ),
        ],
        id="context-drawer", title="Details", opened=False, position="right", size=330,
        overlayProps={"backgroundOpacity": .55, "blur": 1}, className="context-drawer",
    )
    waiting = waiting_banner_text(load_waiting_for_you())
    banner = dmc.Alert(waiting, id="waiting-banner", color="yellow", icon=DashIconify(icon="tabler:hourglass", width=18), m="lg", mb=0) if waiting else None
    return html.Div([*stores, header, *([banner] if banner else []), body, drawer], className="dashboard-app")


def _selected_item(snapshot: dict[str, Any], selection: dict[str, Any] | None) -> dict[str, Any] | None:
    if not selection:
        return snapshot.get("latest_finding")
    candidate_id = selection.get("candidate_id")
    run_id = selection.get("run_id")
    rows = [*snapshot.get("survivors", []), *snapshot.get("chart", [])]
    if snapshot.get("latest_finding"):
        rows.append(snapshot["latest_finding"])
    return next((row for row in rows if (candidate_id and row.get("candidate_id") == candidate_id) or (run_id and row.get("run_id") == run_id)), selection)


def register_callbacks(application: Dash) -> None:
    @application.callback(Output("snapshot-store", "data"), Input("time-window", "value"), Input("market-filter", "value"), Input("refresh-state", "n_clicks"))
    def refresh_snapshot(window: str, market: str, _refresh: int | None) -> dict[str, Any]:
        return load_dashboard_snapshot(window=window or "90d", market=market or "all", unseen_report=oos_report_metrics)

    @application.callback(Output("selected-candidate", "data"), Input("candidate-chart", "clickData"), Input("survivor-grid", "selectedRows"), Input("snapshot-store", "data"), State("selected-candidate", "data"))
    def sync_selection(click_data: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, snapshot: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, Any] | None:
        snapshot = snapshot or {}
        if ctx.triggered_id == "candidate-chart" and click_data:
            candidate_id = str(click_data["points"][0]["customdata"][0])
            return next((row for row in snapshot.get("chart", []) if row.get("candidate_id") == candidate_id), None)
        if ctx.triggered_id == "survivor-grid" and selected_rows:
            return selected_rows[0]
        rows = [*snapshot.get("survivors", []), *snapshot.get("chart", [])]
        if snapshot.get("latest_finding"):
            rows.append(snapshot["latest_finding"])
        identities = {(row.get("candidate_id"), row.get("run_id")) for row in rows}
        if current and (current.get("candidate_id"), current.get("run_id")) in identities:
            return current
        return rows[0] if rows else None

    @application.callback(
        Output("running-value", "children"), Output("running-detail", "children"), Output("survivor-value", "children"), Output("survivor-detail", "children"),
        Output("advancing-value", "children"), Output("advancing-detail", "children"), Output("needs-value", "children"), Output("needs-detail", "children"),
        Output("candidate-chart", "figure"), Output("survivor-grid", "rowData"), Output("finding-panel", "children"), Output("factory-panel", "children"),
        Output("health-copy", "children"), Output("health-indicator", "className"), Output("universe-subtitle", "children"), Output("universe-note", "children"), Output("survivor-note", "children"),
        Output("summary-needs", "style"), Output("survivors-panel", "style"), Output("universe-panel", "className"),
        Input("snapshot-store", "data"), Input("selected-candidate", "data"),
    )
    def render_snapshot(snapshot: dict[str, Any] | None, selection: dict[str, Any] | None):
        snapshot = snapshot or {"counts": {}, "chart": [], "survivors": [], "message": "Loading state.", "available": False, "stages": {}, "operation": {}, "population_count": 0}
        counts = snapshot.get("counts", {})
        item = _selected_item(snapshot, selection)
        try:
            observed_label = eastern_time_label(str(snapshot.get("observed_at") or ""))
        except ValueError:
            observed_label = "time unavailable"
        health = f"State refreshed {observed_label}" if snapshot.get("available") else "Can't load right now · click to retry"
        health_class = "health-dot" if snapshot.get("available") else "health-dot unavailable"
        chart_count = len(snapshot.get("chart", [])); population = int(snapshot.get("population_count") or 0); survivor_count = len(snapshot.get("survivors", []))
        return (
            f"{int(counts.get('running', 0)):,}", f"{int(counts.get('queued', 0)):,} queued", f"{int(counts.get('survivors', 0)):,}", "need your review",
            f"{int(counts.get('advancing', 0)):,}", "queued or running", "—" if counts.get("needs") is None else f"{int(counts['needs']):,}", "" if counts.get("needs") is None else "waiting on you",
            _candidate_figure(snapshot.get("chart", [])), snapshot.get("survivors", []), _finding_content(item, snapshot), _factory_content(snapshot), health, health_class,
            f"{population:,} ideas · {chart_count:,} with out-of-sample results shown",
            f"Up to {snapshot.get('chart_limit', 200):,} points · click one to see that idea",
            f"{survivor_count:,} of {int(counts.get('survivors', 0)):,}, best out-of-sample Sharpe first",
            {"display": "none"} if counts.get("needs") is None else {}, {} if survivor_count else {"display": "none"},
            "panel universe" if chart_count else "panel universe collapsed",
        )

    @application.callback(Output("survivor-grid", "columnDefs"), Input("toggle-columns", "n_clicks"), prevent_initial_call=True)
    def toggle_columns(n_clicks: int | None) -> list[dict[str, Any]]:
        hide_optional = bool((n_clicks or 0) % 2)
        return [{**column, **({"hide": hide_optional} if column["field"] in {"retained", "paper"} else {})} for column in SURVIVOR_COLUMNS]

    drawer_inputs = [
        Input("summary-running", "n_clicks"), Input("summary-survivors", "n_clicks"), Input("summary-advancing", "n_clicks"), Input("summary-needs", "n_clicks"),
        Input("open-ranked", "n_clicks"),
        Input("stage-submitted", "n_clicks"), Input("stage-costs", "n_clicks"), Input("stage-oos", "n_clicks"), Input("stage-walk_forward", "n_clicks"), Input("stage-robustness", "n_clicks"), Input("stage-survivors", "n_clicks"),
    ]

    @application.callback(
        Output("context-drawer", "opened"), Output("context-drawer", "title"),
        Output("drawer-value", "children"), Output("drawer-copy", "children"), Output("drawer-query", "data"),
        *drawer_inputs, State("snapshot-store", "data"), State("time-window", "value"), State("market-filter", "value"),
        prevent_initial_call=True,
    )
    def open_context_drawer(*args: Any):
        snapshot = args[-3] or {}; window = args[-2] or "90d"; market = args[-1] or "all"
        trigger = str(ctx.triggered_id or ""); counts = snapshot.get("counts", {}); stages = snapshot.get("stages", {})
        if not ctx.triggered or ctx.triggered[0].get("value") is None:
            return no_update, no_update, no_update, no_update, no_update
        if trigger.startswith("summary-"):
            key = trigger.removeprefix("summary-")
            lookup = {
                "running": ("running", "Running now", counts.get("running", 0), "Tests running right now."),
                "survivors": ("survivors", "Passed ideas", counts.get("survivors", 0), "Ideas that passed every test."),
                "advancing": ("advancing", "Testing", counts.get("advancing", 0), "Tests waiting or running."),
                "needs": ("needs", "Needs you", None, "Nothing is tracked here yet."),
            }
            kind, title, value, copy = lookup[key]
            label = "Unavailable" if value is None else f"{int(value):,} records"
            return True, title, label, copy, {"kind": kind, "window": window, "market": market, "nonce": datetime.now().isoformat()}
        if trigger.startswith("stage-"):
            key = trigger.removeprefix("stage-"); title = STAGE_LABELS.get(key, key)
            return True, title, f"{int(stages.get(key, 0)):,} ideas", "The ideas behind this number.", {"kind": key, "window": window, "market": market, "nonce": datetime.now().isoformat()}
        if trigger == "open-ranked":
            return True, "Passed ideas, best first", f"{int(counts.get('survivors', 0)):,} passed ideas", "Open Ideas for the full list.", {"kind": "ranked", "window": window, "market": market, "nonce": datetime.now().isoformat()}
        return False, "Details", "—", "Nothing to show.", None

    @application.callback(
        Output("drawer-grid", "getRowsResponse"),
        Input("drawer-grid", "getRowsRequest"), Input("drawer-query", "data"),
    )
    def load_drawer_rows(request: dict[str, Any] | None, query: dict[str, Any] | None) -> dict[str, Any]:
        if not request or not query:
            return {"rowData": [], "rowCount": 0}
        return load_drilldown_page(
            kind=str(query.get("kind") or ""), window=str(query.get("window") or "90d"), market=str(query.get("market") or "all"),
            start=int(request.get("startRow") or 0), end=int(request.get("endRow") or 20),
            sort_model=request.get("sortModel"), filter_model=request.get("filterModel"),
        )


def create_app() -> Dash:
    application = Dash(__name__, title="Quant Factory", suppress_callback_exceptions=True, external_stylesheets=[FONT_URL])
    revision = _application_revision()
    server = application.server

    @server.get("/__qf_revision__")
    def revision_document():
        response = jsonify({"revision": revision, "reload_required": False})
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-QF-Revision"] = revision
        return response

    @server.before_request
    def reject_stale_callback_client():
        if request.path != "/_dash-update-component":
            return None
        client_revision = request.cookies.get("qf_revision")
        if client_revision == revision:
            return None
        response = jsonify({
            "error": "revision_mismatch",
            "message": "Quant Factory was updated. Reload this page before continuing.",
            "revision": revision,
        })
        response.status_code = 409
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-QF-Revision-Mismatch"] = revision
        return response

    @server.after_request
    def publish_revision(response):
        response.headers["X-QF-Revision"] = revision
        if request.method == "GET" and response.content_type and response.content_type.startswith("text/html"):
            response.set_cookie("qf_revision", revision, secure=True, httponly=False, samesite="Strict")
        return response

    application.layout = app_shell(dcc.Location(id="router-location", refresh=False), html.Div(id="route-page"))

    @application.callback(Output("route-page", "children"), Input("router-location", "pathname"), Input("router-location", "search"))
    def route(pathname: str | None, search: str | None):
        if pathname == "/candidates": return page_content(candidates_layout(search))
        if pathname == "/results": return page_content(results_layout(search))
        if pathname == "/factory": return page_content(factory_layout())
        if pathname == "/submit": return page_content(submit_layout())
        if pathname == "/compare": return page_content(compare_layout(search))
        if pathname == "/paper-trading": return page_content(paper_layout())
        return page_content(dashboard_layout())

    nav_triggers = (
        "open-results", "open-candidate", "candidate-open-results", "candidate-submit", "factory-open-candidates", "factory-open-results",
        "compare-selected", "compare-back", "compare-clear",
        # Results still draws its own hidden rail until its slice rebuilds the page.
        "results-nav-dashboard", "results-nav-candidates", "results-back-candidates", "results-nav-factory", "results-nav-submit", "results-nav-paper",
    )

    @application.callback(
        Output("router-location", "pathname"), Output("router-location", "search"),
        *[Input(item, "n_clicks", allow_optional=True) for item in nav_triggers],
        State("results-record", "data", allow_optional=True), State("selected-candidate", "data", allow_optional=True), State("candidate-detail-record", "data", allow_optional=True), State("factory-selected", "data", allow_optional=True), State("candidate-compare-selection", "data", allow_optional=True), prevent_initial_call=True,
    )
    def navigate(*values: Any):
        trigger = ctx.triggered_id
        if not ctx.triggered or not ctx.triggered[0].get("value"):
            return no_update, no_update
        if trigger == "factory-open-candidates":
            selected = values[-2] or {}
            candidate_id = selected.get("candidate_id")
            return "/candidates", f"?candidate_id={quote(str(candidate_id), safe='')}" if candidate_id else ""
        if trigger == "results-back-candidates":
            candidate_id = (values[-5] or {}).get("candidate_id")
            return "/candidates", f"?candidate_id={quote(str(candidate_id), safe='')}" if candidate_id else ""
        if trigger == "open-candidate":
            candidate_id = (values[-4] or {}).get("candidate_id")
            return "/candidates", f"?candidate_id={quote(str(candidate_id), safe='')}" if candidate_id else ""
        if trigger in {"results-nav-candidates", "compare-back"}: return "/candidates", ""
        if trigger == "compare-clear": return "/candidates", "?clear_compare=1"
        if trigger in {"open-results", "candidate-open-results", "factory-open-results"}:
            selected = values[-4] if trigger == "open-results" else values[-3] if trigger == "candidate-open-results" else values[-2]
            candidate_id = (selected or {}).get("candidate_id")  # Results is one page per idea
            if candidate_id:
                return "/results", f"?candidate_id={quote(str(candidate_id), safe='')}"
            run_id = (selected or {}).get("results_run_id") or (selected or {}).get("run_id")
            return "/results", f"?run_id={quote(str(run_id), safe='')}" if run_id else ""
        if trigger == "compare-selected":
            run_ids = [str(row.get("run_id")) for row in (values[-1] or []) if row.get("run_id")]
            return "/compare", "?" + "&".join(f"run_id={quote(run_id, safe='')}" for run_id in run_ids)
        if trigger == "results-nav-factory": return "/factory", ""
        if trigger in {"candidate-submit", "results-nav-submit"}: return "/submit", ""
        if trigger == "results-nav-paper": return "/paper-trading", ""
        return "/", ""

    register_callbacks(application)
    register_candidate_callbacks(application)
    register_results_callbacks(application)
    register_factory_callbacks(application)
    register_submit_callbacks(application)
    register_compare_callbacks(application)
    return application


app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
