"""Results: one page per idea, laid out like a strategy tester.

Header and verdict, five unseen-data numbers, a strip of the five tests, and
tabs for the selected test: account value, performance summary, list of
trades, price chart and the settings the costs test tried. Built from Dash,
Dash Mantine, AG Grid, Plotly and pandas only.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash_iconify import DashIconify

from dashboard.formatting import format_money
from dashboard.idea_results_projection import (
    STAGES, TRADE_STAGES, idea_for_run, load_idea, load_period_price, load_stage_detail, load_trade_view,
)
from dashboard.plain_labels import FAILED_TESTING
from dashboard.results_projection import list_results_runs, load_results_record, load_session_price
from dashboard.score_projection import LUCK_OLDER, load_run_scores
from dashboard.ui.layout import page_header, stat_card
from dashboard.ui.results_settings import display_settings_rows, register_settings_callbacks, settings_columns, settings_heatmap_layout
from dashboard.ui.scores import score_cards
from dashboard.ui.theme import COLUMN_DEFAULTS, DOWN, UP, grid_options, hide_when_narrow


MONEY_JS = "params.value == null ? '—' : (params.value < 0 ? '-$' : '$') + Math.abs(params.value).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})"


SCORE_NOTES = (
    "Share of the rolling test periods that made money. Higher is steadier.",
    "Average return per unit of risk across those periods. Above 0 is good.",
    "Whether it still worked with worse costs and shuffled trades.",
    "Chance the result is skill, not luck from trying many settings. Higher is better.",
    "Chance it only looks good because it was picked from many settings. Lower is better.",
)


SCORES_NOTE = "Scores are information, not pass marks — paper trading is the final test."


CHART_UNAVAILABLE = "The price chart for this run is not available right now."
TRADE_MARKER_LIMIT = 300  # more markers than this in view read as a smear, so the chart asks to zoom in
CHART_HELP = "scroll to zoom, drag to move, pick a trade below to centre on it"
RANGE_BUTTONS = [  # Plotly rangeselector, as on a strategy tester
    {"count": 7, "label": "1W", "step": "day", "stepmode": "backward"},
    {"count": 1, "label": "1M", "step": "month", "stepmode": "backward"},
    {"count": 1, "label": "1Y", "step": "year", "stepmode": "backward"},
    {"label": "All", "step": "all"},
]


def settings_tried_line(total: int, screened_out: int) -> str:
    """Count line for the settings table, true to the rows of the run being shown."""
    if total and screened_out == total:
        return f"{total:,} settings tried · all screened out"
    passed = total - screened_out
    return f"{total:,} settings tried · {passed:,} passed" + (f", {screened_out:,} screened out" if screened_out else "")


def _weak_scores(scores: dict[str, Any]) -> bool:
    return (
        scores.get("rolling_status") == "failed" or scores.get("stress_status") == "failed"
        or (scores.get("luck") is not None and scores.get("luck_basis") != LUCK_OLDER and scores["luck"] < 0.5)
        or (scores.get("overfitting") is not None and scores["overfitting"] > 0.5)
    )


def explained_score_cards(scores: dict[str, Any] | None, *, passed: bool) -> list[Any]:
    """Score tiles with a plain line under each; a weak score on a passed idea gets the reminder once."""
    cards = score_cards(scores)
    for card, note in zip(cards, SCORE_NOTES):
        card.children.children.append(dmc.Text(note, size="xs", c="dimmed"))
    if passed and _weak_scores(scores or {}):
        cards.append(dmc.Text(SCORES_NOTE, size="xs", c="yellow.5", style={"gridColumn": "1 / -1"}))
    return cards


TRADE_COLUMNS = [
    {"field": "trade_id", "headerName": "Trade", "minWidth": 70, "flex": .6},
    {"field": "direction", "headerName": "Side", "minWidth": 70, "flex": .6},
    {"field": "entry_display", "headerName": "Entry (Eastern)", "minWidth": 220, "flex": 1.4},
    {"field": "exit_display", "headerName": "Exit (Eastern)", "minWidth": 220, "flex": 1.4},
    {"field": "duration", "headerName": "Duration", "minWidth": 90, "flex": .8},
    {"field": "pnl", "headerName": "Profit or loss", "type": "numericColumn", "minWidth": 120, "flex": 1, "valueFormatter": {"function": MONEY_JS}, "cellStyle": {"styleConditions": [{"condition": "params.value > 0", "style": {"color": UP}}, {"condition": "params.value < 0", "style": {"color": DOWN}}]}},
    {"field": "outcome", "headerName": "Outcome", "minWidth": 86, "flex": .8},
]


METRIC_COLUMNS = [
    {"field": "total_return", "headerName": "Net return", "type": "numericColumn", "width": 90, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "sharpe_ratio", "headerName": "Sharpe", "type": "numericColumn", "width": 78, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Max drawdown", "type": "numericColumn", "width": 82, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "number_of_trades", "headerName": "Trades", "type": "numericColumn", "width": 72, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}},
    {"field": "win_rate", "headerName": "Win rate", "type": "numericColumn", "width": 76, "headerClass": "qf-center-header", "cellStyle": {"textAlign": "center"}, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "screening_status", "headerName": "Outcome", "width": 134, "valueFormatter": {"function": "params.value === 'screened_out' ? '" + FAILED_TESTING + "' : params.value ? params.value.charAt(0).toUpperCase() + params.value.slice(1) : '—'"}},
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


def _equity_figure(rows: list[dict[str, Any]], empty_message: str) -> go.Figure:
    """Equity on top, drawdown below on its own axis (plotly make_subplots); drawdown is value / pandas cummax - 1."""
    if not rows:
        return _empty_figure(empty_message, height=168)
    frame = pd.DataFrame(rows)
    values = frame["value"].astype(float)
    drawdown = (values / values.cummax() - 1) * 100
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[.68, .32], vertical_spacing=.08)
    figure.add_trace(go.Scatter(x=frame["timestamp"], y=values, name="Account value", line={"color": "#4aa8ff", "width": 2}), row=1, col=1)
    figure.add_trace(go.Scatter(x=frame["timestamp"], y=drawdown, name="Drop from peak %", fill="tozeroy", line={"color": "#ff5f6d", "width": 1.2}), row=2, col=1)
    _style(figure, height=320)
    figure.update_xaxes(  # a multi-year axis: Plotly tickformatstops pick the label by zoom level
        tickformat=None, title_text=None,
        tickformatstops=[
            {"dtickrange": [None, 86400000], "value": "%b %d<br>%I:%M %p"},
            {"dtickrange": [86400000, "M1"], "value": "%b %d, %Y"},
            {"dtickrange": ["M1", None], "value": "%b %Y"},
        ],
    )
    figure.update_xaxes(showticklabels=False, title_text=None, row=1, col=1)  # dates only under the drawdown panel
    figure.update_yaxes(tickprefix="$", row=1, col=1)
    figure.update_yaxes(ticksuffix="%", row=2, col=1)
    return figure


def _trade_grid(grid_id: str) -> dag.AgGrid:
    """The one trade table (same columns and format wherever trades are listed)."""
    return dag.AgGrid(id=grid_id, columnDefs=TRADE_COLUMNS, rowData=[], defaultColDef={**COLUMN_DEFAULTS, "filter": True, "suppressHeaderMenuButton": True, "suppressHeaderFilterButton": True},
                      dashGridOptions=grid_options("No trades for this run.", rowSelection={"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}, pagination=True, paginationPageSize=10, paginationPageSizeSelector=False, animateRows=False, domLayout="autoHeight"),
                      getRowId="params.data.trade_id || params.data.row_id")  # phones scroll sideways (column minWidth) rather than lose the running total


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


def _stamp(value: Any) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize(None) if stamp.tzinfo else stamp


def relayout_window(data: dict[str, Any] | None) -> tuple[pd.Timestamp, pd.Timestamp] | str | None:
    """The x-range a Plotly zoom, pan or range button left (relayoutData); 'all' for autorange; None when x did not move."""
    data = data or {}
    if data.get("xaxis.autorange"):
        return "all"
    start, end = data.get("xaxis.range[0]"), data.get("xaxis.range[1]")
    if start is None and isinstance(data.get("xaxis.range"), list):
        start, end = data["xaxis.range"][:2]
    return (_stamp(start), _stamp(end)) if start is not None and end is not None else None


def trades_in(trades: list[dict[str, Any]], first: Any, last: Any) -> list[dict[str, Any]]:
    """Trades whose entry falls between two times."""
    start, end = _stamp(first), _stamp(last)
    return [trade for trade in trades if trade.get("entry_timestamp") and start <= _stamp(trade["entry_timestamp"]) <= end]


def trades_figure(price: list[dict[str, Any]], trades: list[dict[str, Any]], selected: dict[str, Any] | None, message: str | None, nonce: Any,
                  window: tuple[Any, Any] | None = None) -> go.Figure:
    """Saved bars as Plotly candles opened on `window`, with trade markers only when few enough are in view; a picked trade is outlined and zoomed to."""
    if not price:
        return _empty_figure(str(message or "No price bars were saved for this run.").replace("persisted ", "saved "), height=560)
    first, last = str(price[0]["timestamp"]), str(price[-1]["timestamp"])
    figure = go.Figure(go.Candlestick(
        x=[row["timestamp"] for row in price], open=[row["open"] for row in price], high=[row["high"] for row in price],
        low=[row["low"] for row in price], close=[row["close"] for row in price], name="Price",
    ))
    shown = [trade for trade in trades if trade.get("entry_timestamp") and first[:10] <= str(trade["entry_timestamp"])[:10] <= last[:10]]
    if len(trades_in(shown, *(window or (first, last)))) > TRADE_MARKER_LIMIT:
        shown = []
    entries = [trade for trade in shown if trade.get("entry_price") is not None]
    if entries:
        figure.add_trace(go.Scatter(
            x=[trade["entry_timestamp"] for trade in entries], y=[trade["entry_price"] for trade in entries], mode="markers", name="Entry",
            text=[f"Trade {trade['trade_id']} · {trade['direction']}" for trade in entries], hovertemplate="%{text}<br>%{y}<extra></extra>",
        ))
    exited = [trade for trade in shown if trade.get("exit_timestamp") and trade.get("exit_price") is not None]
    for label, group in (("Exit Profit", [t for t in exited if (t.get("pnl") or 0) > 0]), ("Exit Loss", [t for t in exited if (t.get("pnl") or 0) <= 0])):
        if group:
            figure.add_trace(go.Scatter(
                x=[trade["exit_timestamp"] for trade in group], y=[trade["exit_price"] for trade in group], mode="markers", name=label,
                text=[f"Trade {trade['trade_id']} · {trade['outcome']}" for trade in group], hovertemplate="%{text}<br>%{y}<extra></extra>",
            ))
    _tradingview_style(figure)
    figure.update_xaxes(rangeselector={"buttons": RANGE_BUTTONS, "x": 0, "y": 1.02, "yanchor": "bottom", "bgcolor": PANEL, "activecolor": "#30363d",
                                       "bordercolor": "#30363d", "borderwidth": 1, "font": {"color": TEXT, "size": 11}})
    figure.update_yaxes(fixedrange=True)  # zoom and drag move time only; prices refit to the bars in view
    if window:
        figure.update_xaxes(range=[_stamp(window[0]), _stamp(window[1])])
    revision = str(nonce)
    if selected and selected.get("entry_timestamp"):
        start = pd.Timestamp(selected["entry_timestamp"]); end = pd.Timestamp(selected.get("exit_timestamp") or selected["entry_timestamp"])
        figure.add_vrect(x0=start, x1=end, fillcolor=ACCENT, opacity=0.12, line_width=0)
        pad = max((end - start) / 2, pd.Timedelta(minutes=45))
        figure.update_xaxes(range=[start - pad, end + pad])  # Plotly axis range: focus the picked trade
    figure.update_xaxes(rangebreaks=[{"bounds": ["sat", "mon"]}])  # Plotly rangebreaks: hide weekends
    figure.update_layout(height=560, uirevision=revision, dragmode="pan")
    return figure


def _chart_session(session: str | None, selected: dict[str, Any] | None, trades: list[dict[str, Any]]) -> str | None:
    """The Eastern day to draw: the picked trade's day, else the chosen session, else the last traded day."""
    if selected and selected.get("entry_timestamp"):
        return str(selected["entry_timestamp"])[:10]
    if session and session != "all":
        return session
    days = [str(trade["entry_timestamp"])[:10] for trade in trades if trade.get("entry_timestamp")]
    return max(days) if days else None



