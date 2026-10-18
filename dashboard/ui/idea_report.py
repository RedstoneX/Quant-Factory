"""Idea report: one dark page per idea. Thin Dash Mantine + Plotly + AG Grid layer over idea_report_projection."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html
from plotly.subplots import make_subplots

from dashboard.idea_report_projection import NOT_SAVED, STATUS_TONE, load_report
from dashboard.ui.results import TRADE_COLUMNS

FONT_URL = "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
SANS, MONO = "Geist, ui-sans-serif, -apple-system, sans-serif", "'Geist Mono', ui-monospace, monospace"
BG, PANEL, INNER, LINE, TEXT, MUTED, FAINT = "#08090B", "#0F1114", "#131519", "#1F2228", "#ECEDEE", "#9BA1AB", "#6B7280"
INDIGO, GREEN, AMBER, RED, HOLD = "#818CF8", "#5EEAB0", "#F5B841", "#F2545B", "#4B5160"
TONE = {"green": GREEN, "amber": AMBER, "red": RED, "grey": MUTED}
REPORT_THEME = {"fontFamily": SANS, "headings": {"fontFamily": SANS}, "colors": {"dark": [TEXT, "#C4C8CF", MUTED, FAINT, "#262930", "#1A1C21", PANEL, BG, "#050506", "#050506"]},
                "primaryColor": "indigo", "defaultRadius": "md", "black": BG, "white": TEXT}
GRID_THEME = {"function": "themeQuartz.withParams(" + json.dumps({
    "browserColorScheme": "dark", "backgroundColor": PANEL, "foregroundColor": TEXT, "chromeBackgroundColor": PANEL, "headerBackgroundColor": PANEL,
    "headerTextColor": FAINT, "borderColor": "#16181C", "accentColor": INDIGO, "oddRowBackgroundColor": PANEL, "fontFamily": SANS, "fontSize": 13,
    "wrapperBorder": False, "rowHeight": 40, "headerHeight": 40}) + ")"}
MONEY_KEYS = {"avg_trade": "Average trade"}


def _panel(title: str, note: str, *children: Any) -> dmc.Paper:
    return dmc.Paper([
        dmc.Group([dmc.Text(title, fw=600, size="md"), dmc.Text(note, size="xs", c=FAINT)], justify="space-between", align="baseline", gap="xs"),
        *children], p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0}, className="idea-report-panel")


def _figure(figure: go.Figure, height: int) -> dcc.Graph:
    figure.update_layout(height=height, margin=dict(l=44, r=8, t=8, b=24), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(family=SANS, color=MUTED, size=11), showlegend=False, hovermode="x unified")
    figure.update_xaxes(gridcolor="#16181C", zeroline=False, showline=False)
    figure.update_yaxes(gridcolor="#16181C", zeroline=False, showline=False)
    return dcc.Graph(figure=figure, config={"displayModeBar": False, "responsive": True}, style={"width": "100%", "height": f"{height}px"})


def _legend() -> dmc.Group:
    def key(color: str, text: str) -> dmc.Group:
        return dmc.Group([html.Span(style={"width": 12, "height": 2, "background": color}), dmc.Text(text, size="xs", c=MUTED)], gap=6)
    return dmc.Group([key(INDIGO, "Built on"), key(GREEN, "Never seen"), key(HOLD, "Buy and hold")], gap="md")


def hero(report: dict[str, Any]) -> dmc.Paper:
    data = report["hero"]
    if data["kind"] == "never_ran":  # no empty chart frame: a plain grey card with the reason and the fix
        return dmc.Paper([
            dmc.Text("No account-value chart for this idea", fw=600, size="md"),
            dmc.Text(data["reason"], size="sm", c=TEXT),
            dmc.Text(f"What to fix: {data['fix']}", size="sm", c=MUTED),
        ], p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minHeight": 160}, className="idea-report-never-ran")
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.04)
    if len(data["hold"]):
        figure.add_trace(go.Scatter(x=data["hold"].index, y=data["hold"], mode="lines", line=dict(color=HOLD, width=1.4), name="Buy and hold"), row=1, col=1)
    for key, color, name in (("built", INDIGO, "Built on"), ("unseen", GREEN, "Never seen")):
        if len(data[key]):
            figure.add_trace(go.Scatter(x=data[key].index, y=data[key], mode="lines", line=dict(color=color, width=2), name=name), row=1, col=1)
    drop = data["drawdown"]
    figure.add_trace(go.Scatter(x=drop.index, y=drop, mode="lines", line=dict(color=RED, width=1.2), fill="tozeroy", fillcolor="rgba(242,84,91,0.25)", name="Below peak %"), row=2, col=1)
    figure.update_yaxes(tickprefix="$", row=1, col=1, autorange=True, rangemode="normal")
    figure.update_yaxes(ticksuffix="%", row=2, col=1)
    note = [] if not data["unseen_label_note"] else [dmc.Text(f"Unseen period: {data['unseen_label_note']}", size="xs", c=FAINT)]
    worst = f"Worst drop {drop.min():.1f}%" if len(drop) else ""
    return dmc.Paper([dmc.Group([dmc.Text("Account value", fw=600, size="md"), _legend()], justify="space-between", gap="xs"),
                      _figure(figure, 380), dmc.Text(worst, size="xs", c=RED, ff=MONO), *note],
                     p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0}, className="idea-report-hero")


def _kpi(label: str, value: str, color: str = TEXT) -> html.Div:
    return html.Div([dmc.Text(label, size="xs", c=FAINT), dmc.Text(value, size="xl", fw=500, c=color, ff=MONO)], style={"padding": "10px 0", "borderBottom": "1px solid #16181C"})


def kpis(report: dict[str, Any]) -> dmc.Paper:
    perf = report["performance"]
    items = []
    if report["unseen_return"] and not report["unseen_return"].startswith("Not"):
        items.append(("Return, unseen data", report["unseen_return"], GREEN if report["unseen_return"].startswith("+") else RED))
    for key, label, fmt in (("max_drawdown", "Worst drop", lambda v: f"{float(v) * 100:.1f}%"), ("profit_factor", "Profit factor", lambda v: f"{float(v):.2f}"),
                            ("win_rate", "Win rate", lambda v: f"{float(v) * 100:.0f}%"), ("avg_trade", "Average trade", lambda v: f"{'-' if float(v) < 0 else '+'}${abs(float(v)):,.2f}"),
                            ("total_trades", "Trades", lambda v: f"{int(v):,}")):
        if perf.get(key) is not None:
            items.append((label, fmt(perf[key]), TEXT))
    if report["sharpe"] is not None:
        items.insert(1, ("Sharpe after costs", f"{float(report['sharpe']):.2f}", TEXT))
    body = [_kpi(*item) for item in items] or [dmc.Text(NOT_SAVED, size="sm", c=FAINT)]
    return dmc.Paper(body, px="lg", py="xs", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0}, className="idea-report-kpis")


def test_card(index: int, test: dict[str, Any]) -> dmc.Paper:
    tone = TONE[STATUS_TONE[test["status"]]]
    bar: list[Any] = []
    if test["fraction"] is not None:
        bar = [html.Div([dmc.Progress(value=max(0, min(1, test["fraction"])) * 100, color=tone, size=6),
                         *([html.Div(style={"position": "absolute", "top": -4, "left": f"{test['pass_line'] * 100:.1f}%", "width": 2, "height": 14, "background": TEXT})] if test["line"] is not None else [])],
                        style={"position": "relative"})]
    saved_note = []
    if test["stage"] == "walk_forward" and test["run_id"] and not test["detail"]["periods"]:
        saved_note = [dmc.Text("Per-window numbers: " + NOT_SAVED.lower(), size="xs", c=FAINT)]
    return dmc.Paper([
        dmc.Group([dmc.Text(f"{index} · {test['label']}", fw=500, size="sm"), dmc.Badge(test["status"], color=TONE[STATUS_TONE[test["status"]]], variant="light", size="sm")], justify="space-between", gap="xs"),
        dmc.Text(test["value"], size="lg", ff=MONO), *bar, dmc.Text(test["line"], size="xs", c=MUTED), *saved_note,
    ], p="md", radius="md", bg=INNER, style={"border": f"1px solid {LINE}"}, className="idea-report-test")


def tests_panel(report: dict[str, Any]) -> dmc.Paper:
    return _panel("The five tests", "White tick = pass line · bar = this idea",
                  dmc.SimpleGrid([test_card(i, t) for i, t in enumerate(report["tests"], 1)], cols={"base": 1, "sm": 2, "lg": 5}, spacing="sm", mt="sm"))


def settings_panel(report: dict[str, Any]) -> dmc.Paper:
    grid = report["grid"]
    if not grid:
        return _panel("Every setting tried", "Sharpe after costs", dmc.Text("No settings were saved for this idea.", size="sm", c=FAINT, mt="sm"))
    figure = go.Figure(go.Heatmap(z=grid["values"], x=grid["columns"], y=grid["rows"], colorscale=[[0, RED], [0.5, "#1A1C21"], [1, GREEN]], zmid=0, showscale=False,
                                  xgap=3, ygap=3, hovertemplate=f"{grid['down']} %{{y}}<br>{grid['across'] or ''} %{{x}}<br>Sharpe %{{z:.2f}}<extra></extra>"))
    if grid["chosen"]:
        figure.add_trace(go.Scatter(x=[grid["chosen"][1]], y=[grid["chosen"][0]], mode="markers", marker=dict(symbol="square-open", size=26, color=TEXT, line=dict(width=2)), hoverinfo="skip"))
    figure.update_xaxes(type="category", title=grid["across"].replace("_", " "))
    figure.update_yaxes(type="category", title=grid["down"].replace("_", " "))
    return _panel("Every setting tried", "Sharpe after costs · white outline = chosen", _figure(figure, 300), dmc.Text(f"{grid['count']:,} settings tried.", size="xs", c=MUTED))


def luck_panel(report: dict[str, Any]) -> dmc.Paper:
    test = next(t for t in report["tests"] if t["stage"] == "monte_carlo")
    checks = test["detail"]["checks"]
    rows = [dmc.Group([dmc.Text(c["check"], size="sm"), dmc.Text(f"{c['measured']} · needs {c['needed']}", size="sm", ff=MONO, c=MUTED)], justify="space-between") for c in checks]
    body = rows or [dmc.Text(f"{test['value']}. The shuffled histories themselves are not saved, so there is no chart.", size="sm", c=FAINT)]
    return _panel("Is it luck?", "Luck test number and pass line", dmc.Stack(body, gap="xs", mt="sm"))


def returns_panel(report: dict[str, Any]) -> dmc.Paper:
    monthly = report["monthly"]
    children: list[Any] = []
    if monthly.empty:
        children.append(dmc.Text("No account-value history was saved.", size="sm", c=FAINT))
    else:
        figure = go.Figure(go.Heatmap(z=monthly.to_numpy(), x=["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"], y=[str(y) for y in monthly.index], zmid=0,
                                      colorscale=[[0, RED], [0.5, "#1A1C21"], [1, GREEN]], showscale=False, xgap=3, ygap=3, hovertemplate="%{y} month %{pointNumber[1]}: %{z:.1f}%<extra></extra>"))
        figure.update_yaxes(type="category", autorange="reversed")
        children.append(_figure(figure, max(140, 34 * len(monthly) + 40)))
    pnl = pd.Series(report["pnl"], dtype=float)
    if pnl.empty:
        children.append(dmc.Text("Profit per trade: no trades were saved.", size="sm", c=FAINT))
    else:
        figure = go.Figure([go.Histogram(x=pnl[pnl < 0], marker_color=RED, xbins=dict(size=_bin(pnl))), go.Histogram(x=pnl[pnl >= 0], marker_color=GREEN, xbins=dict(size=_bin(pnl)))])
        figure.update_layout(barmode="overlay", bargap=0.05)
        children += [dmc.Group([dmc.Text("Profit per trade", size="sm"), dmc.Text(f"{len(pnl):,} trades", size="xs", c=FAINT)], justify="space-between"), _figure(figure, 150)]
    return _panel("Monthly returns", "% per month", *children)


def _bin(pnl: pd.Series) -> float:
    return float((pnl.max() - pnl.min()) / 24) or 1.0


def trades_panel(report: dict[str, Any]) -> dmc.Paper:
    note = [] if report["unseen_trades_saved"] else [dmc.Text("Trades from the unseen period: " + NOT_SAVED.lower(), size="xs", c=FAINT)]
    grid = dag.AgGrid(id="idea-report-trades", columnDefs=TRADE_COLUMNS, rowData=report["trades"], defaultColDef={"sortable": True, "filter": True, "resizable": True, "minWidth": 70},
                      dashGridOptions={"theme": GRID_THEME, "localeText": {"noRowsToShow": "No trades were saved for this idea."}, "pagination": True, "paginationPageSize": 10, "paginationPageSizeSelector": False},
                      columnSize="responsiveSizeToFit", style={"height": 480}, getRowId="params.data.trade_id")
    return _panel("Trades", "Sort or filter any column", *note, grid)


def header(report: dict[str, Any]) -> dmc.Stack:
    chips = [dmc.Badge(report["verdict"], color=TONE[report["verdict_tone"]], variant="light")]
    chips += [dmc.Badge(text, color="gray", variant="light") for text in (report["symbol"], report["tested"]) if text]
    return dmc.Stack([dmc.Text("Results / Idea report", size="xs", c=FAINT), dmc.Title(report["title"], order=1, size=26, fw=600), dmc.Group(chips, gap=6)], gap=8)


def _message(text: str) -> dmc.Paper:
    return dmc.Paper(dmc.Text(text, size="sm", c=MUTED), p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}"})


def idea_report_layout(search: str | None = None) -> html.Div:
    query = {key: values[0] for key, values in parse_qs((search or "").lstrip("?")).items()}
    report = load_report(query.get("candidate_id"), run_id=query.get("run_id"))
    if not report["available"]:
        body: list[Any] = [_message(report["message"])]
    else:
        body = [header(report),
                dmc.Grid([dmc.GridCol(hero(report), span={"base": 12, "lg": 8}), dmc.GridCol(kpis(report), span={"base": 12, "lg": 4})], gutter="md"),
                tests_panel(report),
                dmc.SimpleGrid([settings_panel(report), luck_panel(report), returns_panel(report)], cols={"base": 1, "md": 2, "xl": 3}, spacing="md"),
                trades_panel(report)]
    return html.Div(dmc.MantineProvider(dmc.Stack(body, gap="md", p={"base": "sm", "sm": "lg"}, maw=1440, mx="auto"), theme=REPORT_THEME, forceColorScheme="dark"),
                    style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})
