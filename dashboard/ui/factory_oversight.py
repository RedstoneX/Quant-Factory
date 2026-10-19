"""Factory oversight page (/factory): read-only, refreshes itself every 10 s.

Thin Dash Mantine + Plotly layer over factory_overview.load_factory_overview. Exports layout() and register_callbacks(app);
the route and nav are wired in app.py by the caller.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import dash_mantine_components as dmc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update

from dashboard.factory_overview import ONE_AT_A_TIME, OUTCOME_WORDS, load_factory_overview
from dashboard.ui import gateway_client
from dashboard.ui.idea_report import AMBER, BG, FAINT, GREEN, HOLD, INDIGO, LINE, MONO, MUTED, REPORT_THEME, RED, SANS, TEXT


REFRESH_MS = 10_000
OUTCOME_COLOR = {"failed": "#4B5160", "close": AMBER, "passed": GREEN, "crashed": RED, "running": INDIGO, "unchecked": MUTED, "interrupted": MUTED}  # neither is a failure: neutral grey
TONE_COLOR = {"green": GREEN, "amber": AMBER, "red": RED, "grey": HOLD, "indigo": INDIGO, "text": TEXT, "idle": MUTED}
ICON = {"green": "✓", "amber": "!", "red": "×"}
STEP_CLASS = {"done": "done", "current": "current", "slow": "slow", "todo": "todo"}
NEUTRAL_FIGURE = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(family=MONO, color=FAINT, size=11))
CARD = "#0F1114"
GAP_PX = 2
MIN_BLOCK = pd.Timedelta(minutes=6)
GRAPH_CONFIG = {"displayModeBar": False}
OUTPUTS = ("fo-pill", "fo-date", "fo-headline", "fo-tiles", "fo-running", "fo-alerts", "fo-old-title", "fo-old-items", "fo-old-wrap", "fo-needs",
           "fo-queue-head", "fo-queue", "fo-timeline", "fo-timeline-empty", "fo-legend", "fo-hourly", "fo-hourly-phone", "fo-health", "fo-health-checked", "fo-log", "fo-log-more")


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
        title = "Each tile's line shows the last 24 hours" if tile.get("spark") is not None else None
        value = html.Span(tile["value"], className="fo-tile-value", style={"color": TONE_COLOR[tile["color"]]})
        out.append(html.Div([html.Span(tile["label"], className="fo-tile-label"),
                             html.Div([value, sparkline(tile["spark"], tile["color"])] if tile.get("spark") is not None else [value], className="fo-tile-row"),
                             html.Span(tile["sub"], className="fo-tile-sub")], className="fo-tile", title=title))
    return out


def running_cards(data: dict[str, Any]) -> list[Any]:
    if not data["running"]:
        last = data.get("last_test")
        text = [f"Idle since {last['when']} · last test: ", _link(last["name"], last["candidate_id"]), f" — {last['outcome']}"] if last else "Idle. The next waiting test starts on its own."
        return [html.Div("Paused — the line is held, nothing lost." if data.get("paused") else text, className="fo-empty")]
    return [html.Div([
        html.Div([_link(card["name"], card["candidate_id"], className="fo-name"), html.Span(card["elapsed"], className="fo-mono" + (" fo-amber" if card["slow"] else ""))], className="fo-between"),
        html.Div([html.Div(className=f"fo-step {STEP_CLASS[step]}") for step in card["steps"]], className="fo-steps"),
        html.Div([html.Span(card["where"]), html.Span(card["note"])], className="fo-between fo-muted"),
        *([html.Div(card["passes"], className="fo-muted")] if card.get("passes") else [])], className="fo-inner") for card in data["running"]]


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


def timeline_figure(rows: list[dict[str, Any]], now: Any, bands: list[dict[str, Any]] | None = None) -> go.Figure:
    now = pd.Timestamp(now)
    frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["name", "start", "end", "minutes", "outcome", "candidate_id"])
    if rows:
        frame["end"] = frame[["end", "start"]].apply(lambda r: max(r["end"], r["start"] + MIN_BLOCK), axis=1)  # a short run still shows; hover keeps the true time
        frame["Lane"] = "Factory"
        frame["Outcome"] = frame["outcome"].map(OUTCOME_WORDS)
        frame["Took"] = [("ended time unknown" if cap else f"{int(m)} min {int(round((m - int(m)) * 60)):02d} s" if m >= 1 else f"{int(round(m * 60))} s") for m, cap in zip(frame["minutes"], frame["capped"])]
        figure = px.timeline(frame, x_start="start", x_end="end", y="Lane", color="Outcome", color_discrete_map={OUTCOME_WORDS[k]: v for k, v in OUTCOME_COLOR.items()}, custom_data=["name", "Took", "Outcome", "candidate_id"])
        figure.update_traces(hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} · %{customdata[2]}<extra></extra>", width=0.9)
        for trace in figure.data:
            trace.marker.line = dict(width=GAP_PX, color=CARD)  # the card colour outlines each block, leaving a visible gap between neighbours
    else:
        figure = go.Figure()
    window = [now - pd.Timedelta(hours=12), now]
    for band in bands or []:  # a faint amber band, below the blocks, for each pause
        figure.add_vrect(x0=band["start"], x1=band["end"], fillcolor="rgba(0,0,0,0)", line=dict(color=AMBER, width=1.5, dash="dot"), layer="below", annotation_text="Paused", annotation_position="top left", annotation_font=dict(color=AMBER, size=11))
    figure.add_vline(x=now.to_pydatetime(), line=dict(color="rgba(236,237,238,0.55)", width=1, dash="dash"), annotation_text="now", annotation_position="top left", annotation_font=dict(color=MUTED, size=11))
    figure.update_layout(height=76, margin=dict(l=0, r=32, t=14, b=26), showlegend=False, hoverlabel=dict(font_family=SANS, bgcolor="#131519", bordercolor=LINE),
                         xaxis=dict(type="date", range=window, gridcolor="#1A1C21", tickformat="%H:%M", dtick=7200000, showline=False, zeroline=False), yaxis=dict(visible=False), bargap=0, **NEUTRAL_FIGURE)
    return figure


def timeline_empty(rows: list[dict[str, Any]]) -> str:
    return "" if rows else "No tests in the last 12 hours"


def hourly_empty_figure() -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text="No tests finished in the last 48 hours", showarrow=False, font=dict(color=FAINT, size=12), xref="paper", yref="paper", x=0.5, y=0.5)
    figure.update_layout(height=190, margin=dict(l=8, r=8, t=6, b=8), xaxis=dict(visible=False), yaxis=dict(visible=False), **NEUTRAL_FIGURE)
    return figure


def _phone_ticks(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Three flat labels (first day, second day, now) so nothing rotates at phone width."""
    if not rows:
        return {}
    return {"tickmode": "array", "tickvals": [rows[0]["hour"], rows[24]["hour"], rows[-1]["hour"]], "ticktext": [f"{rows[0]['hour']:%a}", f"{rows[24]['hour']:%a}", "now"], "tickangle": 0}