TOP_NOTES = {
    "Net profit": "What it made on data it never saw.",
    "Max drawdown": "Biggest drop from a high point.",
    "Trades": "Trades it took on that data.",
    "Win rate": "Share of trades that made money.",
    "Profit factor": "Money won ÷ money lost; above 1 makes money.",
}
SUMMARY_ROWS = (
    ("net_profit", "Net profit"), ("gross_profit", "Money won"), ("gross_loss", "Money lost"), ("profit_factor", "Profit factor"),
    ("max_drawdown", "Biggest drop from a high"), ("total_trades", "Trades"), ("win_rate", "Win rate"), ("avg_trade", "Average trade"),
    ("avg_win", "Average win"), ("avg_loss", "Average loss"), ("largest_win", "Largest win"), ("largest_loss", "Largest loss"),
    ("avg_bars_in_trade", "Average bars in a trade"), ("commission_paid", "Commission paid"),
)
MONEY_KEYS = {"net_profit", "gross_profit", "gross_loss", "max_drawdown", "avg_trade", "avg_win", "avg_loss", "largest_win", "largest_loss", "commission_paid"}
SUMMARY_MISSING = "Saved when the idea is next tested."
BAR_WORDS = {"5m": "5-minute", "15m": "15-minute", "1h": "hourly", "1D": "daily", "1W": "weekly", "1M": "monthly"}
PERIOD_COLUMNS = [
    {"field": "period", "headerName": "Test period", "minWidth": 180, "flex": 1.4},
    {"field": "result", "headerName": "Result", "minWidth": 80, "flex": .6, "narrow": False},
    {"field": "trades", "headerName": "Trades", "minWidth": 70, "flex": .5, "narrow": False},
    {"field": "net_return", "headerName": "Net return", "minWidth": 90, "flex": .6, "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2) + '%'"}},
    {"field": "note", "headerName": "Why", "minWidth": 260, "flex": 2, "wrapText": True, "autoHeight": True, "narrow": False},
]
CHECK_COLUMNS = [
    {"field": "check", "headerName": "Check", "minWidth": 150, "flex": 2, "wrapText": True, "autoHeight": True},
    {"field": "result", "headerName": "Result", "minWidth": 70, "flex": .6},
    {"field": "measured", "headerName": "Measured", "minWidth": 90, "flex": .7, },
    {"field": "needed", "headerName": "Needed", "minWidth": 80, "flex": .6, "narrow": False},
]
TRADE_COLUMNS = [*TRADE_COLUMNS[:5], {**TRADE_COLUMNS[5], "minWidth": 100},
                 {**TRADE_COLUMNS[5], "field": "cum_pnl", "headerName": "Running total"}, TRADE_COLUMNS[6]]


