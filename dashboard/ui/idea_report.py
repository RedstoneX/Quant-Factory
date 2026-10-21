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

from dashboard.idea_report_projection import NOT_SAVED, STATUS_TONE, UNSAVED_UNSEEN_NOTE, load_report
from dashboard.ui.results import TRADE_COLUMNS

FONT_URL = "https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap"
SANS, MONO = "Geist, ui-sans-serif, -apple-system, sans-serif", "'Geist Mono', ui-monospace, monospace"
BG, PANEL, INNER, LINE, TEXT, MUTED, FAINT = "#08090B", "#0F1114", "#131519", "#1F2228", "#ECEDEE", "#9BA1AB", "#6B7280"
INDIGO, GREEN, AMBER, RED, HOLD = "#818CF8", "#5EEAB0", "#F5B841", "#F2545B", "#4B5160"
TONE = {"green": GREEN, "amber": AMBER, "red": RED, "grey": MUTED}
SCALE = [[0, RED], [0.5, "#1A1C21"], [1, GREEN]]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
REPORT_THEME = {"fontFamily": SANS, "headings": {"fontFamily": SANS}, "colors": {"dark": [TEXT, "#C4C8CF", MUTED, FAINT, "#262930", "#1A1C21", PANEL, BG, "#050506", "#050506"]},
                "primaryColor": "indigo", "defaultRadius": "md", "black": BG, "white": TEXT}
GRID_THEME = {"function": "themeQuartz.withParams(" + json.dumps({
    "browserColorScheme": "dark", "backgroundColor": PANEL, "foregroundColor": TEXT, "chromeBackgroundColor": PANEL, "headerBackgroundColor": PANEL,
    "headerTextColor": FAINT, "borderColor": "#16181C", "accentColor": INDIGO, "oddRowBackgroundColor": PANEL, "fontFamily": SANS, "fontSize": 13,
    "wrapperBorder": False, "rowHeight": 40, "headerHeight": 40}) + ")"}
CARD = {"border": f"1px solid {LINE}", "minWidth": 0, "overflow": "hidden"}


def _panel(title: str, note: str, *children: Any) -> dmc.Paper:
    return dmc.Paper([
        dmc.Group([dmc.Text(title, fw=600, size="md"), dmc.Text(note, size="xs", c=FAINT)], justify="space-between", align="baseline", gap="xs"),
        *children], p="lg", radius="lg", bg=PANEL, style=CARD, className="idea-report-panel")


def _figure(figure: go.Figure, height: int, right: int = 8, legend: bool = False) -> dcc.Graph:
    """`legend`: show Plotly's own legend for the traces that opt in (showlegend=True), as a click-to-toggle control."""
    figure.update_layout(autosize=True, height=height, margin=dict(l=44, r=right, t=28 if legend else 8, b=24), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(family=SANS, color=MUTED, size=11), showlegend=legend, hovermode="x unified",
                         legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom", bgcolor="rgba(0,0,0,0)", font=dict(color=MUTED, size=11)))
    figure.update_xaxes(gridcolor="#16181C", zeroline=False, showline=False)
    figure.update_yaxes(gridcolor="#16181C", zeroline=False, showline=False)
    return dcc.Graph(figure=figure, config={"displayModeBar": False, "responsive": True}, responsive=True, style={"width": "100%", "height": f"{height}px"})


def _legend(data: dict[str, Any]) -> dmc.Group:
    def key(color: str, text: str) -> dmc.Group:
        return dmc.Group([html.Span(style={"width": 12, "height": 2, "background": color}), dmc.Text(text, size="xs", c=MUTED)], gap=6)
    drawn = [(INDIGO, "Built on", len(data["built"])), (GREEN, "Unseen data", len(data["unseen"]))]  # buy and hold is the chart's own legend toggle
    return dmc.Group([key(color, text) for color, text, count in drawn if count], gap="md")


def _fill(color: str) -> str:
    return f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.12)"


