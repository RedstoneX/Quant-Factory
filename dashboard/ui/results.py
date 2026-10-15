"""Production Results workspace in the accepted Quant Factory shell."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
import plotly.graph_objects as go

from dashboard.overview_projection import configured_database_path
from orchestration.candidate_setting_rebuild import SettingRebuildRefused, rebuild_setting

from dashboard.results_projection import (
    list_results_runs,
    list_screening_configuration_sessions,
    load_results_record,
    load_screening_configuration_evidence,
)


GLYPHS = {"dashboard": "▦", "file": "+", "flow": "⌁", "list": "☷", "chart": "⌁", "external": "↗", "back": "←", "reset": "↻"}
TRADE_COLUMNS = [
    {"field": "trade_id", "headerName": "Trade", "width": 72, "pinned": "left"},
    {"field": "direction", "headerName": "Side", "width": 70},
    {"field": "entry_display", "headerName": "Entry (Eastern)", "minWidth": 170, "flex": 1},
    {"field": "exit_display", "headerName": "Exit (Eastern)", "minWidth": 170, "flex": 1},
    {"field": "duration", "headerName": "Duration", "width": 84},
    {"field": "pnl", "headerName": "Net P&L", "type": "numericColumn", "width": 90},
    {"field": "outcome", "headerName": "Outcome", "width": 86},
]
METRIC_COLUMNS = [
    {"field": "total_return", "headerName": "Net return", "type": "numericColumn", "width": 98, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "sharpe_ratio", "headerName": "Sharpe", "type": "numericColumn", "width": 84, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Maximum DD", "type": "numericColumn", "width": 102, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "number_of_trades", "headerName": "Trades", "type": "numericColumn", "width": 80, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}},
    {"field": "win_rate", "headerName": "Win rate", "type": "numericColumn", "width": 88, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "screening_status", "headerName": "Outcome", "minWidth": 112, "flex": 1, "valueFormatter": {"function": "params.value === 'screened_out' ? 'Failed testing' : params.value"}},
]


def _screening_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = list((rows[0].get("parameters") or {}) if rows else [])
    centred = {"headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}}
    parameters = [{"field": f"parameters.{name}", "headerName": name.replace("_", " ").capitalize(), "minWidth": 90, **centred} for name in names]
    return [{"field": "rank", "headerName": "Rank", "minWidth": 64, "pinned": "left", **centred}, *parameters, *METRIC_COLUMNS]

_GRAPH_CONFIG = {"displayModeBar": False, "scrollZoom": True, "responsive": True}


def _icon(name: str) -> html.Span:
    return html.Span(GLYPHS[name], className="icon", **{"aria-hidden": "true"})


def _rail(name: str, label: str, item_id: str, *, active: bool = False, disabled: bool = False) -> dmc.ActionIcon:
    return dmc.Tooltip(dmc.ActionIcon(_icon(name), id=item_id, className=f"rail-item{' active' if active else ''}", variant="subtle", disabled=disabled, **{"aria-label": label}), label=label, position="right", withArrow=True, openDelay=300)


def _empty_figure(message: str, *, height: int = 300) -> go.Figure:
    figure = go.Figure()
    figure.add_shape(
        type="rect", x0=.16, x1=.84, y0=.31, y1=.69, xref="paper", yref="paper",
        line={"color": "rgba(74,168,255,.22)", "width": 1},
        fillcolor="rgba(74,168,255,.035)", layer="below",
    )
    figure.add_annotation(
        text=f"<b>Evidence boundary</b><br><span style='font-size:10px'>{message}</span>",
        x=.5, y=.5, xref="paper", yref="paper", showarrow=False, align="center",
        font={"color": "#aebdce", "size": 12},
    )
    figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
    figure.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(7,10,15,.32)", margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return figure


def _style(figure: go.Figure, *, height: int) -> go.Figure:
    figure.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 44, "r": 16, "t": 18, "b": 48}, font={"family": "Inter, sans-serif", "size": 9, "color": "#8a97a8"},
        legend={"orientation": "h", "y": 1.08}, hovermode="x unified",
    )
    figure.update_xaxes(
        gridcolor="#202936", linecolor="#344050", zeroline=False,
        type="date", tickformat="%b %d<br>%I:%M %p", title_text="Eastern time",
        title_standoff=7, showticklabels=True, ticks="outside", automargin=True,
    )
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


def _configuration_equity_figure(evidence: dict[str, Any]) -> go.Figure:
    rows = evidence.get("equity") or []
    if not rows:
        return _empty_figure("No persisted equity series is available for this configuration.", height=168)
    values = [float(row["value"]) for row in rows]
    peaks: list[float] = []
    peak = values[0]
    for value in values:
        peak = max(peak, value)
        peaks.append(peak)
    drawdown = [((value / high) - 1) * 100 if high else 0 for value, high in zip(values, peaks)]
    timestamps = [row.get("timestamp") for row in rows]
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=timestamps, y=values, name="Equity", line={"color": "#4aa8ff", "width": 2}))
    figure.add_trace(go.Scatter(x=timestamps, y=drawdown, name="Drawdown %", yaxis="y2", line={"color": "#ff5f6d", "width": 1.4}))
    figure.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "ticksuffix": "%"})
    return _style(figure, height=168)


def _configuration_metric_cards(evidence: dict[str, Any]) -> list[Any]:
    metrics = evidence.get("metrics") or {}

    def percentage(key: str, *, absolute: bool = False) -> str:
        value = metrics.get(key)
        if value is None:
            return "—"
        number = float(value)
        if abs(number) <= 1:
            number *= 100
        number = abs(number) if absolute else number
        return f"{number:+.2f}%" if key == "total_return" else f"{number:.2f}%"

    values = [
        ("Selected net return", percentage("total_return")),
        ("Selected Sharpe", "—" if metrics.get("sharpe_ratio") is None else f"{float(metrics['sharpe_ratio']):.2f}"),
        ("Maximum drawdown", percentage("max_drawdown", absolute=True)),
        ("Completed trades", f"{int(metrics.get('number_of_trades') or 0):,}"),
        ("Win rate", percentage("win_rate")),
        ("Evidence", "Exact retained screening"),
    ]
    return [html.Div([html.Span(label), html.Strong(value)], className="results-metric") for label, value in values]


def _configuration_chart_caption(evidence: dict[str, Any], identity: str) -> str:
    rows = evidence.get("price") or []
    trades = evidence.get("trades") or []
    if not rows:
        return f"Selected configuration · {identity} · no retained price session"
    first, last = str(rows[0]["timestamp"]), str(rows[-1]["timestamp"])
    plotted = sum(
        1 for trade in trades
        if trade.get("entry_timestamp") and first <= str(trade["entry_timestamp"]) <= last
    )
    session = str(evidence.get("selected_session") or first[:10])
    total = int(evidence.get("trade_count") or len(trades))
    return f"Selected configuration · {identity} · session {session} Eastern · {plotted} of {total:,} trades shown"


def _configuration_identity(selected: dict[str, Any]) -> str:
    if selected.get("range_minutes") is not None:
        offset = int(selected.get("breakout_offset_ticks") or 0)
        tick_label = "tick" if offset == 1 else "ticks"
        direction = str(selected.get("direction_variant") or "Unrecorded").title()
        return f"{int(selected['range_minutes'])}-minute opening range · {offset} {tick_label} · {direction}"
    if selected.get("run_length") is not None:
        return f"{selected['run_length']} run bars · {selected.get('minimum_ticks_per_bar', '—')} minimum ticks"
    return "Exact persisted parameters"


def _run_from_search(search: str | None, runs: list[dict[str, Any]]) -> str | None:
    requested = parse_qs((search or "").lstrip("?")).get("run_id", [None])[0]
    if requested and any(row["run_id"] == requested for row in runs):
        return requested
    return next((row["run_id"] for row in runs if row["status"] == "succeeded"), runs[0]["run_id"] if runs else None)


def results_layout(search: str | None = None) -> dmc.MantineProvider:
    runs = list_results_runs()
    selected = _run_from_search(search, runs)
    choices = [
        {"value": row["run_id"], "label": f"{row['title']} · {row['stage']} · {row['status']} · {row['run_id'][:12]}"}
        for row in runs
    ]
    nav = dmc.Stack([
        dmc.Paper("Q", className="logo", radius="md"), _rail("dashboard", "Dashboard", "results-nav-dashboard"),
        _rail("file", "Submit strategies", "results-nav-submit"), _rail("flow", "Factory runs", "results-nav-factory"),
        _rail("list", "Candidates", "results-nav-candidates"), _rail("chart", "Results", "results-nav-results", active=True),
        html.Div(className="rail-spacer"), _rail("external", "Paper Trading", "results-nav-paper"), dmc.Avatar("TO", className="avatar", radius="xl"),
    ], gap=7, align="center", className="rail")
    header = dmc.Group([
        html.Div([dmc.Title("Results", order=1), dmc.Text("Select a run and inspect its persisted evidence", className="eyebrow")]),
        html.Div([dmc.Text("Selected run", className="results-run-kicker"), dmc.Text("Loading", id="results-run-name", className="results-run-name"), dmc.Text("Exact persisted run evidence", id="results-meta", className="results-run-meta")], className="results-run-identity"),
        html.Div(className="top-spacer"), dmc.Badge("Loading", id="results-state", className="candidate-state"),
        dmc.Button("View screening decision", id="results-sensitivity", className="ghost", variant="default"),
        dmc.Button("Compare selected unavailable", className="ghost", variant="default", disabled=True),
    ], gap=9, className="topbar results-topbar")
    toolbar = dmc.Group([
        dmc.Select(id="results-run", data=choices, value=selected, allowDeselect=False, searchable=True, placeholder="No persisted runs", className="results-run-select"),
        dmc.Select(id="results-bars", data=[{"value": "5m", "label": "Bars · 5 minute"}, {"value": "15m", "label": "Bars · 15 minute"}, {"value": "1D", "label": "Bars · daily"}], value="15m", allowDeselect=False, className="results-control"),
        dmc.Select(id="results-view", data=[{"value": "session", "label": "View · full session"}, {"value": "trade", "label": "View · selected trade"}, {"value": "morning", "label": "View · morning"}], value="session", allowDeselect=False, className="results-control"),
        dmc.Button("Reset range", id="results-reset-range", leftSection=_icon("reset"), className="ghost", variant="default"),
        dmc.Button("Reset layout", id="results-reset-layout", className="ghost", variant="default"),
        html.Div(className="top-spacer"), dmc.Text("Persisted OHLC and completed trades", id="results-toolbar-context", className="candidate-context"),
    ], gap=8, className="candidate-filters results-toolbar")
    context = dmc.Group([
        dmc.Button("Back to Candidate", id="results-back-candidates", leftSection=_icon("back"), className="ghost", variant="default"),
        dmc.Badge("Sealed run", id="results-run-chip", className="filter-chip"),
        dmc.Select(id="results-session", data=[{"value": "all", "label": "All persisted sessions"}], value="all", allowDeselect=False, className="results-session"),
        dmc.Badge("Bars unavailable", id="results-bars-chip", className="filter-chip"), html.Div(className="top-spacer"),
        dmc.Badge("Paper lane inactive", className="candidate-state"), dmc.Button("View evidence", id="results-package", className="ghost", variant="default"),
    ], gap=8, className="candidate-filters results-context")
    price_panel = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Price and completed trades", id="results-chart-title", order=3), dmc.Text("Persisted run evidence · select a trade to focus its interval", id="results-chart-caption", className="panel-subtitle")]), html.Div(className="top-spacer")], className="panel-head"),
        dcc.Loading(html.Div(id="results-price-chart", className="results-price-chart"), type="dot"),
        html.Div(id="results-assumptions", className="results-assumptions"),
    ], className="panel results-price", radius="md", withBorder=True)
    metrics = html.Aside(id="results-metrics", className="results-metrics")
    ledger = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Completed trade ledger", id="results-ledger-title", order=3), dmc.Text("Select a trade to focus its exact persisted interval", id="results-ledger-subtitle", className="panel-subtitle")]), html.Div(className="top-spacer"), dmc.TextInput(id="results-trade-search", placeholder="Search trades", className="results-trade-search", debounce=True)], className="panel-head"),
        dag.AgGrid(id="results-trade-grid", columnDefs=TRADE_COLUMNS, rowData=[], columnSize="responsiveSizeToFit", defaultColDef={"sortable": True, "resizable": True, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True}, dashGridOptions={"rowSelection": {"mode": "singleRow", "enableClickSelection": True}, "pagination": True, "paginationPageSize": 6, "paginationPageSizeSelector": False, "animateRows": False}, getRowId="params.data.trade_id || params.data.row_id", className="ag-theme-quartz-dark results-trade-grid"),
        html.Footer([html.Span("0 persisted trades", id="results-trade-count"), html.Div(className="top-spacer"), html.Span("Bounded ledger")], className="candidate-grid-footer"),
    ], className="panel results-ledger", radius="md", withBorder=True)
    linked = dmc.Paper([
        dmc.Group([html.Div([dmc.Title("Linked evidence", order=3), dmc.Text("Selection remains synchronized across analysis", className="panel-subtitle")])], className="panel-head"),
        dmc.Tabs([dmc.TabsList([dmc.TabsTab("Trades", value="trades"), dmc.TabsTab("Equity & DD", value="equity"), dmc.TabsTab("Robustness", value="robustness"), dmc.TabsTab("Walk-forward", value="walk_forward"), dmc.TabsTab("Monte Carlo", value="monte_carlo"), dmc.TabsTab("Lineage", value="lineage")])], id="results-evidence-tab", value="trades", className="candidate-detail-tabs"),
        html.Div(id="results-evidence-body", className="results-evidence-body"),
    ], className="panel results-linked", radius="md", withBorder=True)
    stores = [dcc.Store(id="results-record"), dcc.Store(id="results-configuration-evidence"), dcc.Store(id="results-range-nonce", data=0)]
    body = html.Div([toolbar, context, html.Div([price_panel, metrics], className="results-primary"), html.Div([ledger, linked], className="results-lower")], className="body results-body")
    return dmc.MantineProvider(html.Div([*stores, html.Div([nav, html.Main([header, body], className="main")], className="app results-app")]), forceColorScheme="dark", theme={"fontFamily": "Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif", "primaryColor": "blue"})


def _metric_value(metrics: list[dict[str, str]], *labels: str) -> str:
    return next((item["value"] for item in metrics if item["label"] in labels), "—")


def _display_trades(record: dict[str, Any], search: str | None) -> list[dict[str, Any]]:
    rows = record.get("screening_rows") or record.get("trades") or []
    token = (search or "").strip().lower()
    if token:
        rows = [row for row in rows if token in " ".join(str(value).lower() for value in row.values())]
    return rows


def _register_record_callbacks(application: Any) -> None:
    @application.callback(Output("results-record", "data"), Input("results-run", "value"), Input("results-bars", "value"))
    def load_record(run_id: str | None, interval: str) -> dict[str, Any]:
        return load_results_record(run_id, interval=interval or "15m")

    @application.callback(
        Output("results-run-name", "children"), Output("results-meta", "children"), Output("results-state", "children"), Output("results-state", "className"),
        Output("results-run-chip", "children"), Output("results-assumptions", "children"),
        Output("results-chart-title", "children"), Output("results-ledger-title", "children"), Output("results-ledger-subtitle", "children"), Output("results-trade-search", "placeholder"), Output("results-toolbar-context", "children"),
        Output("results-bars", "disabled"), Output("results-view", "disabled"), Output("results-reset-range", "disabled"),
        Input("results-record", "data"),
    )
    def render_record(record: dict[str, Any] | None):
        record = record or {}; run = record.get("run") or {}
        title = run.get("title") or "Results unavailable"; run_id = run.get("run_id") or "No run identity"
        result_status = str(record.get("result_status") or "").strip().lower()
        screening_rows = record.get("screening_rows") or []
        screened_out = bool(screening_rows) and int(record.get("screened_out_count") or 0) == len(screening_rows)
        state = "Failed testing" if screened_out else "Evidence invalid" if result_status == "invalid" else str(run.get("status") or "Unavailable").replace("_", " ").title()
        assumptions = [html.Div([html.Span("Run"), html.Strong(run_id)], className="results-assumption"), html.Div([html.Span("Market"), html.Strong(run.get("symbol") or "Unrecorded")], className="results-assumption"), html.Div([html.Span("Stage"), html.Strong(str(run.get("stage") or "Unrecorded").replace("_", " ").title())], className="results-assumption"), html.Div([html.Span("Authority"), html.Strong("Research evidence only")], className="results-assumption")]
        return (
            title, f"{run_id} · exact persisted evidence", state, "candidate-state rejected" if screened_out else "candidate-state", f"Sealed run · {run_id[:12]}",
            assumptions,
            "Selected configuration price and trades" if screened_out else "Price and completed trades",
            f"{len(screening_rows):,} declared configurations" if screened_out else "Completed trade ledger",
            "Select a configuration to inspect its exact rejection reasons" if screened_out else "Select a trade to focus its exact persisted interval",
            "Search configurations" if screened_out else "Search trades",
            "Select a configuration to inspect its persisted screening evidence" if screened_out else "Persisted OHLC and completed trades",
            False, screened_out, False,
        )

    @application.callback(
        Output("results-session", "data"), Output("results-session", "value"), Output("results-session", "disabled"),
        Input("results-record", "data"), Input("results-trade-grid", "selectedRows"),
    )
    def configure_sessions(record: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None):
        record = record or {}; screening_rows = record.get("screening_rows") or []
        if screening_rows:
            selected = (selected_rows or screening_rows[:1])[-1]
            sessions = list_screening_configuration_sessions(
                (record.get("run") or {}).get("run_id"), selected.get("row_id")
            )
            data = [{"value": day, "label": f"Session · {day} (Eastern)"} for day in sessions]
            return data, (sessions[-1] if sessions else None), not bool(sessions)
        sessions = sorted({str(row.get("entry_timestamp") or "")[:10] for row in record.get("trades") or [] if row.get("entry_timestamp")})
        data = [{"value": "all", "label": "All persisted sessions"}] + [{"value": day, "label": f"Session · {day}"} for day in sessions]
        return data, "all", False


def _register_configuration_callbacks(application: Any) -> None:
    @application.callback(
        Output("results-bars-chip", "children"), Output("results-chart-caption", "children"), Output("results-metrics", "children"),
        Input("results-record", "data"), Input("results-configuration-evidence", "data"),
    )
    def render_selected_configuration(record: dict[str, Any] | None, configuration_evidence: dict[str, Any] | None):
        record = record or {}; configuration_evidence = configuration_evidence or {}
        screening_rows = record.get("screening_rows") or []
        if screening_rows:
            if not configuration_evidence.get("available"):
                metrics = record.get("metrics") or []
                cards = [
                    html.Div([html.Span(label), html.Strong(value)], className="results-metric")
                    for label, value in (
                        ("Best net return", _metric_value(metrics, "Total Return")),
                        ("Screening Sharpe", _metric_value(metrics, "Sharpe Ratio")),
                        ("Maximum drawdown", _metric_value(metrics, "Max Drawdown")),
                        ("Screening trades", _metric_value(metrics, "Number Of Trades")),
                        ("Win rate", _metric_value(metrics, "Win Rate")),
                        ("Evidence", configuration_evidence.get("message") or "Select a configuration"),
                    )
                ]
                return "Configuration evidence", configuration_evidence.get("message") or "Select a configuration to load its exact retained evidence", cards
            row_id = configuration_evidence.get("parameter_row_id")
            selected = next((row for row in screening_rows if row.get("row_id") == row_id), {})
            identity = _configuration_identity(selected)
            return (
                f"{configuration_evidence.get('interval', '—')} bars",
                _configuration_chart_caption(configuration_evidence, identity),
                _configuration_metric_cards(configuration_evidence),
            )
        metrics = record.get("metrics") or []
        cards = [
            html.Div([html.Span(label), html.Strong(value)], className="results-metric")
            for label, value in (
                ("Net return", _metric_value(metrics, "Total Return")),
                ("OOS Sharpe", _metric_value(metrics, "Sharpe Ratio")),
                ("Maximum drawdown", _metric_value(metrics, "Max Drawdown")),
                ("Completed trades", _metric_value(metrics, "Number Of Trades")),
                ("Win rate", _metric_value(metrics, "Win Rate")),
                ("Profit factor", _metric_value(metrics, "Profit Factor")),
                ("Evidence", record.get("result_status") or "Unavailable"),
            )
        ]
        return f"{record.get('interval', '—')} bars", record.get("price_reason") or "Persisted OHLC · scroll to zoom · select a trade to focus", cards

    @application.callback(Output("results-trade-grid", "rowData"), Output("results-trade-grid", "columnDefs"), Output("results-trade-count", "children"), Input("results-record", "data"), Input("results-trade-search", "value"), Input("results-session", "value"))
    def render_trades(record: dict[str, Any] | None, search: str | None, session: str):
        record = record or {}; rows = _display_trades(record, search)
        screening = bool(record.get("screening_rows"))
        if not screening and session and session != "all": rows = [row for row in rows if str(row.get("entry_timestamp") or "").startswith(session)]
        if screening:
            total = int(record.get("screening_count") or 0)
            return rows, _screening_columns(rows), f"{len(rows):,} shown · {total:,} declared configurations · all screened out"
        total = int(record.get("trade_count") or 0); bounded = int(record.get("trade_limit") or 0)
        return rows, TRADE_COLUMNS, f"{len(rows):,} shown · {total:,} persisted" + (f" · first {bounded:,} loaded" if total > bounded else "")

    @application.callback(
        Output("results-configuration-evidence", "data"),
        Input("results-record", "data"), Input("results-trade-grid", "selectedRows"), Input("results-bars", "value"), Input("results-session", "value"),
    )
    def load_configuration_evidence(record: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, interval: str, session: str | None) -> dict[str, Any]:
        record = record or {}
        screening_rows = record.get("screening_rows") or []
        if not screening_rows:
            return {}
        selected = (selected_rows or screening_rows[:1])[-1]
        run_id = (record.get("run") or {}).get("run_id")
        return load_screening_configuration_evidence(
            run_id, selected.get("row_id"), interval=interval or "15m", session=session,
        )


def _register_figure_callbacks(application: Any) -> None:
    @application.callback(Output("results-price-chart", "children"), Input("results-record", "data"), Input("results-trade-grid", "selectedRows"), Input("results-view", "value"), Input("results-range-nonce", "data"))
    def render_price(record: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, view: str, nonce: Any) -> Any:
        screening_rows = (record or {}).get("screening_rows")
        if not screening_rows:
            return dcc.Graph(figure=_price_figure(record, (selected_rows or [None])[-1], view or "session", nonce), config=_GRAPH_CONFIG)
        try:
            rebuild = rebuild_setting(str(configured_database_path()), record["run"]["run_id"], (selected_rows or screening_rows[:1])[-1]["row_id"])
        except (SettingRebuildRefused, ValueError, OSError) as error:
            return dmc.Alert(str(error), color="yellow", title="Chart not shown")
        if not rebuild.exact:
            return dmc.Alert(rebuild.reason, color="yellow", title="Chart not shown")
        figure = rebuild.portfolio.plot(subplots=["trades", "value", "underwater"], subplot_settings={"trades": {"title": ""}}, template="qf", make_subplots_kwargs={"row_heights": [0.6, 0.2, 0.2], "vertical_spacing": 0.03})
        figure.update_layout(height=560, uirevision=f"{selected_rows}-{nonce}")
        figure.update_yaxes(side="right")
        return dcc.Graph(figure=figure, config=_GRAPH_CONFIG)

    @application.callback(Output("results-evidence-body", "children"), Input("results-record", "data"), Input("results-configuration-evidence", "data"), Input("results-evidence-tab", "value"), Input("results-trade-grid", "selectedRows"))
    def render_evidence(record: dict[str, Any] | None, configuration_evidence: dict[str, Any] | None, tab: str, selected_rows: list[dict[str, Any]] | None):
        record = record or {}
        configuration_evidence = configuration_evidence or {}
        screening_rows = record.get("screening_rows") or []
        if screening_rows:
            if tab == "lineage":
                fields = record.get("lineage") or []
                return html.Div([html.Div([html.Span(item["label"]), html.Strong(item["value"])], className="candidate-evidence-item") for item in fields[:8]], className="results-evidence-list")
            if not configuration_evidence.get("available"):
                return html.Div(configuration_evidence.get("message") or "Select a configuration with retained evidence.", className="results-stage-stop")
            if tab == "trades":
                rows = configuration_evidence.get("trades") or []
                return dag.AgGrid(
                    columnDefs=TRADE_COLUMNS, rowData=rows,
                    defaultColDef={"sortable": True, "resizable": True, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True},
                    dashGridOptions={"pagination": True, "paginationPageSize": 4, "paginationPageSizeSelector": False, "animateRows": False},
                    getRowId="params.data.trade_id", className="ag-theme-quartz-dark results-linked-trade-grid",
                )
            if tab == "equity":
                return dcc.Graph(figure=_configuration_equity_figure(configuration_evidence), config={"displayModeBar": False, "responsive": True})
            return html.Div(f"{tab.replace('_', ' ').title()} was not reached because all configurations failed initial screening.", className="results-stage-stop")
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
        if ctx.triggered_id == "results-sensitivity": return no_update, "equity"
        if ctx.triggered_id == "results-package": return no_update, "lineage"
        return "session", "equity"


def register_results_callbacks(application: Any) -> None:
    _register_record_callbacks(application)
    _register_configuration_callbacks(application)
    _register_figure_callbacks(application)


__all__ = ["register_results_callbacks", "results_layout"]