def _query(search: str | None) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs((search or "").lstrip("?")).items() if values}


def _resolve(search: str | None) -> tuple[dict[str, Any], str]:
    """The idea a URL names (?candidate_id=, or an old ?run_id= link opened on its idea with that test selected)."""
    query = _query(search)
    candidate_id, run_id, test = query.get("candidate_id"), query.get("run_id"), query.get("test")
    if run_id:
        found = idea_for_run(run_id) or {}
        candidate_id = candidate_id or found.get("candidate_id")
        test = test or found.get("stage")
    if not candidate_id and not run_id:
        latest = next((row for row in list_results_runs() if row.get("candidate_id")), None)
        candidate_id = (latest or {}).get("candidate_id")
    idea = load_idea(candidate_id, run_id=run_id)
    stages = [stage for stage, _label in STAGES]
    if test not in stages:
        test = idea.get("open_test") or "screening"  # the furthest test the idea reached that saved a result
    return idea, test


def _signed(value: float | None) -> str | None:
    return None if value is None else "teal.4" if value > 0 else "red.4" if value < 0 else None


def top_line(idea: dict[str, Any]) -> list[Any]:
    """Five unseen-data numbers, each with one plain line (Net profit from the saved summary, else the sum of its trades)."""
    run_id = ((idea.get("runs") or {}).get("oos") or {}).get("run_id")
    record = load_results_record(run_id) if run_id else {}
    metrics = {item["label"]: item["value"] for item in record.get("metrics") or []}
    view = load_trade_view(idea, "oos") if run_id else {}
    saved = (((view.get("performance") or {}).get("performance") or {}).get("all") or {}).get("net_profit")
    trades = view.get("trades") or []
    complete = trades and len(trades) == int(view.get("trade_count") or 0)
    net = saved if saved is not None else float(pd.Series([t.get("pnl") for t in trades], dtype="float64").sum()) if complete else None
    percent = metrics.get("Total Return")
    values = [
        ("Net profit", f"{format_money(net)} ({percent or '—'})" if net is not None else percent or "—", _signed(net)),
        ("Max drawdown", str(metrics.get("Max Drawdown", "—")).lstrip("-"), "red.4"),
        ("Trades", metrics.get("Number Of Trades", "—"), None),
        ("Win rate", metrics.get("Win Rate", "—"), None),
        ("Profit factor", metrics.get("Profit Factor", "—"), None),
    ]
    return [stat_card(label, value, TOP_NOTES[label], color=color or "white") for label, value, color in values]


