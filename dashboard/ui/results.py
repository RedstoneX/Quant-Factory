"""Production Results workspace in the accepted Quant Factory shell."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
import plotly.graph_objects as go

from dashboard.results_projection import list_results_runs, load_results_record


GLYPHS = {"dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷", "chart": "⌁", "external": "↗", "back": "←", "reset": "↻"}
TRADE_COLUMNS = [
    {"field": "trade_id", "headerName": "Trade", "width": 72, "pinned": "left"},
    {"field": "direction", "headerName": "Side", "width": 70},
    {"field": "entry_timestamp", "headerName": "Entry", "minWidth": 150, "flex": 1},
    {"field": "exit_timestamp", "headerName": "Exit", "minWidth": 150, "flex": 1},
    {"field": "duration", "headerName": "Duration", "width": 84},
    {"field": "pnl", "headerName": "Net P&L", "type": "numericColumn", "width": 90},
    {"field": "outcome", "headerName": "Outcome", "width": 86},
]


def _icon(name: str) -> html.Span:
    return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})


def _rail(name: str, label: str, item_id: str, *, active: bool = False, disabled: bool = False) -> dmc.ActionIcon:
    return dmc.ActionIcon(_icon(name), id=item_id, className=f"rail-item{' active' if active else ''}", variant="subtle", disabled=disabled, **{"aria-label": label})


def _empty_figure(message: str, *, height: int = 300) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font={"color": "#8a97a8", "size": 11})
    figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
    figure.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return figure


def _style(figure: go.Figure, *, height: int) -> go.Figure:
    figure.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 44, "r": 16, "t": 18, "b": 34}, font={"family": "Inter, sans-serif", "size": 9, "color": "#8a97a8"},
        legend={"orientation": "h", "y": 1.08}, hovermode="x unified",
    )
    figure.update_xaxes(gridcolor="#202936", linecolor="#344050", zeroline=False)
    figure.update_yaxes(gridcolor="#202936", linecolor="#344050", zeroline=False)
    return figure


def _price_figure(record: dict[str, Any] | None, selected: dict[str, Any] | None, view: str, nonce: Any) -> go.Figure:
    record = record or {}
    rows = record.get("price") or []
    if not rows:
        return _empty_figure(record.get("price_reason") or record.get("message") or "No persisted OHLC bars are available.", height=326)
    figure = go.Figure(go.Candlestick(
        x=[row["timestamp"] for row in rows], open=[row["open"] for row in rows], high=[row["high"] for row in rows],
        low=[row["low"] for row in rows], close=[row["close"] for row in rows], name="Persisted OHLC",
        increasing_line_color="#38d39f", decreasing_line_color="#ff5f6d",
    ))
    if selected:
        entry, exit_at = selected.get("entry_timestamp"), selected.get("exit_timestamp")
        if entry: figure.add_vline(x=entry, line_color="#4aa8ff", line_dash="dot")
        if exit_at: figure.add_vline(x=exit_at, line_color="#9b7bff", line_dash="dot")
    if view == "morning":
        figure.update_xaxes(rangebreaks=[])
    figure.update_layout(xaxis_rangeslider_visible=False, uirevision=f"results-{nonce}")
    return _style(figure, height=326)


def _evidence_figure(record: dict[str, Any], tab: str) -> go.Figure:
    if tab != "equity":
        return _empty_figure(f"{tab.replace('_', ' ').title()} chart evidence is not persisted for this run.", height=168)
    equity, drawdown = record.get("equity") or [], record.get("drawdown") or []
    if not equity:
        return _empty_figure("No persisted equity and drawdown series are available.", height=168)
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=[row.get("timestamp") for row in equity], y=[row.get("value") for row in equity], name="Equity", line={"color": "#4aa8ff", "width": 2}))
    if drawdown:
        figure.add_trace(go.Scatter(x=[row.get("timestamp") for row in drawdown], y=[row.get("drawdown") for row in drawdown], name="Drawdown", yaxis="y2", line={"color": "#ff5f6d", "width": 1.4}))
        figure.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
    return _style(figure, height=168)


def _run_from_search(search: str | None, runs: list[dict[str, Any]]) -> str | None:
    requested = parse_qs((search or "").lstrip("?")).get("run_id", [None])[0]
    if requested and any(row["run_id"] == requested for row in runs):
        return requested
    return next((row["run_id"] for row in runs if row["status"] == "succeeded"), runs[0]["run_id"] if runs else None)


def results_layout(search: str | None = None) -> dmc.MantineProvider:
    runs = list_results_runs()
    selected = _run_from_search(search, runs)
    choices = [{"value": row["run_id"], "label": f"{row['title']} · {row['stage']} · {row['status']}"} for row in runs]
    nav = dmc.Stack([
        dmc.Paper("Q", className="logo", radius="md"), _rail("dashboard", "Dashboard", "results-nav-dashboard"),
        _rail("file", "Submit strategies", "results-nav-submit"), _rail("flow", "Factory runs", "results-nav-factory"),
        _rail("list", "Candidates", "results-nav-candidates"), _rail("chart", "Results", "results-nav-results", active=True),
        html.Div(className="rail-spacer"), _rail("external", "Paper Trading unavailable", "results-nav-paper", disabled=True), dmc.Avatar("TO", className="avatar", radius="xl"),
    ], gap=7, align="center", className="rail")
    header = dmc.Group([
        html.Div([dmc.Title("Results", id="results-title", order=1), dmc.Text("Exact persisted run evidence", id="results-meta", className="eyebrow")]),
        html.Div(className="top-spacer"), dmc.Badge("Loading", id="results-state", className="candidate-state"),
        dmc.Button("View sensitivity", id="results-sensitivity", className="ghost", variant="default"),
        dmc.Button("Compare selected unavailable", className="ghost", variant="default", disabled=True),
    ], gap=9, className="topbar results-topbar")
    toolbar = dmc.Group([
        dmc.Select(id="results-run", data=choices, value=selected, allowDeselect=False, searchable=True, placeholder="No persisted runs", className="results-run-select"),
        dmc.Select(id="results-bars", data=[{"value": "5m", "label": "Bars · 5 minute"}, {"value": "15m", "label": "Bars · 15 minute"}, {"value": "1D", "label": "Bars · daily"}], value="15m", allowDeselect=False, className="results-control"),
        dmc.Select(id="results-view", data=[{"value": "session", "label": "View · full session"}, {"value": "trade", "label": "View · selected trade"}, {"value": "morning", "label": "View · morning"}], value="session", allowDeselect=False, className="results-control"),
        dmc.Button("Reset range", id="results-reset-range", leftSection=_icon("reset"), className="ghost", variant="default"),
        dmc.Button("Reset layout", id="results-reset-layout", className="ghost", variant="default"),
        html.Div(className="top-spacer"), dmc.Text("Persisted OHLC and completed trades", className="candidate-context"),
    ], gap=8, className="candidate-filters results-toolbar")
    context = dmc.Group([
        dmc.Button("Ranked survivors", id="results-back-candidates", leftSection=_icon("back"), className="ghost", variant="default"),
        dmc.Badge("Sealed run", id="results-run-chip", className="filter-chip"),
        dmc.Select(id="results-session", data=[{"value": "all", "label": "All persisted sessions"}], value="all", allowDeselect=False, className="results-session"),
        dmc.Badge("Bars unavailable", id="results-bars-chip", className="filter-chip"), html.Div(className="top-spacer"),
        dmc.Badge("Paper lane inactive", className="candidate-state"), dmc.Button("View evidence", id="results-package", className="ghost", variant="default"),
    ], gap=8, className="candidate-filters results-context")
    price_panel = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Price and completed trades", order=3), dmc.Text("Persisted run evidence · select a trade to focus its interval", id="results-chart-caption", className="panel-subtitle")]), html.Div(className="top-spacer")], className="panel-head"),
        dcc.Graph(id="results-price-chart", figure=_empty_figure("Loading persisted OHLC bars", height=326), config={"displayModeBar": False, "scrollZoom": True, "responsive": True}),
        html.Div(id="results-assumptions", className="results-assumptions"),
    ], className="panel results-price", radius="md", withBorder=True)
    metrics = html.Aside(id="results-metrics", className="results-metrics")
    ledger = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Completed trade ledger", order=3), dmc.Text("Select a trade to focus its exact persisted interval", className="panel-subtitle")]), html.Div(className="top-spacer"), dmc.TextInput(id="results-trade-search", placeholder="Search trades", className="results-trade-search", debounce=True)], className="panel-head"),
        dag.AgGrid(id="results-trade-grid", columnDefs=TRADE_COLUMNS, rowData=[], defaultColDef={"sortable": True, "resizable": True, "filter": True}, dashGridOptions={"rowSelection": {"mode": "singleRow", "enableClickSelection": True}, "pagination": True, "paginationPageSize": 5, "animateRows": False}, getRowId="params.data.trade_id", className="ag-theme-quartz-dark results-trade-grid"),
        html.Footer([html.Span("0 persisted trades", id="results-trade-count"), html.Div(className="top-spacer"), html.Span("Bounded ledger")], className="candidate-grid-footer"),
    ], className="panel results-ledger", radius="md", withBorder=True)
    linked = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Linked evidence", order=3), dmc.Text("Selection remains synchronized across analysis", className="panel-subtitle")])], className="panel-head"),
        dmc.Tabs([dmc.TabsList([dmc.TabsTab("Equity & DD", value="equity"), dmc.TabsTab("Robustness", value="robustness"), dmc.TabsTab("Walk-forward", value="walk_forward"), dmc.TabsTab("Monte Carlo", value="monte_carlo"), dmc.TabsTab("Lineage", value="lineage")])], id="results-evidence-tab", value="equity", className="candidate-detail-tabs"),
        html.Div(id="results-evidence-body", className="results-evidence-body"),
    ], className="panel results-linked", radius="md", withBorder=True)
    stores = [dcc.Store(id="results-record"), dcc.Store(id="results-range-nonce", data=0)]
    body = html.Div([toolbar, context, html.Div([price_panel, metrics], className="results-primary"), html.Div([ledger, linked], className="results-lower")], className="body results-body")
    return dmc.MantineProvider(html.Div([*stores, html.Div([nav, html.Main([header, body], className="main")], className="app results-app")]), forceColorScheme="dark", theme={"fontFamily": "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", "primaryColor": "blue"})


def _metric_value(metrics: list[dict[str, str]], *labels: str) -> str:
    return next((item["value"] for item in metrics if item["label"] in labels), "—")


def _display_trades(record: dict[str, Any], search: str | None) -> list[dict[str, Any]]:
    rows = record.get("trades") or []
    token = (search or "").strip().lower()
    if token:
        rows = [row for row in rows if token in " ".join(str(value).lower() for value in row.values())]
    return rows


def register_results_callbacks(application: Any) -> None:
    @application.callback(Output("results-record", "data"), Input("results-run", "value"), Input("results-bars", "value"))
    def load_record(run_id: str | None, interval: str) -> dict[str, Any]:
        return load_results_record(run_id, interval=interval or "15m")

    @application.callback(
        Output("results-title", "children"), Output("results-meta", "children"), Output("results-state", "children"),
        Output("results-run-chip", "children"), Output("results-bars-chip", "children"), Output("results-chart-caption", "children"),
        Output("results-metrics", "children"), Output("results-assumptions", "children"), Output("results-session", "data"), Output("results-session", "value"),
        Input("results-record", "data"),
    )
    def render_record(record: dict[str, Any] | None):
        record = record or {}; run = record.get("run") or {}; metrics = record.get("metrics") or []
        title = run.get("title") or "Results unavailable"; run_id = run.get("run_id") or "No run identity"
        result_status = str(record.get("result_status") or "").strip().lower()
        state = "Evidence invalid" if result_status == "invalid" else str(run.get("status") or "Unavailable").replace("_", " ").title()
        metric_cards = [
            ("Net return", _metric_value(metrics, "Total Return")), ("OOS Sharpe", _metric_value(metrics, "Sharpe Ratio")),
            ("Maximum drawdown", _metric_value(metrics, "Max Drawdown")), ("Completed trades", _metric_value(metrics, "Number Of Trades")),
            ("Win rate", _metric_value(metrics, "Win Rate")), ("Profit factor", _metric_value(metrics, "Profit Factor")),
            ("Evidence", record.get("result_status") or "Unavailable"),
        ]
        cards = [html.Div([html.Span(label), html.Strong(value)], className="results-metric") for label, value in metric_cards]
        assumptions = [html.Div([html.Span("Run"), html.Strong(run_id)], className="results-assumption"), html.Div([html.Span("Market"), html.Strong(run.get("symbol") or "Unrecorded")], className="results-assumption"), html.Div([html.Span("Stage"), html.Strong(str(run.get("stage") or "Unrecorded").replace("_", " ").title())], className="results-assumption"), html.Div([html.Span("Authority"), html.Strong("Research evidence only")], className="results-assumption")]
        sessions = sorted({str(row.get("entry_timestamp") or "")[:10] for row in record.get("trades") or [] if row.get("entry_timestamp")})
        session_data = [{"value": "all", "label": "All persisted sessions"}] + [{"value": day, "label": f"Session · {day}"} for day in sessions]
        caption = record.get("price_reason") or "Persisted OHLC · scroll to zoom · select a trade to focus"
        return title, f"{run_id} · exact persisted evidence", state, f"Sealed run · {run_id[:12]}", f"{record.get('interval', '—')} bars", caption, cards, assumptions, session_data, "all"

    @application.callback(Output("results-trade-grid", "rowData"), Output("results-trade-count", "children"), Input("results-record", "data"), Input("results-trade-search", "value"), Input("results-session", "value"))
    def render_trades(record: dict[str, Any] | None, search: str | None, session: str) -> tuple[list[dict[str, Any]], str]:
        record = record or {}; rows = _display_trades(record, search)
        if session and session != "all": rows = [row for row in rows if str(row.get("entry_timestamp") or "").startswith(session)]
        total = int(record.get("trade_count") or 0); bounded = int(record.get("trade_limit") or 0)
        return rows, f"{len(rows):,} shown · {total:,} persisted" + (f" · first {bounded:,} loaded" if total > bounded else "")

    @application.callback(Output("results-price-chart", "figure"), Input("results-record", "data"), Input("results-trade-grid", "selectedRows"), Input("results-view", "value"), Input("results-range-nonce", "data"))
    def render_price(record: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, view: str, nonce: Any) -> go.Figure:
        return _price_figure(record, (selected_rows or [None])[-1], view or "session", nonce)

    @application.callback(Output("results-evidence-body", "children"), Input("results-record", "data"), Input("results-evidence-tab", "value"))
    def render_evidence(record: dict[str, Any] | None, tab: str):
        record = record or {}
        if tab == "equity": return dcc.Graph(figure=_evidence_figure(record, tab), config={"displayModeBar": False, "responsive": True})
        fields = record.get("lineage") if tab == "lineage" else []
        if fields:
            return html.Div([html.Div([html.Span(item["label"]), html.Strong(item["value"])], className="candidate-evidence-item") for item in fields[:8]], className="results-evidence-list")
        return html.Div([dcc.Graph(figure=_evidence_figure(record, tab), config={"displayModeBar": False})])

    @application.callback(Output("results-range-nonce", "data"), Input("results-reset-range", "n_clicks"), State("results-range-nonce", "data"), prevent_initial_call=True)
    def reset_range(_clicks: int, nonce: int | None) -> int:
        return int(nonce or 0) + 1

    @application.callback(Output("results-view", "value"), Output("results-evidence-tab", "value"), Input("results-reset-layout", "n_clicks"), Input("results-sensitivity", "n_clicks"), Input("results-package", "n_clicks"), prevent_initial_call=True)
    def change_layout(*_clicks: Any):
        if ctx.triggered_id == "results-sensitivity": return no_update, "robustness"
        if ctx.triggered_id == "results-package": return no_update, "lineage"
        return "session", "equity"


__all__ = ["register_results_callbacks", "results_layout"]
