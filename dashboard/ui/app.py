"""Production read-only Quant Factory Dashboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update
import plotly.graph_objects as go

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.overview_projection import load_dashboard_snapshot, load_drilldown_page
from dashboard.ui.candidates import candidates_layout, register_candidate_callbacks
from dashboard.ui.results import register_results_callbacks, results_layout


GLYPHS = {
    "dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷",
    "chart": "⌁", "external": "↗", "activity": "⌁", "gem": "◇",
    "up": "⇈", "alert": "!", "table": "▦", "check": "✓",
    "settings": "☷", "loader": "◌",
}


def icon(name: str) -> html.Span:
    return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})


def rail_item(name: str, label: str, item_id: str, *, active: bool = False, disabled: bool = False) -> dmc.ActionIcon:
    return dmc.ActionIcon(
        icon(name), id=item_id, className=f"rail-item{' active' if active else ''}",
        variant="subtle", disabled=disabled, **{"aria-label": label},
    )


def kpi(title: str, value_id: str, detail_id: str, icon_name: str, tone: str, button_id: str) -> dmc.UnstyledButton:
    return dmc.UnstyledButton(
        dmc.Paper(
            [
                dmc.Group([dmc.Text(title), icon(icon_name)], justify="space-between", className="kpi-head"),
                dmc.Group([html.Strong("0", id=value_id, className=tone), html.Small("—", id=detail_id)], gap=8, align="baseline", className="kpi-main"),
            ],
            className=f"kpi glow-{tone or 'blue'}", radius="md", withBorder=True,
        ),
        id=button_id, className="kpi-button", **{"aria-label": f"Inspect {title.lower()}"},
    )


def metric(label: str, value: str) -> dmc.Paper:
    return dmc.Paper([html.Span(label), html.Strong(value)], className="metric", radius="sm", withBorder=True)


def _format_number(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    number = float(value)
    return f"{number:.1f}%" if percent else f"{number:.2f}"


def _style_figure(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 48, "r": 16, "t": 18, "b": 42},
        font={"family": "Inter, sans-serif", "size": 9, "color": "#8a97a8"},
        legend={"orientation": "h", "y": -0.2, "x": 0, "font": {"size": 9}},
        hovermode="closest", uirevision="dashboard-candidate-universe",
    )
    figure.update_xaxes(gridcolor="#202936", linecolor="#344050", zeroline=False, title_font={"size": 9})
    figure.update_yaxes(gridcolor="#202936", linecolor="#344050", zeroline=False, title_font={"size": 9})
    return figure


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font={"size": 11, "color": "#8a97a8"})
    figure.update_xaxes(title="Maximum drawdown", range=[0, 20])
    figure.update_yaxes(title="OOS Sharpe", range=[0, 2])
    return _style_figure(figure)


def _candidate_figure(rows: list[dict[str, Any]]) -> go.Figure:
    if not rows:
        return _empty_figure("No persisted Candidate metrics match these filters")
    colors = {"survivor": "#38d39f", "advancing": "#4aa8ff", "closed": "#46515f"}
    figure = go.Figure()
    for state in ("survivor", "advancing", "closed"):
        cohort = [row for row in rows if row["state"] == state]
        if not cohort:
            continue
        figure.add_trace(go.Scatter(
            x=[row["max_drawdown"] for row in cohort], y=[row["sharpe"] for row in cohort],
            mode="markers", name=state.title(), text=[row["title"] for row in cohort],
            customdata=[[row["candidate_id"], row["run_id"]] for row in cohort],
            marker={"size": 9 if state != "survivor" else 11, "color": colors[state], "line": {"width": 3, "color": colors[state]}, "opacity": .92},
            hovertemplate="%{text}<br>Sharpe %{y:.2f}<br>Max DD %{x:.1f}%<extra></extra>",
        ))
    figure.update_xaxes(title="Maximum drawdown", rangemode="tozero", ticksuffix="%")
    figure.update_yaxes(title="OOS Sharpe", rangemode="tozero")
    return _style_figure(figure)


def _finding_content(item: dict[str, Any] | None, snapshot: dict[str, Any]) -> list[Any]:
    if item is None:
        return [
            dmc.Group([dmc.Badge("No verified selection", className="badge"), dmc.Text("No selection", className="rank")], justify="space-between", className="status-row"),
            dmc.Title("No persisted survivor", order=2),
            dmc.Text("Exact Candidate and run identity unavailable", className="finding-id"),
            dmc.Text(snapshot.get("message") if not snapshot.get("available") else "No qualified survivor with persisted metrics matches the current filters.", className="signal"),
            html.Div([metric("OOS Sharpe", "—"), metric("Maximum DD", "—"), metric("OOS retained", "—")], className="metrics"),
            html.Div(dmc.Text("No persisted equity preview loaded", className="mini-empty"), className="mini-equity"),
            dmc.Group([dmc.Button("Results unavailable", id="open-results", className="primary", disabled=True), dmc.Button("Candidate unavailable", id="open-candidate", className="ghost", variant="default", disabled=True)], gap=7, className="finding-actions"),
        ]
    stage = str(item.get("stage") or "not_run").replace("_", " ").title()
    status = "Verified survivor" if item.get("state") == "survivor" else str(item.get("run_status") or "Not run").replace("_", " ").title()
    if item.get("record_type") == "factory_study":
        outcome = str(item.get("outcome") or status).replace("_", " ").title()
        return [
            dmc.Group([dmc.Badge("Latest factory finding", className="badge"), dmc.Text(f"Run {str(item.get('run_id') or 'none')[:10]}", className="rank")], justify="space-between", className="status-row"),
            dmc.Title(item.get("title") or "Persisted factory study", order=2),
            dmc.Text(f"Persisted study · {item.get('symbol')} · no Candidate packet", className="finding-id"),
            dmc.Text(f"{stage} · {status} · {outcome}. This retained study is factory history, not a qualified survivor.", className="signal"),
            html.Div([metric("Screening Sharpe", _format_number(item.get("sharpe"))), metric("Maximum DD", _format_number(item.get("max_drawdown"), percent=True)), metric("OOS retained", "—")], className="metrics"),
            html.Div(dmc.Text("Exact persisted run identity retained for Results when that surface is enabled", className="mini-empty"), className="mini-equity"),
            dmc.Group([dmc.Button("Open persisted Results", id="open-results", className="primary", disabled=not item.get("run_id")), dmc.Button("Candidate unavailable", id="open-candidate", className="ghost", variant="default", disabled=True)], gap=7, className="finding-actions"),
        ]
    version = str(item.get("candidate_version") or "")[:12] or "version unavailable"
    return [
        dmc.Group([dmc.Badge(status, leftSection=icon("check") if item.get("state") == "survivor" else None, className="badge"), dmc.Text(f"Run {str(item.get('run_id') or 'none')[:10]}", className="rank")], justify="space-between", className="status-row"),
        dmc.Title(item.get("title") or "Untitled Candidate", order=2),
        dmc.Text(f"{item.get('candidate_id')} · v{version} · {item.get('symbol')}", className="finding-id"),
        dmc.Text(f"{stage} · {status}. Paper lane remains inactive.", className="signal"),
        html.Div([metric("OOS Sharpe", _format_number(item.get("sharpe"))), metric("Maximum DD", _format_number(item.get("max_drawdown"), percent=True)), metric("OOS retained", _format_number(item.get("retained"), percent=True))], className="metrics"),
        html.Div(dmc.Text("Full persisted evidence is lazy-loaded in Results", className="mini-empty"), className="mini-equity"),
        dmc.Group([dmc.Button("Open full Results", id="open-results", className="primary", disabled=not item.get("run_id")), dmc.Button("View in Candidates", id="open-candidate", className="ghost", variant="default", disabled=True)], gap=7, className="finding-actions"),
    ]


def _factory_content(snapshot: dict[str, Any]) -> list[Any]:
    stages = snapshot.get("stages", {})
    stage_defs = [("submitted", "Submitted", "submitted"), ("costs", "Costs", "costs"), ("oos", "OOS", "oos"), ("walk_forward", "WF", "wf"), ("robustness", "Robust", "robust"), ("survivors", "Gold", "gold")]
    operation = snapshot.get("operation", {})
    active = int(operation.get("active") or 0)
    terminal = int(operation.get("terminal") or 0)
    failed = int(snapshot.get("counts", {}).get("failed") or 0)
    median = operation.get("median_minutes")
    secondary = f"{operation.get('bottleneck', 'Unavailable')} bottleneck"
    secondary += f" · recorded median {median:.0f}m" if median is not None else " · duration unavailable"
    return [
        dmc.Group([dmc.Title("Factory now", order=2), dmc.Text(f"{snapshot.get('population_count', 0):,} Candidates · current filter")], justify="space-between", className="flow-top"),
        html.Div([dmc.Button(f"{int(stages.get(key, 0)):,}", id=f"stage-{key}", className=f"stage {tone}", variant="subtle", **{"aria-label": f"Inspect {label} stage"}) for key, label, tone in stage_defs], className="flow-track"),
        html.Div([html.Span(label) for _, label, _ in stage_defs], className="flow-labels"),
        dmc.Group([
            dmc.ActionIcon(icon("loader"), className="operation-icon", variant="light", disabled=True),
            html.Div([
                html.Strong(f"{active} active Candidate runs"),
                html.Span(
                    secondary
                    if active
                    else f"{failed} failed · {terminal} terminal attempts · data state available · throughput unavailable"
                ),
            ], className="operation-copy"),
            dmc.Group([html.Span(className=f"health-dot{' muted' if active == 0 else ''}"), dmc.Text("Idle" if active == 0 else "Active")], gap=6, className="operation-pulse"),
        ], gap=10, className="operation"),
    ]


SURVIVOR_COLUMNS = [
    {"field": "title", "headerName": "Candidate", "flex": 2.2, "minWidth": 180, "pinned": "left", "filter": True},
    {"field": "symbol", "headerName": "Market", "flex": .65, "minWidth": 70, "filter": True},
    {"field": "sharpe", "headerName": "OOS Sharpe", "type": "numericColumn", "flex": .8, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Max DD", "type": "numericColumn", "flex": .8, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "retained", "headerName": "Retained", "type": "numericColumn", "flex": .8, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "paper", "headerName": "Paper", "flex": .65},
]

DRILLDOWN_COLUMNS = [
    {"field": "title", "headerName": "Candidate", "minWidth": 180, "flex": 1.6, "filter": True},
    {"field": "symbol", "headerName": "Market", "minWidth": 75, "flex": .6, "filter": True},
    {"field": "stage", "headerName": "Stage", "minWidth": 95, "flex": .8, "filter": True},
    {"field": "status", "headerName": "Run", "minWidth": 80, "flex": .7, "filter": True},
    {"field": "candidate_id", "headerName": "Candidate ID", "minWidth": 150, "filter": True},
    {"field": "run_id", "headerName": "Run ID", "minWidth": 150, "filter": True},
]


def dashboard_layout() -> dmc.MantineProvider:
    nav = dmc.Stack([
        dmc.Paper("Q", className="logo", radius="md"),
        rail_item("dashboard", "Dashboard and refresh", "nav-dashboard", active=True),
        rail_item("file", "Submit strategies unavailable", "nav-submit", disabled=True), rail_item("flow", "Factory unavailable", "nav-factory", disabled=True),
        rail_item("list", "Candidates", "nav-candidates"), rail_item("chart", "Results", "nav-results"),
        html.Div(className="rail-spacer"), rail_item("external", "Paper Trading destination not configured", "nav-paper", disabled=True),
        dmc.Avatar("TO", className="avatar", radius="xl"),
    ], gap=7, align="center", className="rail")

    header = dmc.Group([
        html.Div([dmc.Title("Dashboard", order=1), dmc.Text("Factory overview · read-only operating state", className="eyebrow")]),
        html.Div(className="top-spacer"),
        dmc.Select(id="time-window", data=[{"value": "90d", "label": "Last 90 days"}, {"value": "30d", "label": "Last 30 days"}, {"value": "ytd", "label": "Year to date"}], value="90d", allowDeselect=False, className="qf-select", **{"aria-label": "Time window"}),
        dmc.Select(id="market-filter", data=[{"value": "all", "label": "All markets"}, {"value": "futures", "label": "Futures"}, {"value": "equities", "label": "Equities"}, {"value": "crypto", "label": "Crypto"}], value="all", allowDeselect=False, className="qf-select market", **{"aria-label": "Market"}),
        dmc.UnstyledButton(dmc.Group([html.Span(className="health-dot", id="health-indicator"), dmc.Text("Loading…", id="health-copy")], gap=7), id="refresh-state", className="health", **{"aria-label": "Refresh Dashboard state"}),
    ], gap=16, className="topbar")

    universe = dmc.Paper([
        dmc.Group([
            html.Div([dmc.Title("Candidate universe", order=2), dmc.Text("Complete filtered population · bounded OOS metric cohort", id="universe-subtitle")], className="panel-title"),
            html.Div(className="head-spacer"), dmc.Button("Open ranked Candidates", id="open-ranked", leftSection=icon("table"), className="ghost", variant="default"),
        ], gap=10, className="panel-head"),
        html.Div(
            dcc.Graph(id="candidate-chart", figure=_empty_figure("Loading persisted Candidate metrics"), config={"displayModeBar": False, "responsive": True}, className="chart-graph", clear_on_unhover=True),
            role="region", **{"aria-label": "Candidate metric scatter plot; use the ranked grid for keyboard-accessible record selection"},
        ),
        dmc.Group([html.Span([html.I(className="legend-dot green"), "verified survivors"]), html.Span([html.I(className="legend-dot blue"), "active"]), html.Span([html.I(className="legend-dot closed"), "closed"]), html.Span("Bounded chart · click a point to inspect exact identity", id="universe-note", className="legend-note")], gap=14, className="chart-legend"),
    ], className="panel universe", radius="md", withBorder=True)

    finding = dmc.Paper(_finding_content(None, {"available": False, "message": "Loading read-only research state."}), id="finding-panel", className="panel finding", radius="md", withBorder=True)
    factory = dmc.Paper(_factory_content({"stages": {}, "operation": {}, "population_count": 0}), id="factory-panel", className="panel flow", radius="md", withBorder=True)
    survivors = dmc.Paper([
        dmc.Group([dmc.Title("Top survivors", order=2), dmc.Text("bounded cohort ranked by OOS Sharpe", id="survivor-note"), html.Div(className="head-spacer"), dmc.Button("Columns", id="toggle-columns", leftSection=icon("settings"), className="ghost", variant="default")], gap=8, className="grid-head"),
        dag.AgGrid(id="survivor-grid", columnDefs=SURVIVOR_COLUMNS, rowData=[], defaultColDef={"sortable": True, "resizable": True, "filter": True}, dashGridOptions={"rowSelection": {"mode": "singleRow", "enableClickSelection": True}, "animateRows": False, "suppressCellFocus": False}, getRowId="params.data.candidate_id", className="ag-theme-quartz-dark qf-grid"),
    ], className="panel survivors", radius="md", withBorder=True)

    body = html.Div([
        html.Section([
            kpi("Running now", "running-value", "running-detail", "activity", "", "summary-running"),
            kpi("Survivors", "survivor-value", "survivor-detail", "gem", "good", "summary-survivors"),
            kpi("Advancing", "advancing-value", "advancing-detail", "up", "violet", "summary-advancing"),
            kpi("Needs you", "needs-value", "needs-detail", "alert", "warn", "summary-needs"),
        ], className="pulse"),
        html.Section([universe, finding], className="workspace"), html.Section([factory, survivors], className="lower"),
    ], className="body")

    stores = [dcc.Location(id="location", refresh=False), dcc.Store(id="snapshot-store"), dcc.Store(id="selected-candidate"), dcc.Store(id="drawer-query")]
    drawer = dmc.Drawer(
        [
            dmc.Title("—", id="drawer-value", order=3, className="drawer-value"),
            dmc.Text("Select a Dashboard aggregate to inspect its exact records.", id="drawer-copy", className="drawer-copy"),
            dag.AgGrid(
                id="drawer-grid", columnDefs=DRILLDOWN_COLUMNS, rowModelType="infinite",
                defaultColDef={"sortable": True, "resizable": True, "filter": True},
                dashGridOptions={"rowSelection": {"mode": "singleRow", "enableClickSelection": True}, "cacheBlockSize": 20, "maxBlocksInCache": 2, "animateRows": False},
                getRowId="params.data.run_id || params.data.candidate_id", className="ag-theme-quartz-dark drawer-grid",
            ),
        ],
        id="context-drawer", title="Dashboard detail", opened=False, position="right", size=330,
        overlayProps={"backgroundOpacity": .55, "blur": 1}, className="context-drawer",
    )
    return dmc.MantineProvider(html.Div([*stores, html.Div([nav, html.Main([header, body], className="main")], className="app"), drawer]), forceColorScheme="dark", theme={"fontFamily": "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", "primaryColor": "blue"})


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
    @application.callback(Output("snapshot-store", "data"), Input("time-window", "value"), Input("market-filter", "value"), Input("refresh-state", "n_clicks"), Input("nav-dashboard", "n_clicks"))
    def refresh_snapshot(window: str, market: str, _refresh: int | None, _dashboard: int | None) -> dict[str, Any]:
        return load_dashboard_snapshot(window=window or "90d", market=market or "all")

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
        Input("snapshot-store", "data"), Input("selected-candidate", "data"),
    )
    def render_snapshot(snapshot: dict[str, Any] | None, selection: dict[str, Any] | None):
        snapshot = snapshot or {"counts": {}, "chart": [], "survivors": [], "message": "Loading state.", "available": False, "stages": {}, "operation": {}, "population_count": 0}
        counts = snapshot.get("counts", {})
        item = _selected_item(snapshot, selection)
        try:
            observed_label = datetime.fromisoformat(str(snapshot.get("observed_at") or "")).strftime("%H:%M:%S UTC")
        except ValueError:
            observed_label = "time unavailable"
        health = f"State refreshed {observed_label}" if snapshot.get("available") else "State unavailable · refresh"
        health_class = "health-dot" if snapshot.get("available") else "health-dot unavailable"
        chart_count = len(snapshot.get("chart", [])); population = int(snapshot.get("population_count") or 0); survivor_count = len(snapshot.get("survivors", []))
        return (
            f"{int(counts.get('running', 0)):,}", f"{int(counts.get('queued', 0)):,} queued", f"{int(counts.get('survivors', 0)):,}", "verified markers",
            f"{int(counts.get('advancing', 0)):,}", "queued or running", "—" if counts.get("needs") is None else f"{int(counts['needs']):,}", "attention projection unavailable" if counts.get("needs") is None else "genuine exceptions",
            _candidate_figure(snapshot.get("chart", [])), snapshot.get("survivors", []), _finding_content(item, snapshot), _factory_content(snapshot), health, health_class,
            f"{population:,} complete filtered Candidates · {chart_count:,} plotted exact OOS rows",
            f"Bounded to {snapshot.get('chart_limit', 200):,} points · click a point to inspect exact identity",
            f"showing {survivor_count:,} of {int(counts.get('survivors', 0)):,} verified survivors ranked by OOS Sharpe",
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
                "running": ("running", "Running now", counts.get("running", 0), "Exact Candidate runs currently recorded as running."),
                "survivors": ("survivors", "Verified survivors", counts.get("survivors", 0), "Exact Candidates linked to the authoritative survivor event marker."),
                "advancing": ("advancing", "Advancing", counts.get("advancing", 0), "Exact Candidate runs currently queued or running."),
                "needs": ("needs", "Needs you", None, "No accepted owner-attention projection exists, so this aggregate fails closed."),
            }
            kind, title, value, copy = lookup[key]
            label = "Unavailable" if value is None else f"{int(value):,} records"
            return True, title, label, copy, {"kind": kind, "window": window, "market": market, "nonce": datetime.now().isoformat()}
        if trigger.startswith("stage-"):
            key = trigger.removeprefix("stage-"); title = key.replace("_", " ").title()
            return True, f"{title} stage", f"{int(stages.get(key, 0)):,} Candidates", "Server-paged exact records behind this complete-population aggregate.", {"kind": key, "window": window, "market": market, "nonce": datetime.now().isoformat()}
        if trigger == "open-ranked":
            return True, "Ranked Candidates", f"{int(counts.get('survivors', 0)):,} verified survivors", "Server-paged exact survivor identities. The separately gated Candidates page is not fabricated here.", {"kind": "ranked", "window": window, "market": market, "nonce": datetime.now().isoformat()}
        return False, "Dashboard detail", "—", "No detail is available.", None

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
    application = Dash(__name__, title="Quant Factory", suppress_callback_exceptions=True)
    application.layout = html.Div([dcc.Location(id="router-location", refresh=False), html.Div(id="route-page")])

    @application.callback(Output("route-page", "children"), Input("router-location", "pathname"), Input("router-location", "search"))
    def route(pathname: str | None, search: str | None):
        if pathname == "/candidates": return candidates_layout()
        if pathname == "/results": return results_layout(search)
        return dashboard_layout()

    @application.callback(
        Output("router-location", "pathname"), Output("router-location", "search"),
        Input("nav-candidates", "n_clicks", allow_optional=True), Input("nav-results", "n_clicks", allow_optional=True), Input("open-results", "n_clicks", allow_optional=True),
        Input("candidates-nav-dashboard", "n_clicks", allow_optional=True), Input("candidates-nav-results", "n_clicks", allow_optional=True), Input("candidate-open-results", "n_clicks", allow_optional=True),
        Input("results-nav-dashboard", "n_clicks", allow_optional=True), Input("results-nav-candidates", "n_clicks", allow_optional=True), Input("results-back-candidates", "n_clicks", allow_optional=True),
        State("selected-candidate", "data", allow_optional=True), State("candidate-detail-record", "data", allow_optional=True), prevent_initial_call=True,
    )
    def navigate(*values: Any):
        trigger = ctx.triggered_id
        if trigger in {"nav-candidates", "results-nav-candidates", "results-back-candidates"}: return "/candidates", ""
        if trigger in {"open-results", "candidate-open-results"}:
            selected = values[-2] if trigger == "open-results" else values[-1]
            run_id = (selected or {}).get("run_id")
            return "/results", f"?run_id={run_id}" if run_id else ""
        if trigger in {"nav-results", "candidates-nav-results"}: return "/results", ""
        return "/", ""

    register_callbacks(application)
    register_candidate_callbacks(application)
    register_results_callbacks(application)
    return application


app = create_app()
server = app.server


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