def _test_tab(test: dict[str, Any]) -> dmc.TabsTab:
    return dmc.TabsTab(dmc.Stack([
        dmc.Text(test["label"], size="sm", fw=600),
        dmc.Badge(test["status_text"], color=test["color"], size="xs", variant="light"),
        dmc.Text(test["line"], size="xs", c="dimmed", style={"whiteSpace": "normal"}),
    ], gap=4, align="flex-start"), value=test["stage"], className="results-test-card")


def _panel(*children: Any) -> dmc.Paper:
    return dmc.Paper(dmc.Stack(list(children), gap="sm"), p={"base": "xs", "sm": "md"})


def _tabs() -> dmc.Tabs:
    names = (("overview", "Overview"), ("chart", "Price chart and trades"), ("summary", "Performance summary"), ("settings", "Settings tried"))
    graph = {"displayModeBar": False, "responsive": True}
    panels = {
        "overview": [dmc.Text("Account value over the whole period, with the drop from its peak below.", id="results-equity-note", size="xs", c="dimmed"),
                     dcc.Loading(dcc.Graph(id="results-equity", config=graph), type="dot")],
        "summary": [html.Div(id="results-summary")],
        "chart": [dmc.Text("", id="results-chart-caption", size="xs", c="dimmed"),
                  dcc.Loading(dcc.Graph(id="results-price-chart", config=_GRAPH_CONFIG, style={"height": "560px"}), type="dot"),
                  _trade_grid("results-trade-grid"), dmc.Text("", id="results-trade-count", size="xs", c="dimmed")],
        "settings": [dmc.Text("", id="results-settings-count", size="xs", c="dimmed"),
                     dag.AgGrid(id="results-settings-grid", rowData=[], columnDefs=[], defaultColDef={**COLUMN_DEFAULTS, "suppressHeaderMenuButton": True},
                                dashGridOptions=grid_options("The costs test saved no settings.", rowSelection={"mode": "singleRow", "checkboxes": False, "enableClickSelection": True}, domLayout="autoHeight", animateRows=False)),
                     dmc.Text("Pick a setting to see its trades, account value and chart.", size="xs", c="dimmed"), settings_heatmap_layout()],
    }
    return dmc.Tabs([
        dmc.ScrollArea(dmc.TabsList([dmc.TabsTab(label, value=value) for value, label in names]), type="never"),
        *[dmc.TabsPanel(dmc.Stack(panels[value], gap="sm", pt="sm"), value=value) for value, _label in names],
    ], id="results-tab", value="overview")