def hourly_figure(rows: list[dict[str, Any]], phone: bool = False) -> go.Figure:
    if not any(row[key] for row in rows for key in ("failed", "close", "passed", "crashed")):
        return hourly_empty_figure()
    figure = go.Figure()
    hours = [row["hour"] for row in rows]
    peak = max(sum(row[key] for key in ("failed", "close", "passed", "crashed")) for row in rows)
    for key in ("failed", "close", "passed", "crashed"):
        figure.add_trace(go.Bar(x=hours, y=[row[key] for row in rows], name=OUTCOME_WORDS[key], marker_color=OUTCOME_COLOR[key], hovertemplate="%{x|%a %H:%M}: %{y} " + OUTCOME_WORDS[key].lower() + "<extra></extra>"))
    figure.update_layout(barmode="stack", bargap=0.15, height=190, margin=dict(l=8, r=28 if phone else 8, t=6, b=8), showlegend=False, hoverlabel=dict(font_family=SANS, bgcolor="#131519", bordercolor=LINE),
                         xaxis=dict(gridcolor="#1A1C21", tickformat="%a %H:%M", showline=False, nticks=4, automargin=True, ticklabelstandoff=8, **_phone_ticks(rows) if phone else {}), yaxis=dict(gridcolor="#1A1C21", zeroline=False, rangemode="tozero", side="left", automargin=True, tickformat="d", **({"dtick": 1} if peak <= 6 else {})), **NEUTRAL_FIGURE)
    return figure


