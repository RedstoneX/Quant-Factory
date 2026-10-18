"""Today: the home screen. Thin Dash Mantine + Plotly layer over today_projection; reuses the idea report's chart, strip and header chips."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dcc, html, no_update

from dashboard.idea_report_projection import load_report
from dashboard.today_projection import load_today
from dashboard.ui.idea_report import AMBER, BG, FAINT, GREEN, HOLD, INDIGO, LINE, MUTED, PANEL, RED, REPORT_THEME, SANS, SCALE, TEXT, TONE, hero, strip

CARD = {"border": f"1px solid {LINE}", "minWidth": 0, "overflow": "hidden"}
STEP_COLOR = [HOLD, INDIGO, INDIGO, INDIGO, INDIGO, GREEN]  # submitted grey, tests indigo, last step green
HEAT_ROWS = 8  # rows of "What works where" shown before "Show all"
LABEL_CHARS = 18  # phone row labels are cut to this many characters
# Dot colour by status, the chip colours: failed or crashed muted red at 50%, close call amber, can't test grey, passed green.
STATUS_DOTS = (("Passed", GREEN, 1.0, 11), ("Close call", AMBER, 1.0, 9), ("Can't test", MUTED, 0.8, 8), ("Failed", RED, 0.5, 8))


def _panel(title: str, note: str, *children: Any) -> dmc.Paper:
    return dmc.Paper([dmc.Group([dmc.Text(title, fw=600, size="md"), dmc.Text(note, size="xs", c=FAINT)], justify="space-between", align="baseline", gap="xs"), *children],
                     p="lg", radius="lg", bg=PANEL, style=CARD)


def _chip(text: str, tone: str, outline: bool = False) -> dmc.Badge:
    return dmc.Badge(text, color=TONE[tone], variant="outline" if outline else "light", h=20, size="sm")


def _link(candidate_id: str) -> str:
    return f"/report?candidate_id={quote(str(candidate_id), safe='')}"


def _graph(figure: go.Figure, height: int, **kwargs: Any) -> dcc.Graph:
    figure.update_layout(autosize=True, height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family=SANS, color=MUTED, size=11), showlegend=bool(figure.layout.showlegend))
    figure.update_xaxes(gridcolor="#16181C", zeroline=False, showline=False)
    figure.update_yaxes(gridcolor="#16181C", zeroline=False, showline=False, side="left", anchor="free", position=0)
    return dcc.Graph(figure=figure, config={"displayModeBar": False, "responsive": True}, responsive=True, style={"width": "100%", "height": f"{height}px"}, **kwargs)


def headline(data: dict[str, Any]) -> dmc.Stack:
    waiting, close = len(data["waiting"]["passed"]), len(data["waiting"]["close"])
    today = pd.Timestamp.now(tz="America/New_York")
    if waiting:
        text = f"{waiting} {'idea is' if waiting == 1 else 'ideas are'} waiting for your call." + (f" {close} more came close." if close else "")
    elif close:
        text = f"Nothing has passed yet. {close} {'idea' if close == 1 else 'ideas'} came close."
    else:
        text = "Nothing needs your call right now."
    return dmc.Stack([dmc.Text(f"{today:%A} {today.day} {today:%B}", size="xs", c=FAINT), dmc.Title(text, order=1, size=26, fw=600)], gap=4)


def best_title(data: dict[str, Any]) -> str:
    """"Best idea" once any idea has passed all five tests, otherwise "Closest so far"."""
    return "Best idea" if len(data["waiting"]["passed"]) else "Closest so far"


def best_panel(data: dict[str, Any]) -> dmc.Stack | None:
    """The best idea: its header chips, the idea report's own summary strip and account-value chart."""
    if not data["best"]:
        return None
    report = load_report(data["best"])
    if not report.get("available") or report["hero"]["kind"] != "chart":
        return None
    chips = [_chip(report["verdict"], report["verdict_tone"])] + [dmc.Badge(text, color="gray", variant="light", h=20, size="sm") for text in (report["symbol"],) if text]
    head = dmc.Group([dmc.Stack([dmc.Text(best_title(data), size="xs", c=FAINT), dmc.Text(report["title"], fw=600, size="lg"), dmc.Group(chips, gap=6)], gap=4, style={"minWidth": 0}),
                      html.A(dmc.Button("Open report →", color="indigo", size="sm"), href=_link(data["best"]), style={"textDecoration": "none"})], justify="space-between", align="flex-start", gap="sm")
    return dmc.Stack([head, strip(report), hero(report)], gap="md", style={"minWidth": 0})