def hero(report: dict[str, Any]) -> dmc.Paper:
    data = report["hero"]
    if data["kind"] == "never_ran":  # no empty chart frame: a plain grey card with the reason and the fix
        return dmc.Paper([
            dmc.Text("No account-value chart for this idea", fw=600, size="md"),
            dmc.Text(data["reason"], size="sm", c=TEXT),
            dmc.Text(f"What to fix: {data['fix']}", size="sm", c=MUTED),
        ], p="lg", radius="lg", bg=INNER, style={"border": f"1px solid {LINE}"}, className="idea-report-never-ran")
    figure = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.76, 0.24], vertical_spacing=0.12)
    start = float((data["built"] if len(data["built"]) else data["unseen"]).iloc[0])  # every line is % growth from the same starting money, on one axis
    growth = {key: (data[key] / start - 1) * 100 for key in ("built", "unseen", "hold")}
    floor = min(float(growth[key].min()) for key in ("built", "unseen") if len(growth[key]))  # hidden buy and hold never sets the scale
    for key, color, name in (("built", INDIGO, "Built on"), ("unseen", GREEN, "Unseen data")):
        if len(growth[key]):  # an invisible floor line gives the soft fill something to fill down to
            figure.add_trace(go.Scatter(x=growth[key].index, y=[floor] * len(growth[key]), mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False), row=1, col=1)
            figure.add_trace(go.Scatter(x=growth[key].index, y=growth[key], mode="lines", line=dict(color=color, width=2), name=name, fill="tonexty", fillcolor=_fill(color), showlegend=False), row=1, col=1)
    if len(growth["hold"]):  # off by default; Plotly's legend click turns it on ("legendonly" is Plotly's standard hidden state)
        figure.add_trace(go.Scatter(x=growth["hold"].index, y=growth["hold"], mode="lines", line=dict(color=HOLD, width=1.4), name="Compare: buy and hold", visible="legendonly", showlegend=True), row=1, col=1)
    if len(data["unseen"]) and len(data["built"]):
        split = data["unseen"].index[0].isoformat()
        for domain in ("y domain", "y2 domain"):
            figure.add_shape(type="line", x0=split, x1=split, y0=0, y1=1, xref="x", yref=domain, line=dict(color=MUTED, width=1, dash="dot"))
        figure.add_annotation(x=split, y=1, xref="x", yref="y domain", text="Unseen data →", showarrow=False, xanchor="left", yanchor="top", font=dict(color=GREEN, size=11))
    drop = data["drawdown"]
    figure.add_trace(go.Scatter(x=drop.index, y=drop, mode="lines", line=dict(color=RED, width=1.2), fill="tozeroy", fillcolor="rgba(242,84,91,0.25)", name="Below peak %", showlegend=False), row=2, col=1)
    figure.update_yaxes(ticksuffix="%", row=1, col=1)
    figure.update_yaxes(ticksuffix="%", row=2, col=1)
    note = [dmc.Text(UNSAVED_UNSEEN_NOTE, size="xs", c=FAINT)] if data["unseen_label_note"] else []
    return dmc.Paper([dmc.Group([dmc.Text("Account value", fw=600, size="md"), _legend(data)], justify="space-between", gap="xs"), _figure(figure, 400, legend=bool(len(data["hold"]))), *note],
                     p="lg", radius="lg", bg=PANEL, style=CARD, className="idea-report-hero")


def strip(report: dict[str, Any]) -> dmc.Paper | None:
    items = report["strip"]
    if not items:
        return None
    cells = [html.Div([dmc.Text(label, size="xs", c=FAINT),
                       dmc.Text(value, size="xl", fw=500, ff=MONO, c=GREEN if value.startswith("+") else RED if value.startswith("-") or label == "Worst drop" else TEXT)]) for label, value in items]
    return dmc.Paper(dmc.SimpleGrid(cells, cols={"base": 2, "sm": len(cells)}, spacing="md"), p="lg", radius="lg", bg=PANEL, style=CARD, className="idea-report-strip")