def results_layout(search: str | None = None) -> html.Div:
    idea, test = _resolve(search)
    if not idea.get("available"):
        return html.Div([dcc.Store(id="results-record", data=idea), page_header("Results", idea.get("message") or "No saved results yet."),
                         dmc.Text("Pick an idea on the Ideas page and open its results.", size="sm", c="dimmed", p="lg")])
    menu = dmc.Menu([dmc.MenuTarget(dmc.Button("More", variant="default", rightSection=DashIconify(icon="tabler:chevron-down", width=14))),
                     dmc.MenuDropdown([dmc.MenuItem("Back to the idea", id="results-back-candidates", leftSection=DashIconify(icon="tabler:arrow-left", width=14))])], position="bottom-end")
    verdict = dmc.Badge(idea["verdict"], color=idea["verdict_color"], size="lg", variant="light", style={"height": "auto", "maxWidth": "100%", "textTransform": "none"},
                        styles={"label": {"whiteSpace": "normal", "overflow": "visible", "textOverflow": "clip"}})
    header = page_header(idea["title"], f"{idea['symbol']} · every test this idea went through", verdict, menu)
    unseen = next((item for item in idea["tests"] if item["stage"] == "oos"), {})
    numbers = [dmc.Text("On data it never saw", size="xs", c="dimmed", fw=600), dmc.SimpleGrid(top_line(idea), cols={"base": 2, "sm": 5}, spacing="sm")] \
        if unseen.get("run_id") and unseen.get("has_result", True) else [dmc.Text(f"On data it never saw: {unseen.get('line') or 'not tested yet.'}", size="sm", c="dimmed")]
    strip = dmc.Tabs(dmc.TabsList([_test_tab(item) for item in idea["tests"]], className="results-test-strip"), id="results-test", value=test, variant="pills")
    stores = [dcc.Store(id="results-record", data=idea), dcc.Store(id="results-view"), dcc.Store(id="results-setting")]
    body = dmc.Stack([
        *numbers,
        dmc.Text("The five tests — pick one to see its detail", size="xs", c="dimmed", fw=600),
        strip,
        html.Div(_panel(dmc.Title("", id="results-view-label", order=5), _tabs()), id="results-trade-panel"),
        html.Div(id="results-score-panel", style={"display": "none"}),
    ], gap="md", p={"base": "sm", "sm": "lg"})
    return html.Div([*stores, header, body])