def funnel_panel(data: dict[str, Any]) -> dmc.Paper | None:
    """Bars drawn to true scale: each bar is that step's share of everything submitted; steps at zero read grey."""
    if not data["funnel"]:
        return None
    total = data["funnel"][0]["count"]
    rows = []
    for index, step in enumerate(data["funnel"]):
        quiet = FAINT if step["count"] == 0 else None
        rows.append(dmc.Stack([dmc.Group([dmc.Text(step["label"], size="sm", c=quiet or "#C4C8CF"),
                                          dmc.Text([str(step["count"]), dmc.Text(f"  {step['share']:.0%}", span=True, c=FAINT)], size="sm", ff="monospace", **({"c": quiet} if quiet else {}))], justify="space-between"),
                               dmc.Progress(value=step["share"] * 100, color=STEP_COLOR[index], size=8)], gap=6))
    failure = data["failure"]
    note = [dmc.Paper(dmc.Text(f"{failure['count']} of {failure['total']} ideas fail the “{failure['label']}” test, more than any other.", size="sm", c="#F5D27A"),
                      p="sm", radius="md", bg="#1A1205", style={"border": "1px solid #33240A"})] if failure else []
    return _panel(f"Where the {total} went", "Bars to true scale", dmc.Stack([*rows, *note], gap="md", mt="sm"))


def per_day_panel(data: dict[str, Any]) -> dmc.Paper | None:
    """Tests run per day over the 14 fixed days, an x label every third day and none rotated."""
    counts = data["per_day"]
    if counts.empty:
        return None
    labels = [f"{stamp.day} {stamp:%b}" for stamp in counts.index]
    figure = go.Figure(go.Bar(x=labels, y=counts.to_numpy(), marker=dict(color=INDIGO), hovertemplate="%{x}: %{y} tests<extra></extra>"))
    figure.update_layout(margin=dict(l=32, r=8, t=8, b=28), bargap=0.25)
    figure.update_xaxes(type="category", tickmode="array", tickvals=labels[::-1][::3], tickangle=0)
    return _panel("Tests run per day", "Last 14 days", _graph(figure, 180))


def status_group(result: str) -> str:
    """Scatter group of a result word: Failed and Crashed share the failed colour, No trades never reaches the scatter."""
    return "Passed" if result == "Passed" else "Close call" if result == "Close call" else "Can't test" if result == "Can't test" else "Failed"


def scatter_panel(data: dict[str, Any]) -> dmc.Paper | None:
    points = data["scatter"]
    if points.empty:
        return None
    figure = go.Figure()
    best = points[points["candidate_id"] == data["best"]]
    rest = points[points["candidate_id"] != data["best"]]
    groups = rest["result"].map(status_group)
    for name, color, opacity, size in STATUS_DOTS:
        part = rest[groups == name]
        if part.empty:
            continue
        figure.add_trace(go.Scatter(x=part["worst_drop"], y=part["total_return"], mode="markers", name=name, customdata=part[["candidate_id", "title"]].to_numpy(),
                                    hovertemplate="%{customdata[1]}<br>Return %{y:.1f}%, worst drop %{x:.1f}%<extra></extra>", marker=dict(color=color, size=size, opacity=opacity)))
    if not best.empty:  # the closest or best idea: bigger, indigo, labelled
        title = str(best.iloc[0]["title"])
        figure.add_trace(go.Scatter(x=best["worst_drop"], y=best["total_return"], mode="markers+text", name=best_title(data), text=[title if len(title) <= 28 else title[:27] + "…"], textposition="middle left",
                                    textfont=dict(color=TEXT, size=11), customdata=best[["candidate_id", "title"]].to_numpy(), hovertemplate="%{customdata[1]}<br>Return %{y:.1f}%, worst drop %{x:.1f}%<extra></extra>",
                                    marker=dict(color=INDIGO, size=15, line=dict(color=TEXT, width=1.5))))
    figure.add_hline(y=0, line=dict(color="#3A3F48", width=1))
    figure.update_layout(margin=dict(l=44, r=8, t=24, b=92), hovermode="closest", xaxis_title="Worst drop (%)", yaxis_title="Return (%)", showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.2, x=0, font=dict(color=MUTED)))
    return _panel("Every idea: profit vs worst drop", "Click a dot to open its report", _graph(figure, 370, id="today-scatter"))