def test_card(index: int, test: dict[str, Any]) -> dmc.Paper:
    tone = TONE[STATUS_TONE[test["status"]]]
    bar: list[Any] = []
    if test["fraction"] is not None:
        tick = [html.Div(style={"position": "absolute", "top": -4, "left": f"{test['pass_line'] * 100:.1f}%", "width": 2, "height": 14, "background": TEXT})] if test["pass_line"] is not None else []
        bar = [html.Div([dmc.Progress(value=max(0, min(1, test["fraction"])) * 100, color=tone, size=6), *tick], style={"position": "relative", "marginBottom": 10})]
    saved_note = []
    if test["stage"] == "walk_forward" and test["run_id"] and not test["detail"]["periods"]:
        saved_note = [dmc.Text("Per-window numbers: " + NOT_SAVED.lower(), size="xs", c=FAINT)]
    return dmc.Paper([
        dmc.Group([dmc.Text(f"{index} · {test['label']}", fw=500, size="sm"), *([dmc.Badge(test["status"], color=tone, variant="light", size="sm")] if test["run_id"] else [])], justify="space-between", gap="xs"),
        *([dmc.Text(test["rule"], size="xs", c=MUTED)] if test.get("rule") else []),
        dmc.Text(test["value"], size="sm", c=MUTED) if str(test["value"]).startswith("Not scored") else dmc.Text(test["value"], size="lg", ff=MONO), *bar,
        *[dmc.Text([f"{name} · not saved"] if value is None else [f"{name} · Sharpe ", html.Span(value, style={"fontFamily": MONO})], size="xs") for name, value in test.get("scores") or []], *([dmc.Text(test["line"], size="xs", c=MUTED)] if test["line"] else []), *saved_note,
    ], p="md", radius="md", bg=INNER, style={"border": f"1px solid {LINE}"}, className="idea-report-test")


def tests_panel(report: dict[str, Any]) -> dmc.Paper:
    return _panel("The five tests", "White tick = pass line · bar = this idea",
                  dmc.SimpleGrid([test_card(i, t) for i, t in enumerate(report["tests"], 1)], cols={"base": 1, "sm": 2, "lg": 5}, spacing="sm", mt="sm"))


def settings_panel(report: dict[str, Any]) -> dmc.Paper | None:
    grid = report["grid"]
    if not grid:
        return None
    down, across = grid["down"].replace("_", " "), grid["across"].replace("_", " ")
    if not grid["across"]:  # one setting varied: a plain vertical list of bars
        values = [row[0] for row in grid["values"]]
        outline = [TEXT if grid["chosen"] and str(row) == grid["chosen"][0] else "rgba(0,0,0,0)" for row in grid["rows"]]
        figure = go.Figure(go.Bar(x=values, y=[str(row) for row in grid["rows"]], orientation="h", marker=dict(color=[GREEN if (v or 0) >= 0 else RED for v in values], line=dict(color=outline, width=2)),
                                  hovertemplate=f"{down} %{{y}}<br>Sharpe %{{x:.2f}}<extra></extra>"))
        figure.update_yaxes(type="category", title=down, autorange="reversed")
        figure.update_xaxes(title="Sharpe after costs")
    else:
        figure = go.Figure(go.Heatmap(z=grid["values"], x=grid["columns"], y=grid["rows"], colorscale=SCALE, zmid=0, showscale=False, xgap=3, ygap=3,
                                      hovertemplate=f"{down} %{{y}}<br>{across} %{{x}}<br>Sharpe %{{z:.2f}}<extra></extra>"))
        if grid["chosen"]:
            figure.add_trace(go.Scatter(x=[grid["chosen"][1]], y=[grid["chosen"][0]], mode="markers", marker=dict(symbol="square-open", size=26, color=TEXT, line=dict(width=2)), hoverinfo="skip"))
        figure.update_xaxes(type="category", title=across)
        figure.update_yaxes(type="category", title=down)
    figure.update_layout(hovermode="closest")
    return _panel("Every setting tried", "Sharpe after costs · white outline = chosen", _figure(figure, 300), dmc.Text(f"{grid['count']:,} settings tried.", size="xs", c=MUTED))