def _grid(grid_id: str, rows: list[dict[str, Any]], columns: list[dict[str, Any]], empty: str) -> dag.AgGrid:
    narrow = [column["field"] for column in columns if column.get("narrow") is False]
    columns = [{key: value for key, value in column.items() if key != "narrow"} for column in columns]
    return dag.AgGrid(id=grid_id, rowData=rows, columnDefs=columns, defaultColDef={**COLUMN_DEFAULTS, "suppressHeaderMenuButton": True, "cellStyle": {"lineHeight": "1.4", "paddingTop": "8px", "paddingBottom": "8px"}},
                      dashGridOptions=grid_options(empty, domLayout="autoHeight", animateRows=False), eventListeners=hide_when_narrow(*narrow) if narrow else {})


def score_detail(idea: dict[str, Any], stage: str) -> list[Any]:
    """The rolling, stress or shuffle test's own detail: the idea's score tiles, then its periods, checks or reasons."""
    test = next(item for item in idea["tests"] if item["stage"] == stage)
    detail = load_stage_detail(idea, stage)
    passed = all(item["status"] == "passed" for item in idea["tests"] if item["stage"] in TRADE_STAGES)
    run_id = next((item["run_id"] for item in idea["tests"] if item["run_id"]), None)
    parts: list[Any] = [
        dmc.Group([dmc.Title(test["label"], order=5), dmc.Badge(test["status_text"], color=test["color"], variant="light")], gap="xs"),
        dmc.Text(test["line"], size="sm"),
        dmc.Text("This test makes no trades of its own; it scores the idea. The scores:", size="xs", c="dimmed"),
        dmc.SimpleGrid(explained_score_cards(load_run_scores(run_id), passed=passed), cols={"base": 2, "sm": 5}, spacing="sm"),
    ]
    if detail["periods"]:
        parts += [dmc.Text("Each rolling period: the idea picked its setting on earlier data, then traded the next stretch.", size="xs", c="dimmed"),
                  _grid("results-period-grid", detail["periods"], PERIOD_COLUMNS, "No periods were saved.")]
    if detail["checks"]:
        parts += [dmc.Text("Each check: what was measured and what was needed.", size="xs", c="dimmed"),
                  _grid("results-check-grid", detail["checks"], CHECK_COLUMNS, "No checks were saved.")]
    parts += [dmc.List([dmc.ListItem(reason) for reason in detail["reasons"]], size="sm")] if detail["reasons"] else []
    if not test["run_id"]:
        parts = parts[:2]
    return [_panel(*parts)]