def close_calls_panel(data: dict[str, Any]) -> dmc.Paper | None:
    if not data["close_calls"]:
        return None
    rows = []
    for item in data["close_calls"]:
        gap = f"{item['check']}: {item['measured']}, needed {item['needed']}" if item["check"] else ""
        rows.append(dmc.Stack([
            dmc.Group([html.A(item["title"], href=_link(item["candidate_id"]), style={"color": TEXT, "textDecoration": "none", "fontWeight": 500, "minWidth": 0, "overflow": "hidden", "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                       dmc.Text(f"Missed at {item['step']}" if item["step"] else "", size="xs", c=FAINT, style={"whiteSpace": "nowrap"})], justify="space-between", wrap="nowrap", gap="sm"),
            *([dmc.Progress(value=item["fraction"] * 100, color="yellow", size=6)] if item["fraction"] is not None else []),
            *([dmc.Text(gap, size="xs", c=MUTED, ff="monospace")] if gap else [])], gap=4, py=10, style={"borderTop": "1px solid #16181C"}))
    return _panel("Close calls", f"{len(data['waiting']['close'])} in all", dmc.Stack(rows, gap=0, mt="sm"))


def owner_panel(data: dict[str, Any]) -> dmc.Paper | None:
    passed = data["waiting"]["passed"]
    if passed.empty:
        return None
    rows = [dmc.Group([dmc.Stack([dmc.Text(row["title"], fw=500, size="sm", truncate="end"), dmc.Text(f"{row['market']} · {row['timeframe']} · {row['family']}", size="xs", c=FAINT, truncate="end")], gap=0, style={"minWidth": 0, "flex": 1}),
                       _chip("Passed", "green"), html.A(dmc.Text("Open report →", size="sm", c=INDIGO), href=_link(row["candidate_id"]), style={"textDecoration": "none"})],
                      wrap="nowrap", gap="sm", py=10, style={"borderTop": "1px solid #16181C"}) for row in passed.to_dict("records")]
    return _panel("Waiting for your call", f"{len(passed)} passed all five tests", dmc.Stack(rows, gap=0, mt="sm"))


def heat_text(value: Any) -> str:
    """One decimal, with no minus sign on a zero (-0.04 prints 0.0)."""
    return "" if pd.isna(value) else f"{round(float(value), 1) + 0.0:.1f}"


def heat_rows(table: pd.DataFrame) -> pd.DataFrame:
    """Longer list down the page, rows ordered by their best cell, highest first."""
    table = table.T if table.shape[1] > table.shape[0] else table
    return table.loc[table.max(axis=1).sort_values(ascending=False, kind="stable").index]


def short_label(name: str, phone: bool) -> str:
    return name if not phone or len(name) <= LABEL_CHARS else name[:LABEL_CHARS - 1] + "…"


def heat_figure(table: pd.DataFrame, cap: float, phone: bool, header: bool) -> dcc.Graph:
    names = list(table.index)
    figure = go.Figure(go.Heatmap(z=table.to_numpy(), x=list(table.columns), y=names, colorscale=SCALE, zmin=-cap, zmax=cap, showscale=False, xgap=3, ygap=3,
                                  text=table.map(heat_text).to_numpy(), texttemplate="%{text}", hovertemplate="%{y} · %{x}<br>Best Sharpe %{z:.2f}<extra></extra>", hoverongaps=False))
    figure.update_layout(margin=dict(l=8, r=8, t=8, b=8), xaxis=dict(side="top", showticklabels=header), yaxis=dict(automargin=True, autorange="reversed", tickmode="array", tickvals=names,
                                                                                                                  ticktext=[short_label(name, phone) for name in names]))
    return _graph(figure, (30 if header else 0) + 34 * len(names) + 16)


def heatmap_panel(data: dict[str, Any]) -> dmc.Paper | None:
    table = data["heatmap"]
    if table.empty:
        return None
    cap = float(table.abs().max().max()) or 1.0
    table = heat_rows(table)
    top, more = table.iloc[:HEAT_ROWS], table.iloc[HEAT_ROWS:]

    def body(phone: bool) -> dmc.Box:
        parts: list[Any] = [heat_figure(top, cap, phone, True)]
        if not more.empty:
            parts.append(dmc.Collapse(heat_figure(more, cap, phone, False), id=f"today-heat-more-{'phone' if phone else 'desk'}", opened=False))
        return dmc.Box(parts, **({"hiddenFrom": "sm"} if phone else {"visibleFrom": "sm"}))
    toggle = [dmc.Button(f"Show all {len(table)}", id="today-heat-toggle", variant="default", size="xs"), dcc.Store(id="today-heat-total", data=len(table))] if not more.empty else []
    return _panel("What works where", "Best Sharpe after costs, by market and strategy type", body(False), body(True), *toggle)


def today_layout() -> html.Div:
    data = load_today()
    if data["ideas"].empty:
        body: list[Any] = [dmc.Paper(dmc.Text("No ideas have saved results yet.", size="sm", c=MUTED), p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}"})]
    else:
        def row(*panels: Any, spans: tuple[int, ...] = (6, 6)) -> dmc.Grid | None:
            shown = [(panel, span) for panel, span in zip(panels, spans) if panel is not None]
            if not shown:
                return None
            if len(shown) == 1:
                return dmc.Grid([dmc.GridCol(shown[0][0], span=12)], gutter="md")
            return dmc.Grid([dmc.GridCol(panel, span={"base": 12, "lg": span}) for panel, span in shown], gutter="md")
        side = [panel for panel in (funnel_panel(data), per_day_panel(data)) if panel is not None]
        sections = [row(best_panel(data), dmc.Stack(side, gap="md", style={"minWidth": 0}) if side else None, spans=(8, 4)), row(owner_panel(data), close_calls_panel(data)),
                    row(scatter_panel(data), heatmap_panel(data))]
        body = [headline(data), *[section for section in sections if section is not None]]
    return html.Div(dmc.MantineProvider(dmc.Stack(body, gap="md", p={"base": "sm", "sm": "lg"}, maw=1440, mx="auto", style={"minWidth": 0}), theme=REPORT_THEME, forceColorScheme="dark"),
                    style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_today_callbacks(application: Dash) -> None:
    """Standard Dash callbacks: a click on a scatter dot opens that idea's report; the heatmap toggle opens or closes its Mantine Collapse."""
    @application.callback(Output("router-location", "pathname", allow_duplicate=True), Output("router-location", "search", allow_duplicate=True),
                          Input("today-scatter", "clickData"), prevent_initial_call=True)
    def open_report(click: dict[str, Any] | None):
        point = ((click or {}).get("points") or [{}])[0]
        candidate = (point.get("customdata") or [None])[0]
        return ("/report", f"?candidate_id={quote(str(candidate), safe='')}") if candidate else (no_update, no_update)

    @application.callback(Output("today-heat-more-desk", "opened"), Output("today-heat-more-phone", "opened"), Output("today-heat-toggle", "children"),
                          Input("today-heat-toggle", "n_clicks"), State("today-heat-more-desk", "opened"), State("today-heat-total", "data"), prevent_initial_call=True)
    def toggle_heatmap(_clicks: int, opened: bool, total: int):
        return not opened, not opened, "Show all " + str(total) if opened else "Show fewer"


__all__ = ["register_today_callbacks", "today_layout"]