def luck_panel(report: dict[str, Any]) -> dmc.Paper | None:
    test = next(t for t in report["tests"] if t["stage"] == "monte_carlo")
    if not test["run_id"]:
        return None
    rows = [dmc.Group([dmc.Text(c["check"], size="sm"), dmc.Text(f"{c['measured']} · needs {c['needed']}", size="sm", ff=MONO, c=MUTED)], justify="space-between") for c in test["detail"]["checks"]]
    if not rows:  # no chart and no numbers: the Shuffle test card already says why
        return None
    luck = report.get("luck")  # the deflated-Sharpe number is a separate score, not a shuffle check
    luck_line = dmc.Text(["Luck score ", html.Span("not scored" if luck is None else f"{float(luck):.2f}", style={"fontFamily": MONO}), " · chance the result is skill, not luck from trying many settings"], size="xs", c=MUTED, mt="xs")
    return _panel("Shuffle test", "Measured · needed, per check", dmc.Stack(rows, gap="xs", mt="sm"), luck_line)


def _bin(pnl: pd.Series) -> float:
    return float((pnl.max() - pnl.min()) / 24) or 1.0


def returns_panel(report: dict[str, Any]) -> dmc.Paper | None:
    monthly = report["monthly"]
    children: list[Any] = []
    if not monthly.empty:
        text = [[None if pd.isna(v) else f"{MONTHS[m - 1]} {year}: {v:+.1f}%" for m, v in zip(range(1, 13), row)] for year, row in zip(monthly.index, monthly.to_numpy())]
        figure = go.Figure(go.Heatmap(z=monthly.to_numpy(), x=list(range(1, 13)), y=[str(year) for year in monthly.index], zmid=0, text=text, hoverinfo="text", colorscale=SCALE, xgap=3, ygap=3,
                                      colorbar=dict(thickness=8, len=0.9, ticksuffix="%", tickfont=dict(size=10), outlinewidth=0)))
        figure.update_xaxes(tickvals=list(range(1, 13)), ticktext=[m[0] for m in MONTHS])
        figure.update_yaxes(type="category", autorange="reversed", side="left")
        figure.update_layout(hovermode="closest")
        children.append(_figure(figure, max(140, 30 * len(monthly) + 40), right=56))
    pnl = pd.Series(report["pnl"], dtype=float)
    if not pnl.empty:
        figure = go.Figure([go.Histogram(x=pnl[pnl < 0], marker_color=RED, xbins=dict(size=_bin(pnl))), go.Histogram(x=pnl[pnl >= 0], marker_color=GREEN, xbins=dict(size=_bin(pnl)))])
        figure.update_layout(barmode="overlay", bargap=0.05)
        children += [dmc.Group([dmc.Text("Profit per trade", size="sm"), dmc.Text(f"{len(pnl):,} trades", size="xs", c=FAINT)], justify="space-between"), _figure(figure, 150)]
    return _panel("Monthly returns", "% per month", *children) if children else None


PHONE_DROPPED = {"entry_display", "exit_display", "duration"}


def _columns(phone: bool) -> list[dict[str, Any]]:
    """Desktop: #, Side, Entry, Exit, Duration, Profit or loss, Running total, Outcome, nothing pinned.
    Phone: # and Profit or loss pinned, Exit and Duration dropped, Entry as a short date."""
    columns: list[dict[str, Any]] = []
    for column in TRADE_COLUMNS:
        if phone and column["field"] in PHONE_DROPPED:
            if column["field"] == "entry_display":
                columns.append({"field": "entry_short", "headerName": "Entry", "minWidth": 120, "flex": 1, "suppressHeaderFilterButton": True, "suppressHeaderMenuButton": True})
            continue
        column = {**column, "minWidth": max(int(column.get("minWidth", 100)), 100), "flex": 1}
        if column["field"] == "trade_id":
            column.update(headerName="#", flex=None, width=48, minWidth=48, suppressHeaderFilterButton=True, suppressHeaderMenuButton=True, **({"pinned": "left"} if phone else {}))
        if column["field"] == "direction" and phone:
            column.update(minWidth=64, suppressHeaderFilterButton=True, suppressHeaderMenuButton=True)
        if column["field"] == "pnl":
            column.update(flex=None, width=90 if phone else 130, minWidth=90 if phone else 130, **({"pinned": "right", "wrapHeaderText": True, "autoHeaderHeight": True} if phone else {}))
        columns.append({key: value for key, value in column.items() if value is not None})
    return columns