def health_rows(data: dict[str, Any]) -> list[Any]:
    return [html.Div([html.Span(ICON.get(item["tone"], "!"), className=f"fo-icon {item['tone']}"), html.Span(item["label"], className="fo-grow"), html.Span(item["value"], className="fo-muted fo-right")], className="fo-health-row") for item in data["health"]] \
        or [html.Div("Health checks are unavailable.", className="fo-empty")]


LOG_SHOWN = 12


def log_rows(data: dict[str, Any], rest: bool = False) -> list[Any]:
    items = data["log"][LOG_SHOWN:] if rest else data["log"][:LOG_SHOWN]
    return [html.Div([html.Span(item["t"], className="fo-mono fo-muted fo-time"), html.Span(className=f"fo-dot small {item['tone']}"), html.Span(item["text"], className="fo-body")], className="fo-log-row") for item in items] \
        or ([] if rest else [html.Div("Nothing has happened yet.", className="fo-empty")])


def headline_children(data: dict[str, Any]) -> Any:
    text = data["headline"] if data["available"] else f"{data['headline']}. {data.get('message') or ''}".strip()
    return html.Span(text, style={"color": AMBER}) if data.get("headline_tone") == "amber" else text


def legend_items(data: dict[str, Any]) -> list[Any]:
    keys = [(OUTCOME_COLOR[key], OUTCOME_WORDS[key]) for key in ("failed", "close", "passed", "crashed", "running")] + ([(AMBER, "Paused")] if data.get("pause_bands") else [])
    return [html.Span([html.Span(className="fo-swatch", style={"background": "transparent", "border": f"1.5px dotted {color}"} if word == "Paused" else {"background": color}), word]) for color, word in keys]


def render(data: dict[str, Any]) -> dict[str, Any]:
    """Every refreshable piece, keyed by component id, in OUTPUTS order (the layout and the 10 s callback both use it)."""
    pill = data["pill"]
    old = data["old_runs"]
    show_needs = bool(data["alerts"] or old)
    return {
        "fo-pill": [html.Span(className="fo-pill-dot"), pill["label"]],
        "fo-date": data["now_label"],
        "fo-headline": headline_children(data),
        "fo-tiles": tiles(data), "fo-running": running_cards(data), "fo-alerts": alert_cards(data),
        "fo-old-title": old["title"] if old else "", "fo-old-items": old_run_items(data), "fo-old-wrap": {"display": "block" if old else "none"},
        "fo-needs": {"display": "flex" if show_needs else "none"},
        "fo-queue-head": queue_head(data), "fo-queue": queue_rows(data),
        "fo-legend": legend_items(data),
        "fo-timeline": timeline_figure(data["timeline"], data["now_et"], data.get("pause_bands")), "fo-timeline-empty": timeline_empty(data["timeline"]), "fo-hourly-phone": hourly_figure(data["hourly"], True), "fo-hourly": hourly_figure(data["hourly"]),
        "fo-health": health_rows(data), "fo-health-checked": f"Checked {data['checked']}", "fo-log": log_rows(data), "fo-log-more": log_rows(data, rest=True),
    }


PAUSE_FAILED = "Could not reach the factory control, so nothing was changed. Try again in a minute."


def pause_button_props(data: dict[str, Any]) -> tuple[str, str, str]:
    """(label, variant, colour): outlined grey 'Pause testing' while testing runs, filled primary 'Resume testing' while paused."""
    return ("Resume testing", "filled", "gray") if data.get("paused") else ("Pause testing", "outline", "gray")