def performance_table(view: dict[str, Any]) -> Any:
    """All / Long / Short table from the run's saved performance summary; never computed here."""
    document = view.get("performance")
    if not document:
        return dmc.Text(SUMMARY_MISSING, size="sm", c="dimmed")
    performance = document.get("performance") or {}

    def shown(key: str, value: Any) -> str:
        if value is None:
            return "—"
        if key in MONEY_KEYS:
            return format_money(value)
        if key == "win_rate":
            number = float(value)
            return f"{number * 100 if abs(number) <= 1 else number:.2f}%"
        if key == "total_trades":
            return f"{int(value):,}"
        return f"{float(value):.2f}"

    rows = [{"measure": label, **{side: shown(key, (performance.get(side) or {}).get(key)) for side in ("all", "long", "short")}} for key, label in SUMMARY_ROWS]
    columns = [{"field": "measure", "headerName": "", "minWidth": 150, "flex": 1.4}] + [
        {"field": side, "headerName": side.title(), "minWidth": 80, "flex": 1, "type": "rightAligned"} for side in ("all", "long", "short")]
    return _grid("results-summary-grid", rows, columns, SUMMARY_MISSING)


def _register_view_callbacks(application: Any) -> None:
    @application.callback(Output("results-view", "data"), Input("results-test", "value"), Input("results-setting", "data"), State("results-record", "data"))
    def load_view(test: str | None, row_id: str | None, idea: dict[str, Any] | None) -> dict[str, Any]:
        return load_trade_view(idea, test, row_id) if test in TRADE_STAGES else {}

    @application.callback(
        Output("results-trade-panel", "style"), Output("results-score-panel", "style"), Output("results-score-panel", "children"),
        Input("results-test", "value"), State("results-record", "data"),
    )
    def choose_panel(test: str | None, idea: dict[str, Any] | None):
        if test in TRADE_STAGES:
            return {}, {"display": "none"}, []
        return {"display": "none"}, {}, score_detail(idea or {}, test)

    @application.callback(
        Output("results-view-label", "children"), Output("results-equity", "figure"), Output("results-equity-note", "children"), Output("results-summary", "children"),
        Output("results-trade-grid", "rowData"), Output("results-trade-count", "children"), Output("results-trade-grid", "selectedRows"),
        Input("results-view", "data"),
    )
    def render_view(view: dict[str, Any] | None):
        view = view or {}
        if not view.get("available"):
            message = view.get("message") or "Pick a test above."
            return message, _empty_figure(message, height=320), "", dmc.Text(message, size="sm", c="dimmed"), [], "", []
        note = "Account value over the whole period, with the drop from its peak below."
        if view.get("equity_from_trades"):
            note += " No curve was saved, so it is built from the saved trades: starting cash plus profit or loss at each exit."
        count = int(view.get("trade_count") or 0)
        return (view.get("label"), _equity_figure(view.get("equity") or [], "No account value was saved for this test."), note,
                performance_table(view), (view.get("trades") or [])[::-1], f"{count:,} trades · pick one to centre the chart on it", [])  # a new test starts on its whole period

    @application.callback(
        Output("results-settings-grid", "rowData"), Output("results-settings-grid", "columnDefs"), Output("results-settings-count", "children"),
        Input("results-record", "data"),
    )
    def render_settings(idea: dict[str, Any] | None):
        rows = (idea or {}).get("screening_rows") or []
        return display_settings_rows(rows), _screening_columns(rows), settings_tried_line(len(rows), int((idea or {}).get("screened_out_count") or 0))

    @application.callback(Output("results-setting", "data"), Output("results-test", "value"), Output("results-tab", "value", allow_duplicate=True),
                          Input("results-settings-grid", "selectedRows"), prevent_initial_call=True)
    def pick_setting(rows: list[dict[str, Any]] | None):
        if not rows:
            return no_update, no_update, no_update
        return rows[-1].get("row_id"), "screening", "overview"