def _short_entry(timestamp: Any) -> str:
    stamp = pd.Timestamp(timestamp)
    return f"{stamp.day} {stamp:%b %y}, {stamp.hour}:{stamp:%M}"


def trades_panel(report: dict[str, Any]) -> dmc.Paper | None:
    if not report["trades"]:
        return None
    rows = [{**trade, "entry_short": _short_entry(trade["entry_timestamp"])} for trade in report["trades"]]
    note = [] if report["unseen_trades_saved"] else [dmc.Text(UNSAVED_UNSEEN_NOTE, size="xs", c=FAINT)]

    def grid(grid_id: str, phone: bool) -> dag.AgGrid:
        return dag.AgGrid(id=grid_id, columnDefs=_columns(phone), rowData=rows, defaultColDef={"sortable": True, "filter": True, "resizable": True},
                          dashGridOptions={"theme": GRID_THEME, "pagination": True, "paginationPageSize": 10, "paginationPageSizeSelector": False},
                          style={"height": 480}, getRowId="params.data.trade_id")
    # Mantine's own breakpoint props pick the layout (no grid scripting): the phone grid below "sm", the desktop grid from "sm" up
    return _panel("Trades", "Sort or filter any column", *note, dmc.Box(grid("idea-report-trades", False), visibleFrom="sm"), dmc.Box(grid("idea-report-trades-phone", True), hiddenFrom="sm"))


def header(report: dict[str, Any]) -> dmc.Stack:
    parts = report.get("verdict_line")
    chips = [] if parts else [dmc.Badge(report["verdict"], color=TONE[report["verdict_tone"]], variant="light")]
    chips += [dmc.Badge(text, color="gray", variant="light") for text in (report["symbol"], report["tested"]) if text]
    line = [dmc.Text([html.Span(text, style={"color": {"green": GREEN, "red": RED}.get(tone, MUTED)}) for text, tone in parts], size="sm")] if parts else []  # sentence case, wraps on phone
    return dmc.Stack([dmc.Text("Results / Idea report", size="xs", c=FAINT), dmc.Title(report["title"], order=1, size=26, fw=600), *line, dmc.Group(chips, gap=6)], gap=8)



def _message(text: str) -> dmc.Paper:
    return dmc.Paper(dmc.Text(text, size="sm", c=MUTED), p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}"})


def idea_report_layout(search: str | None = None) -> html.Div:
    query = {key: values[0] for key, values in parse_qs((search or "").lstrip("?")).items()}
    report = load_report(query.get("candidate_id"), run_id=query.get("run_id"))
    if not report["available"]:
        body: list[Any] = [_message(report["message"])]
    elif report["hero"]["kind"] == "never_ran":  # nothing else has data to show
        body = [header(report), hero(report), tests_panel(report)]
    else:
        lower = [panel for panel in (settings_panel(report), luck_panel(report), returns_panel(report)) if panel is not None]
        body = [header(report), strip(report), hero(report), tests_panel(report)]
        if lower:
            body.append(dmc.SimpleGrid(lower, cols={"base": 1, "md": min(2, len(lower)), "xl": len(lower)}, spacing="md", style={"minWidth": 0, "alignItems": "start"}))
        body = [item for item in [*body, trades_panel(report)] if item is not None]
    return html.Div(dmc.MantineProvider(dmc.Stack(body, gap="md", p={"base": "sm", "sm": "lg"}, maw=1440, mx="auto", style={"minWidth": 0}), theme=REPORT_THEME, forceColorScheme="dark"),
                    style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})