def handle_pause_action(trigger: str | None, paused: bool) -> tuple[Any, Any, Any]:
    """(modal opened, refresh stamp, alert children) for a press on the pause button, its confirm button or its cancel button."""
    if trigger == "fo-pause-cancel" or (trigger == "fo-pause-btn" and not paused):
        return trigger == "fo-pause-btn", no_update, []
    reply = gateway_client.resume_campaign() if trigger == "fo-pause-btn" else gateway_client.pause_campaign("from dashboard")
    if not isinstance(reply, dict) or not reply.get("ok"):
        message = ((reply or {}).get("error") or {}).get("message") if isinstance(reply, dict) else None
        return False, no_update, dmc.Alert(f"{PAUSE_FAILED}" + (f" ({message})" if message else ""), title="Pause / resume did not work", color="red", withCloseButton=True)
    return False, time.time(), []


def _pill_class(data: dict[str, Any]) -> str:
    return f"fo-pill {data['pill']['tone']}"


def _card(title: str, hint: str | None, *children: Any, **props: Any) -> html.Div:
    head = html.Div([html.Span(title, className="fo-h"), html.Span(hint, className="fo-muted")], className="fo-between") if hint is not None else None
    return html.Div([head, *children] if head else list(children), className="fo-card", **props)


def layout() -> html.Div:
    data = load_factory_overview()
    part = render(data)
    button = pause_button_props(data)
    legend = html.Div(part["fo-legend"], id="fo-legend", className="fo-legend")
    body = html.Div([
        html.Section([html.Div([html.Div(part["fo-date"], id="fo-date", className="fo-muted"), html.H1(part["fo-headline"], id="fo-headline", className="fo-title")]),
                      html.Div([html.Span(part["fo-pill"], id="fo-pill", className=_pill_class(data)), dmc.Button(button[0], id="fo-pause-btn", variant=button[1], color=button[2], size="sm"), html.A("All runs →", href="/factory/runs", className="fo-all-runs"), html.Span("Refreshes every 10 s", className="fo-muted")], className="fo-top-right")], className="fo-top"),
        html.Section(part["fo-tiles"], id="fo-tiles", className="fo-tiles"),
        html.Section([
            _card("Running now", ONE_AT_A_TIME, html.Div(part["fo-running"], id="fo-running", className="fo-col")),
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
            html.Span("← earlier", className="fo-muted fo-phone-only"),
            html.Span(part["fo-timeline-empty"], id="fo-timeline-empty", className="fo-muted fo-empty-note"),
            html.Div(dcc.Graph(id="fo-timeline", figure=part["fo-timeline"], config=GRAPH_CONFIG, style={"height": 76}), className="fo-scroll"),
            html.Span("Each block is one test run, coloured by how it ended. Hover for the idea, how long it took and the outcome; click to open its report. A gap means the factory sat idle.", className="fo-muted")],
            className="fo-card")),
        html.Section([
            _card("Runs per hour", "Last 48 hours", html.Div(dcc.Graph(id="fo-hourly", figure=part["fo-hourly"], config=GRAPH_CONFIG, style={"height": 190}), className="fo-desktop-only"),
                  html.Div(dcc.Graph(id="fo-hourly-phone", figure=part["fo-hourly-phone"], config={**GRAPH_CONFIG, "responsive": True}, responsive=True, style={"height": 190, "width": "100%"}), className="fo-phone-only"),
                  html.Span("Flat stretches are nights and weekends with nothing queued, not faults.", className="fo-muted")),
            _card("Health checks", None, html.Div([html.Span("Health checks", className="fo-h"), html.Span(part["fo-health-checked"], id="fo-health-checked", className="fo-muted")], className="fo-between"),
                  html.Div(part["fo-health"], id="fo-health")),
            _card("What happened", "Plain-language log", html.Div(part["fo-log"], id="fo-log"),
                  dmc.Collapse(html.Div(part["fo-log-more"], id="fo-log-more"), id="fo-log-collapse", opened=False),
                  dmc.Button("Show more", id="fo-log-toggle", variant="subtle", color="gray", size="compact-xs", style={"alignSelf": "flex-start", "display": "block" if len(data["log"]) > LOG_SHOWN else "none"})),
        ], className="fo-three"),
        dmc.Modal(html.Div([html.Span("The current test finishes; nothing new starts until you resume.", className="fo-body"),
                            html.Div([dmc.Button("Cancel", id="fo-pause-cancel", variant="default"), dmc.Button("Pause", id="fo-pause-confirm", color="gray")], className="fo-modal-buttons")], className="fo-col"),
                  id="fo-pause-modal", title="Pause testing?", opened=False, centered=True),
        html.Div(id="fo-notice"),
    ], className="fo-page")
    return html.Div([dcc.Interval(id="fo-tick", interval=REFRESH_MS), dcc.Store(id="fo-refresh"), dcc.Store(id="fo-paused", data=bool(data.get("paused"))), dcc.Location(id="fo-nav", refresh=True),
                     dmc.MantineProvider(body, theme=REPORT_THEME, forceColorScheme="dark")], className="fo-root", style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_callbacks(application: Any) -> None:
    """Standard Dash callbacks only: the 10 s refresh, the old-runs toggle, and click-to-open-report."""
    properties = {"fo-date": "children", "fo-headline": "children", "fo-pill": "children", "fo-tiles": "children", "fo-running": "children", "fo-alerts": "children", "fo-old-title": "children",
                  "fo-old-items": "children", "fo-old-wrap": "style", "fo-needs": "style", "fo-queue-head": "children", "fo-queue": "children", "fo-timeline": "figure", "fo-legend": "children", "fo-timeline-empty": "children", "fo-hourly": "figure", "fo-hourly-phone": "figure",
                  "fo-health": "children", "fo-health-checked": "children", "fo-log": "children", "fo-log-more": "children"}

    @application.callback([Output(key, properties[key]) for key in OUTPUTS] + [Output("fo-pill", "className"), Output("fo-pause-btn", "children"), Output("fo-pause-btn", "variant"), Output("fo-pause-btn", "color"), Output("fo-paused", "data")],
                          Input("fo-tick", "n_intervals"), Input("fo-refresh", "data"), prevent_initial_call=True)
    def refresh(_ticks: int | None, _stamp: float | None):
        data = load_factory_overview()
        part = render(data)
        return [part[key] for key in OUTPUTS] + [_pill_class(data), *pause_button_props(data), bool(data.get("paused"))]

    @application.callback(Output("fo-pause-modal", "opened"), Output("fo-refresh", "data"), Output("fo-notice", "children"),
                          Input("fo-pause-btn", "n_clicks"), Input("fo-pause-confirm", "n_clicks"), Input("fo-pause-cancel", "n_clicks"), State("fo-paused", "data"), prevent_initial_call=True)
    def pause_action(_press: int | None, _confirm: int | None, _cancel: int | None, paused: bool | None):
        return handle_pause_action(ctx.triggered_id, bool(paused))

    @application.callback(Output("fo-old-collapse", "opened"), Output("fo-old-toggle", "children"), Input("fo-old-toggle", "n_clicks"), State("fo-old-collapse", "opened"), prevent_initial_call=True)
    def toggle_old(_clicks: int | None, opened: bool):
        return (not opened), ("Show them" if opened else "Hide them")

    @application.callback(Output("fo-log-collapse", "opened"), Output("fo-log-toggle", "children"), Input("fo-log-toggle", "n_clicks"), State("fo-log-collapse", "opened"), prevent_initial_call=True)
    def toggle_log(_clicks: int | None, opened: bool):
        return (not opened), ("Show more" if opened else "Show less")

    @application.callback(Output("fo-nav", "pathname"), Output("fo-nav", "search"), Input("fo-timeline", "clickData"), prevent_initial_call=True)
    def open_report(click: dict[str, Any] | None):
        point = ((click or {}).get("points") or [{}])[0]
        custom = point.get("customdata") or []
        if len(custom) < 4 or not custom[3]:
            return no_update, no_update
        return "/report", f"?candidate_id={quote(str(custom[3]), safe='')}"



__all__ = ["layout", "register_callbacks"]