def _register_chart_callbacks(application: Any) -> None:
    @application.callback(
        Output("results-price-chart", "figure"), Output("results-chart-caption", "children"),
        Input("results-view", "data"), Input("results-trade-grid", "selectedRows"), Input("results-price-chart", "relayoutData"),
        Input("results-tab", "value"),
    )
    def render_price(view: dict[str, Any] | None, selected_rows: list[dict[str, Any]] | None, relayout: dict[str, Any] | None, tab: str | None):
        """Opens on the latest month; a zoom, pan or range button (relayoutData) reloads the bars in view at the finest size that fits.

        Drawn only while its tab is open: Plotly cannot lay out a chart inside a hidden panel.
        """
        if tab != "chart":
            return no_update, no_update
        view = view or {}
        if not view.get("available"):
            return _empty_figure(view.get("message") or CHART_UNAVAILABLE, height=560), ""
        trades = view.get("trades") or []
        selected = (selected_rows or [None])[-1]
        revision = f"{view.get('run_id')}-{view.get('row_id')}-{(selected or {}).get('trade_id', 'latest')}"  # Plotly uirevision keeps the user's zoom
        window = relayout_window(relayout) if ctx.triggered_id == "results-price-chart" else None
        if ctx.triggered_id == "results-price-chart" and window is None:
            return no_update, no_update
        revision += "-all" if window == "all" else ""  # 'All' ends on the last saved bar, not Plotly's padded autorange
        if ctx.triggered_id == "results-trade-grid" and selected and selected.get("entry_timestamp"):  # a picked trade: its own day in 5-minute bars
            bars = load_session_price(view.get("price_run_id"), _chart_session(None, selected, trades), interval="5m")
            caption = f"Trade {selected.get('trade_id')} · {selected.get('direction')} · in {selected.get('entry_display')} · out {selected.get('exit_display')} · {format_money(selected.get('pnl'))}"
            return trades_figure(bars["price"], trades, selected, bars["reason"], revision), caption
        whole = load_period_price(view.get("price_run_id"), view.get("period"))
        if not whole["price"]:
            return trades_figure([], trades, None, whole["reason"] or CHART_UNAVAILABLE, revision), ""
        first, last = _stamp(whole["price"][0]["timestamp"]), _stamp(whole["price"][-1]["timestamp"])
        start, end = (first, last) if window == "all" else window or (last - pd.DateOffset(months=1), last)
        start, end = max(_stamp(start), first), min(_stamp(end), last)
        price = whole if (start, end) == (first, last) else load_period_price(view.get("price_run_id"), [start.date().isoformat(), end.date().isoformat()])
        count = len(trades_in(trades, start, end))
        caption = (f"{BAR_WORDS.get(price['interval'], price['interval']).capitalize()} bars · {count:,} trades in view"
                   + (" · zoom in to see trades" if count > TRADE_MARKER_LIMIT else "") + f" · {CHART_HELP}") if price["price"] else ""
        return trades_figure(price["price"], trades, selected if window else None, price["reason"] or CHART_UNAVAILABLE, revision, window=(start, end)), caption


def register_results_callbacks(application: Any) -> None:
    _register_view_callbacks(application)
    _register_chart_callbacks(application)
    register_settings_callbacks(application)


__all__ = ["register_results_callbacks", "results_layout", "top_line", "score_detail", "performance_table"]
