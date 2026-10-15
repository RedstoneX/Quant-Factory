"""Production Results workspace in the accepted Quant Factory shell."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash_iconify import DashIconify

from dashboard.overview_projection import configured_database_path
from dashboard.plain_labels import FAILED_TESTING
from dashboard.ui.layout import copy_id, page_header, stat_card
from dashboard.ui.results_settings import display_settings_rows, register_settings_callbacks, settings_columns, settings_heatmap_layout, settings_identity
from dashboard.ui.theme import COLUMN_DEFAULTS, DOWN, UP, grid_options, hide_when_narrow
from orchestration.candidate_setting_rebuild import SettingRebuildRefused, rebuild_setting

from dashboard.results_projection import (
    list_results_runs,
    list_screening_configuration_sessions,
    load_results_record,
    load_screening_configuration_evidence,
)


TRADE_COLUMNS = [
    {"field": "trade_id", "headerName": "Trade", "minWidth": 70, "flex": .6},
    {"field": "direction", "headerName": "Side", "minWidth": 70, "flex": .6},
    {"field": "entry_display", "headerName": "Entry (Eastern)", "minWidth": 130, "flex": 1.4},
    {"field": "exit_display", "headerName": "Exit (Eastern)", "minWidth": 130, "flex": 1.4},
    {"field": "duration", "headerName": "Duration", "minWidth": 80, "flex": .8},
    {"field": "pnl", "headerName": "Profit or loss", "type": "numericColumn", "minWidth": 90, "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": UP}}, {"condition": "params.value < 0", "style": {"color": DOWN}}]}},
    {"field": "outcome", "headerName": "Outcome", "minWidth": 86, "flex": .8},
]
METRIC_COLUMNS = [
    {"field": "total_return", "headerName": "Net return", "type": "numericColumn", "width": 90, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "sharpe_ratio", "headerName": "Sharpe", "type": "numericColumn", "width": 78, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Biggest drop", "type": "numericColumn", "width": 82, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "number_of_trades", "headerName": "Trades", "type": "numericColumn", "width": 72, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}},
    {"field": "win_rate", "headerName": "Win rate", "type": "numericColumn", "width": 76, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "screening_status", "headerName": "Outcome", "width": 134, "valueFormatter": {"function": "params.value === 'screened_out' ? '" + FAILED_TESTING + "' : params.value"}},
]


def _screening_columns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    centred = {"headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}}
    return [{"field": "rank", "headerName": "Rank", "width": 66, "pinned": "left", **centred}, *settings_columns(rows), *METRIC_COLUMNS]

_GRAPH_CONFIG = {"displayModeBar": False, "scrollZoom": True, "responsive": True}


def _empty_figure(message: str, *, height: int = 300) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=.5, y=.5, xref="paper", yref="paper", showarrow=False, font={"size": 12})
    figure.update_xaxes(visible=False); figure.update_yaxes(visible=False)
    figure.update_layout(height=height, margin={"l": 20, "r": 20, "t": 20, "b": 20})
    return figure


def _style(figure: go.Figure, *, height: int) -> go.Figure:
    figure.update_layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 44, "r": 16, "t": 18, "b": 48}, 
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
        return _empty_figure(str(record.get("price_reason") or record.get("message") or "No price bars are saved for this run.").replace("persisted ", "saved "), height=326)
    figure = go.Figure(go.Candlestick(
        x=[row["timestamp"] for row in rows], open=[row["open"] for row in rows], high=[row["high"] for row in rows],
        low=[row["low"] for row in rows], close=[row["close"] for row in rows], name="Price",
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
        return _empty_figure(f"{tab.replace('_', ' ').title()} chart evidence was not saved for this run.", height=168)
    equity, drawdown = record.get("equity") or [], record.get("drawdown") or []
    if not equity:
        return _empty_figure("No equity curve was saved for this run.", height=168)
    figure = go.Figure()
    figure.add_trace(go.Scatter(x=[row.get("timestamp") for row in equity], y=[row.get("value") for row in equity], name="Equity", line={"color": "#4aa8ff", "width": 2}))
    if drawdown:
        figure.add_trace(go.Scatter(x=[row.get("timestamp") for row in drawdown], y=[row.get("drawdown") for row in drawdown], name="Drawdown", yaxis="y2", line={"color": "#ff5f6d", "width": 1.4}))
        figure.update_layout(yaxis2={"overlaying": "y", "side": "right", "showgrid": False})
    return _style(figure, height=168)


def _configuration_equity_figure(evidence: dict[str, Any]) -> go.Figure:
    rows = evidence.get("equity") or []
    if not rows:
        return _empty_figure("No equity curve was saved for this setting.", height=168)
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
        ("Net return", percentage("total_return"), _signed_color(percentage("total_return"))),
        ("Sharpe", "—" if metrics.get("sharpe_ratio") is None else f"{float(metrics['sharpe_ratio']):.2f}", None),
        ("Biggest drop", percentage("max_drawdown", absolute=True), "red.4"),
        ("Trades", f"{int(metrics.get('number_of_trades') or 0):,}", None),
        ("Win rate", percentage("win_rate"), None),
    ]
    return [_stat(label, value, color) for label, value, color in values]


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
    return settings_identity(selected.get("parameters") or {})


def _run_from_search(search: str | None, runs: list[dict[str, Any]]) -> str | None:
    requested = parse_qs((search or "").lstrip("?")).get("run_id", [None])[0]
    if requested and any(row["run_id"] == requested for row in runs):
        return requested
    return next((row["run_id"] for row in runs if row["status"] == "succeeded"), runs[0]["run_id"] if runs else None)


def _stat(label: str, value: str, color: str | None = None) -> dmc.Paper:
    return stat_card(label, value, color=color or "white")


def _signed_color(value: str) -> str | None:
    text = str(value).strip()
    return "teal.4" if text.startswith("+") else "red.4" if text.startswith("-") else None


def _chart_controls(suffix: str = "", *, width: Any = None) -> list[Any]:
    """Bars, view and session pickers; the phone copy (suffix '-m') lives in the filter Drawer."""
    size = {"size": "xs", "allowDeselect": False}
    return [
        dmc.Select(id=f"results-bars{suffix}", data=[{"value": "5m", "label": "5-minute bars"}, {"value": "15m", "label": "15-minute bars"}, {"value": "1D", "label": "Daily bars"}], value="15m", w=width, **size),
        dmc.Select(id=f"results-view{suffix}", data=[{"value": "session", "label": "Full session"}, {"value": "trade", "label": "Selected trade"}, {"value": "morning", "label": "Morning"}], value="session", w=width, **size),
        dmc.Select(id=f"results-session{suffix}", data=[{"value": "all", "label": "All sessions"}], value="all", w=width, **size),
    ]


def results_layout(search: str | None = None) -> html.Div:
    runs = list_results_runs()
    selected = _run_from_search(search, runs)
    choices = [{"value": row["run_id"], "label": f"{row['title']} · {str(row['stage']).replace('_', ' ')} · {str(row['status']).replace('_', ' ')}"} for row in runs]
    menu = dmc.Menu([
        dmc.MenuTarget(dmc.Button("More", variant="default", rightSection=DashIconify(icon="tabler:chevron-down", width=14))),
        dmc.MenuDropdown([
            dmc.MenuItem("Back to the idea", id="results-back-candidates", leftSection=DashIconify(icon="tabler:arrow-left", width=14)),
            dmc.MenuItem("Why it was screened out", id="results-sensitivity"), dmc.MenuItem("Where it came from", id="results-package"),
            dmc.MenuDivider(), dmc.MenuItem("Reset zoom", id="results-reset-range", leftSection=DashIconify(icon="tabler:refresh", width=14)), dmc.MenuItem("Reset layout", id="results-reset-layout"),
        ]),
    ], position="bottom-end")
    header = page_header("Results", "Price chart and trades for one test run", dmc.Badge("Loading", id="results-state"),
                         dmc.Button("Filters", id="results-filters-open", variant="default", hiddenFrom="sm", leftSection=DashIconify(icon="tabler:adjustments", width=14)), menu)
    drawer = dmc.Drawer(dmc.Stack([dmc.Text("Chart options", size="xs", c="dimmed"), *_chart_controls("-m", width="100%")], gap="sm", pb="md"), id="results-filters-drawer", title="Filters", opened=False, position="bottom", size="auto")
    run_picker = dmc.Select(id="results-run", data=choices, value=selected, allowDeselect=False, searchable=True, placeholder="No runs yet", size="xs", w={"base": "100%", "sm": 420})
    identity = dmc.Stack([dmc.Title("Loading", id="results-run-name", order=5, lineClamp=2), dmc.Group(id="results-meta", gap=6)], gap=2)
    toolbar = dmc.Group([run_picker, dmc.Group(_chart_controls(width=150), gap="xs", visibleFrom="sm")], gap="xs", wrap="wrap")
    chart = dmc.Paper(dmc.Stack([
        dmc.Stack([dmc.Title("Price and trades", id="results-chart-title", order=5), dmc.Text("Scroll to zoom; pick a trade to focus on it", id="results-chart-caption", size="xs", c="dimmed")], gap=2),
        dcc.Loading(html.Div(id="results-price-chart"), type="dot"),
        dmc.Group(id="results-assumptions", gap="lg"),
    ], gap="sm"), p="md")
    ledger = dmc.Paper(dmc.Stack([
        dmc.Group([dmc.Stack([dmc.Title("Trades", id="results-ledger-title", order=5), dmc.Text("Pick a trade to see it on the chart", id="results-ledger-subtitle", size="xs", c="dimmed")], gap=2),
                   dmc.TextInput(id="results-trade-search", placeholder="Search trades", size="xs", debounce=True, w={"base": "100%", "sm": 200})], justify="space-between", align="flex-end"),
        dag.AgGrid(id="results-trade-grid", columnDefs=TRADE_COLUMNS, rowData=[], columnSize="responsiveSizeToFit", defaultColDef={**COLUMN_DEFAULTS, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True},
                   dashGridOptions=grid_options("No trades for this run.", rowSelection={"mode": "singleRow", "enableClickSelection": True}, pagination=True, paginationPageSize=10, paginationPageSizeSelector=False, animateRows=False, domLayout="autoHeight"),
                   getRowId="params.data.trade_id || params.data.row_id", eventListeners=hide_when_narrow("exit_display", "duration", "direction")),
        dmc.Text("0 trades", id="results-trade-count", size="xs", c="dimmed"),
    ], gap="sm"), p="md")
    linked = dmc.Paper(dmc.Stack([
        dmc.Title("More detail", order=5),
        dmc.ScrollArea(dmc.Tabs(dmc.TabsList([dmc.TabsTab("Trades", value="trades"), dmc.TabsTab("Equity and drops", value="equity"), dmc.TabsTab("Robustness", value="robustness"), dmc.TabsTab("Rolling test", value="walk_forward"), dmc.TabsTab("Shuffle test", value="monte_carlo"), dmc.TabsTab("Origin", value="lineage")]), id="results-evidence-tab", value="trades"), type="never"),
        html.Div(id="results-evidence-body"),
    ], gap="sm"), p="md")
    stores = [dcc.Store(id="results-record"), dcc.Store(id="results-configuration-evidence"), dcc.Store(id="results-range-nonce", data=0)]
    return html.Div([*stores, drawer, header, dmc.Stack([identity, toolbar, dmc.SimpleGrid(id="results-metrics", cols={"base": 2, "sm": 3}, spacing="sm"), chart, settings_heatmap_layout(), ledger, linked], gap="md", p="lg")])


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
        Output("results-run-name", "children"), Output("results-meta", "children"), Output("results-state", "children"), Output("results-state", "color"),
        Output("results-assumptions", "children"),
        Output("results-chart-title", "children"), Output("results-ledger-title", "children"), Output("results-ledger-subtitle", "children"), Output("results-trade-search", "placeholder"),
        Output("results-bars", "disabled"), Output("results-view", "disabled"), Output("results-reset-range", "disabled"),
        Input("results-record", "data"),
    )
    def render_record(record: dict[str, Any] | None):
        record = record or {}; run = record.get("run") or {}
        title = run.get("title") or "Results unavailable"; run_id = run.get("run_id") or ""
        result_status = str(record.get("result_status") or "").strip().lower()
        screening_rows = record.get("screening_rows") or []
        screened_out = bool(screening_rows) and int(record.get("screened_out_count") or 0) == len(screening_rows)
        failed = str(run.get("status") or "").lower() == "failed"
        state = FAILED_TESTING if screened_out else "Evidence invalid" if result_status == "invalid" else str(run.get("status") or "Unavailable").replace("_", " ").title()
        color = "gray" if screened_out else "red" if failed or result_status == "invalid" else "teal" if state == "Succeeded" else "blue"
        meta = [dmc.Text(f"{run.get('symbol') or 'Unknown market'} · { {'screening': 'first check', 'oos': 'unseen-data test', 'walk_forward': 'rolling test', 'monte_carlo': 'shuffle test'}.get(str(run.get('stage')), str(run.get('stage') or 'unknown').replace('_', ' ')) }", size="xs", c="dimmed"), copy_id(run_id)] if run_id else []
        return (
            title, meta, state, color, [],
            "Price and trades for the chosen setting" if screened_out else "Price and trades",
            f"{len(screening_rows):,} settings tried" if screened_out else "Trades",
            "Pick a setting to see why it failed" if screened_out else "Pick a trade to see it on the chart",
            "Search settings" if screened_out else "Search trades",
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
        data = [{"value": "all", "label": "All sessions"}] + [{"value": day, "label": f"Session · {day}"} for day in sessions]
        return data, "all", False


def _register_configuration_callbacks(application: Any) -> None:
    @application.callback(
        Output("results-chart-caption", "children"), Output("results-metrics", "children"),
        Input("results-record", "data"), Input("results-configuration-evidence", "data"),
    )
    def render_selected_configuration(record: dict[str, Any] | None, configuration_evidence: dict[str, Any] | None):
        record = record or {}; configuration_evidence = configuration_evidence or {}
        screening_rows = record.get("screening_rows") or []
        if screening_rows and configuration_evidence.get("available"):
            row_id = configuration_evidence.get("parameter_row_id")
            selected = next((row for row in screening_rows if row.get("row_id") == row_id), {})
            return _configuration_chart_caption(configuration_evidence, _configuration_identity(selected)), _configuration_metric_cards(configuration_evidence)
        metrics = record.get("metrics") or []
        labels = (
            ("Best net return", "Total Return", True), ("Sharpe on first check", "Sharpe Ratio", False), ("Biggest drop", "Max Drawdown", False),
            ("Trades", "Number Of Trades", False), ("Win rate", "Win Rate", False), ("Profit factor", "Profit Factor", False),
        ) if screening_rows else (
            ("Net return", "Total Return", True), ("Sharpe on unseen data", "Sharpe Ratio", False), ("Biggest drop", "Max Drawdown", False),
            ("Trades", "Number Of Trades", False), ("Win rate", "Win Rate", False), ("Profit factor", "Profit Factor", False),
        )
        cards = [_stat(label, _metric_value(metrics, key), _signed_color(_metric_value(metrics, key)) if signed else "red.4" if "drop" in label else None) for label, key, signed in labels]
        caption = (configuration_evidence.get("message") if screening_rows else None) or str(record.get("price_reason") or "").replace("persisted ", "saved ") or "Scroll to zoom; pick a trade to focus on it"
        return caption, cards

    @application.callback(Output("results-trade-grid", "rowData"), Output("results-trade-grid", "columnDefs"), Output("results-trade-count", "children"), Input("results-record", "data"), Input("results-trade-search", "value"), Input("results-session", "value"))
    def render_trades(record: dict[str, Any] | None, search: str | None, session: str):
        record = record or {}; rows = _display_trades(record, search)
        screening = bool(record.get("screening_rows"))
        if not screening and session and session != "all": rows = [row for row in rows if str(row.get("entry_timestamp") or "").startswith(session)]
        if screening:
            total = int(record.get("screening_count") or 0)
            return display_settings_rows(rows), _screening_columns(rows), f"{total:,} settings tried · all screened out"
        total = int(record.get("trade_count") or 0); bounded = int(record.get("trade_limit") or 0)
        return rows, TRADE_COLUMNS, f"{total:,} trades" + (f" · showing the first {bounded:,}" if total > bounded else "")

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


_RESAMPLE = {"5m": "5min", "15m": "15min", "1D": "1D"}
_DEFAULT_SESSIONS = 20


BG, PANEL, GRID, TEXT, MUTED = "#0d1117", "#161b22", "rgba(255,255,255,0.05)", "#e6edf3", "#7d8590"
UP, DOWN, ACCENT = "#26a69a", "#ef5350", "#58a6ff"


def _tradingview_style(figure: go.Figure) -> None:
    """Approved TradingView-like look (mock build3.py): filled bodies, thin wicks, faint grid, unified hover."""
    figure.update_layout(
        paper_bgcolor=BG, plot_bgcolor=BG, font={"family": "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif", "size": 11, "color": MUTED},
        legend={"orientation": "h", "x": 1, "xanchor": "right", "y": 1.04, "font": {"size": 11, "color": MUTED}, "bgcolor": "rgba(0,0,0,0)"},
        hovermode="x unified", hoverlabel={"bgcolor": PANEL, "bordercolor": "#30363d", "font": {"color": TEXT, "size": 11}},
        margin={"l": 20, "r": 56, "t": 30, "b": 36},
    )
    figure.update_xaxes(gridcolor=GRID, zeroline=False, showline=False, title_text=None, tickfont={"color": MUTED}, showspikes=True, spikemode="across", spikethickness=1, spikedash="dot", spikecolor="#484f58", rangeslider_visible=False)
    figure.update_yaxes(gridcolor=GRID, zeroline=False, showline=False, title_text=None, tickfont={"color": MUTED}, side="right")
    figure.update_traces(selector={"type": "candlestick"}, increasing={"line": {"color": UP, "width": 1}, "fillcolor": UP}, decreasing={"line": {"color": DOWN, "width": 1}, "fillcolor": DOWN}, name="Price", whiskerwidth=0)
    figure.update_traces(selector={"name": "Entry"}, marker={"symbol": "triangle-up", "size": 10, "color": ACCENT, "line": {"width": 1, "color": BG}})
    for trace in figure.data:
        if trace.name and trace.name.startswith("Exit"):
            win = "Profit" in trace.name
            trace.update(marker={"symbol": "triangle-down", "size": 10, "color": UP if win else DOWN, "line": {"width": 1, "color": BG}}, name="Exit · win" if win else "Exit · loss")
    figure.update_traces(selector={"name": "Value"}, line={"color": ACCENT, "width": 1.6}, name="Account value")
    figure.update_traces(selector={"name": "Drawdown"}, line={"color": DOWN, "width": 1.2})
    for shape in figure.layout.shapes:
        if shape.type == "rect":
            shape.update(opacity=0.12, line_width=0)
        elif shape.type == "line":
            shape.update(line={"color": "#30363d", "width": 1, "dash": "dot"})


def window_figure(portfolio: Any, session: str | None, interval: str | None) -> go.Figure:
    """Plot only the selected Eastern session (or the last sessions) of the exact rebuilt portfolio."""
    index = portfolio.wrapper.index
    if session and session != "all":
        start = pd.Timestamp(session, tz="US/Eastern")
        end = start + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    else:
        end = index[-1].tz_convert("US/Eastern")
        start = (end - pd.Timedelta(days=_DEFAULT_SESSIONS)).normalize()
    window = portfolio.loc[start:end]  # vbt Portfolio label indexing
    window = window.resample(_RESAMPLE.get(interval or "15m", "15min"))  # vbt Portfolio.resample
    window = window.replace(wrapper=window.wrapper.replace(index=window.wrapper.index.tz_convert("US/Eastern")))  # one Eastern clock for bars, markers and zones
    figure = window.plot(subplots=["trades", "value", "underwater"], subplot_settings={"trades": {"title": ""}}, template="qf", make_subplots_kwargs={"row_heights": [0.6, 0.2, 0.2], "vertical_spacing": 0.03})
    for trace in figure.data:  # plotly draws wall-clock values, so express every x in Eastern
        if getattr(trace, "x", None) is not None and len(trace.x) and isinstance(trace.x[0], (pd.Timestamp, np.datetime64, str)):
            trace.x = pd.to_datetime(list(trace.x), utc=True).tz_convert("US/Eastern").tz_localize(None)
    for shape in figure.layout.shapes:  # trade zones: same wall-clock as the traces
        if isinstance(shape.x0, pd.Timestamp):
            shape.x0, shape.x1 = shape.x0.tz_convert("US/Eastern").tz_localize(None), shape.x1.tz_convert("US/Eastern").tz_localize(None)
    for trace in figure.data:  # drop the solid value fill, soften the drawdown fill
        if trace.name == "Drawdown":
            trace.fillcolor = "rgba(220,57,18,0.12)"
        elif trace.type == "scatter" and trace.fill is not None:
            trace.fill = "none"
    _tradingview_style(figure)
    for note in figure.layout.annotations:  # small muted panel labels at the left edge, as in the mock
        note.update(text={"Value": "ACCOUNT VALUE", "Underwater": "DRAWDOWN"}.get(note.text, ""), font={"size": 10, "color": MUTED}, x=0.003, xanchor="left")
    breaks = [{"bounds": ["sat", "mon"]}] + ([{"bounds": [16, 9.5], "pattern": "hour"}] if interval != "1D" else [])
    figure.update_xaxes(rangebreaks=breaks, title_text=None)  # Plotly rangebreaks: hide weekends and the overnight gap
    return figure


def _register_figure_callbacks(application: Any) -> None:
    @application.callback(Output("results-price-chart", "children"), Input("results-record", "data"), Input("results-trade-grid", "selectedRows"), Input("results-view", "value"), Input("results-range-nonce", "data"), Input("results-session", "value"), Input("results-bars", "value"))
    def render_price(record: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, view: str, nonce: Any, session: str | None = None, interval: str | None = None) -> Any:
        screening_rows = (record or {}).get("screening_rows")
        if not screening_rows:
            return dcc.Graph(figure=_price_figure(record, (selected_rows or [None])[-1], view or "session", nonce), config=_GRAPH_CONFIG)
        try:
            rebuild = rebuild_setting(str(configured_database_path()), record["run"]["run_id"], (selected_rows or screening_rows[:1])[-1]["row_id"])
        except (SettingRebuildRefused, ValueError, OSError) as error:
            return dmc.Alert(str(error), color="gray", variant="light", title="Chart not shown")
        if not rebuild.exact:
            return dmc.Alert(rebuild.reason, color="gray", variant="light", title="Chart not shown")
        figure = window_figure(rebuild.portfolio, session, interval)
        figure.update_layout(height=560, width=None, autosize=True, uirevision=f"{selected_rows}-{nonce}")
        figure.update_yaxes(side="right")
        return dcc.Graph(figure=figure, config=_GRAPH_CONFIG, style={"height": "560px"})

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
                    defaultColDef={**COLUMN_DEFAULTS, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True},
                    dashGridOptions=grid_options("No trades for this setting.", pagination=True, paginationPageSize=4, paginationPageSizeSelector=False, animateRows=False, domLayout="autoHeight"),
                    getRowId="params.data.trade_id", className="results-linked-trade-grid",
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


def _register_filter_drawer(application: Any) -> None:
    """The phone Drawer holds a copy of the chart pickers; each pair is kept in step with Dash callbacks."""
    application.clientside_callback("(clicks) => true", Output("results-filters-drawer", "opened"), Input("results-filters-open", "n_clicks"), prevent_initial_call=True)
    for name in ("bars", "view", "session"):
        same = "(value, other) => value === other ? window.dash_clientside.no_update : value"
        application.clientside_callback(same, Output(f"results-{name}", "value", allow_duplicate=True), Input(f"results-{name}-m", "value"), State(f"results-{name}", "value"), prevent_initial_call=True)
        application.clientside_callback(same, Output(f"results-{name}-m", "value"), Input(f"results-{name}", "value"), State(f"results-{name}-m", "value"))
    application.clientside_callback("(data, disabled) => [data, disabled]", Output("results-session-m", "data"), Output("results-session-m", "disabled"), Input("results-session", "data"), Input("results-session", "disabled"))


def register_results_callbacks(application: Any) -> None:
    _register_record_callbacks(application)
    _register_configuration_callbacks(application)
    _register_figure_callbacks(application)
    _register_filter_drawer(application)
    register_settings_callbacks(application)


__all__ = ["register_results_callbacks", "results_layout"]
