"""Results workbench: one dark grid of every idea (or every setting tried). Thin Dash Mantine + Plotly + AG Grid layer over results_workbench_projection."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

import dash_ag_grid as dag
import dash_mantine_components as dmc
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html

from dashboard.results_workbench_projection import load_shortfall, load_workbench, newest_real_idea, page_of_settings
from dashboard.ui.idea_report import AMBER, BG, FAINT, GREEN, GRID_THEME, INDIGO, INNER, LINE, MUTED, PANEL, RED, REPORT_THEME, SANS, TEXT, TONE, test_card

GRIDS = (("ideas", False), ("ideas", True), ("settings", False), ("settings", True))  # (mode, phone layout)
BRUSHES = (("sharpe", "Sharpe"), ("worst_drop", "Worst drop (%)"), ("total_return", "Return (%)"), ("trades", "Trades"))
DOT = '<span style="display:inline-block;width:18px;height:6px;border-radius:2px;margin-right:3px;background:{}"></span>'
TYPE_ALL = "All strategy types"


def grid_id(mode: str, phone: bool) -> str:
    return f"wb-{mode}-{'phone' if phone else 'desk'}"


def _markdown_safe(text: str) -> str:
    """Titles come from agents: neutralise HTML and markdown so only our own link and dots render."""
    out = escape(str(text))
    for char in "\\`*_{}[]()#+-.!|":
        out = out.replace(char, "\\" + char)
    return out


def grid_rows(frame: pd.DataFrame, mode: str) -> list[dict[str, Any]]:
    """The frame as plain grid rows: the idea link with market and timeframe, five test dots, and one-value bar arrays."""
    if frame.empty:
        return []
    out = frame.copy()
    link = out["candidate_id"].map(lambda value: f"/report?candidate_id={quote(str(value), safe='')}")
    sub = out["market"].astype(str) + " · " + out["timeframe"].astype(str) + (" · " + out["setting"].astype(str) if mode == "settings" else "")
    out["idea_md"] = ["[" + _markdown_safe(title) + "](" + url + ")  \n" + _markdown_safe(text) for title, url, text in zip(out["title"], link, sub)]
    out["dots_html"] = out["dots"].map(lambda tones: "".join(DOT.format(TONE[tone]) for tone in tones))
    out = out.drop(columns=["dots"]).astype(object).where(out.notna(), None)
    return out.to_dict("records")


def _data_bar(scale: float, color: str, negative: str | None = None) -> dict[str, Any]:
    """A bar behind the number: dash-ag-grid's documented cellStyle function string, a CSS gradient sized to the value on one shared scale."""
    return {"function": "({background: 'linear-gradient(90deg, " + (f"' + (params.value < 0 ? '{negative}' : '{color}') + '" if negative else color) + " ' + Math.min(100, Math.abs(params.value || 0) / " + f"{scale:.6f}" + " * 100) + '%, transparent 0)', fontFamily: \"'Geist Mono', monospace\"})"}


def columns(phone: bool, bounds: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
    number = lambda fmt: {"function": f"d3.format('{fmt}')(params.value)"}  # noqa: E731  (dash-ag-grid documented d3 formatter)
    pct = {"function": "params.value == null ? '' : d3.format('+.1f')(params.value) + '%'"}
    drop = {"function": "params.value == null ? '' : d3.format('.1f')(params.value) + '%'"}
    mono = {"fontFamily": "'Geist Mono', ui-monospace, monospace"}
    scale_return = max(abs(bounds["total_return"][0]), abs(bounds["total_return"][1])) or 1.0
    scale_drop = max(abs(bounds["worst_drop"][0]), abs(bounds["worst_drop"][1])) or 1.0
    cols: list[dict[str, Any]] = [
        {"field": "idea_md", "headerName": "Idea", "cellRenderer": "markdown", "minWidth": 280, "flex": 1, "filter": "agTextColumnFilter", "cellStyle": {"lineHeight": "1.35", "paddingTop": "6px"},
         **({"pinned": "left", "width": 150, "minWidth": 150, "flex": None} if phone else {})},
        {"field": "sharpe", "headerName": "Sharpe", "width": 84 if phone else 110, "filter": "agNumberColumnFilter", "valueFormatter": number(".2f"), "cellStyle": mono, **({"pinned": "left"} if phone else {})},
        {"field": "total_return", "headerName": "Return", "width": 150, "filter": "agNumberColumnFilter", "valueFormatter": pct, "cellStyle": _data_bar(scale_return, "rgba(94,234,176,0.35)", "rgba(242,84,91,0.35)")},
        {"field": "worst_drop", "headerName": "Worst drop", "width": 150, "filter": "agNumberColumnFilter", "valueFormatter": drop, "cellStyle": _data_bar(scale_drop, "rgba(242,84,91,0.35)")},
        {"field": "trades", "headerName": "Trades", "width": 110, "filter": "agNumberColumnFilter", "valueFormatter": number(","), "cellStyle": mono},
        {"field": "dots_html", "headerName": "Five tests", "width": 150, "cellRenderer": "markdown", "sortable": False, "filter": False},
        {"field": "result", "headerName": "Result", "width": 190, "filter": "agTextColumnFilter"},
        {"field": "family", "headerName": "Strategy type", "width": 190, "filter": "agTextColumnFilter", "sort": "asc", "sortIndex": 0},
        {"field": "created_at", "headerName": "Submitted", "hide": True, "sort": "desc", "sortIndex": 1},
    ]
    return cols


def _bounds(frame: pd.DataFrame) -> dict[str, tuple[float, float]]:
    return {key: (float(frame[key].min()), float(frame[key].max())) if not frame.empty and frame[key].notna().any() else (0.0, 1.0) for key, _label in BRUSHES}


def _grid(mode: str, phone: bool, frame: pd.DataFrame, first: str | None) -> dag.AgGrid:
    options: dict[str, Any] = {"theme": GRID_THEME, "rowHeight": 54, "animateRows": False, "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                               "tooltipShowDelay": 300}
    props: dict[str, Any] = {}
    if mode == "ideas":
        props.update(rowData=grid_rows(frame, mode), getRowId="params.data.candidate_id",
                     selectedRows=[row for row in grid_rows(frame, mode) if row["candidate_id"] == first])  # opens on the newest real idea
    else:
        options.update(cacheBlockSize=100, maxBlocksInCache=10)
        props.update(rowModelType="infinite", getRowId="params.data.row_id")
    return dag.AgGrid(id=grid_id(mode, phone), columnDefs=columns(phone, _bounds(frame)), defaultColDef={"sortable": True, "resizable": True, "filter": True},
                      dashGridOptions=options, dangerously_allow_code=True, style={"height": 620}, **props)


def _histogram(frame: pd.DataFrame, key: str, low: float, high: float) -> go.Figure:
    values = frame[key].dropna() if not frame.empty else pd.Series(dtype=float)
    figure = go.Figure()
    for part, color in ((values[(values < low) | (values > high)], "#2C3038"), (values[(values >= low) & (values <= high)], INDIGO)):
        figure.add_trace(go.Histogram(x=part, marker_color=color, xbins=dict(start=float(values.min()) if len(values) else 0, end=float(values.max()) if len(values) else 1, size=float((values.max() - values.min()) / 20) or 1.0)))
    figure.update_layout(barmode="stack", bargap=0.1, showlegend=False, height=70, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         xaxis=dict(visible=False), yaxis=dict(visible=False), hovermode=False)
    return figure


def _range_text(low: float, high: float, full: tuple[float, float]) -> str:
    return "All" if (low, high) == full else f"{low:,.2f} to {high:,.2f}"


def brush_cards(frame: pd.DataFrame) -> list[dmc.Paper]:
    """Histogram plus range slider per number (dash-mantine RangeSlider + a Plotly histogram); hidden when there is no data."""
    cards = []
    for key, label in BRUSHES:
        if frame.empty or frame[key].dropna().empty:
            continue
        low, high = float(frame[key].min()), float(frame[key].max())
        cards.append(dmc.Paper([
            dmc.Group([dmc.Text(label, size="sm", c="#C4C8CF"), dmc.Text("All", size="xs", ff="monospace", c=INDIGO, id=f"wb-range-{key}")], justify="space-between"),
            dcc.Graph(id=f"wb-hist-{key}", figure=_histogram(frame, key, low, high), config={"displayModeBar": False, "staticPlot": True}, style={"height": 70}),
            dmc.RangeSlider(id=f"wb-slider-{key}", min=low, max=high, value=[low, high], step=(high - low) / 100 or 1, minRange=0, size="xs", color="indigo", label=None),
        ], p="md", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0}))
    return cards


def panel_body(item: dict[str, Any] | None) -> list[Any]:
    """Close-call side panel: how far the test fell short (same bar-and-tick card as the idea report) and the full-width link."""
    if not item:
        return []
    cards = [test_card(item["number"], {"stage": "shortfall", "label": item["label"], "status": "Close call", "run_id": True, "value": f"{entry['measured']}, needed {entry['needed']}",
                                        "fraction": entry["fraction"], "pass_line": 1.0, "line": entry["check"], "detail": {"periods": [1]}}) for entry in item["items"]]
    return [dmc.Badge("Close call", color="yellow", variant="light"), dmc.Text(item["title"], fw=600, size="md"), *cards,
            html.A(dmc.Button("Open full report →", fullWidth=True, color="indigo", size="md"), href=f"/report?candidate_id={quote(item['candidate_id'], safe='')}", style={"display": "block", "textDecoration": "none"})]


def results_workbench_layout(search: str | None = None) -> html.Div:
    data = load_workbench()
    ideas, settings = data["ideas"], data["settings"]
    if ideas.empty:
        body: list[Any] = [dmc.Paper(dmc.Text("No ideas have saved results yet.", size="sm", c=MUTED), p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}"})]
    else:
        first = newest_real_idea(ideas)
        head = dmc.Stack([dmc.Text("Results", size="xs", c=FAINT), dmc.Title("Results workbench", order=1, size=26, fw=600)], gap=4)
        controls = dmc.Group([
            dmc.SegmentedControl(id="wb-mode", value="ideas", data=[{"value": "ideas", "label": f"Ideas · {len(ideas):,}"}, {"value": "settings", "label": f"Every setting tried · {len(settings):,}"}]),
            dmc.Select(id="wb-type", value=TYPE_ALL, data=[TYPE_ALL, *sorted(ideas["family"].unique())], allowDeselect=False, w=260),
        ], gap="sm")
        brushes = brush_cards(ideas)
        def wrap(mode: str) -> dmc.Box:
            return dmc.Box([dmc.Box(_grid(mode, False, ideas if mode == "ideas" else settings, first), visibleFrom="sm"),
                            dmc.Box(_grid(mode, True, ideas if mode == "ideas" else settings, first), hiddenFrom="sm")], id=f"wb-wrap-{mode}", style={"display": "block" if mode == "ideas" else "none"})
        table = dmc.Paper([wrap("ideas"), wrap("settings")], radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0, "overflow": "hidden", "flex": "999 1 640px"})
        side = dmc.Paper(id="wb-panel", p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid #2A2E36", "minWidth": 0, "flex": "1 1 340px", "display": "none"})
        body = [head, controls, *([dmc.SimpleGrid(brushes, cols={"base": 1, "sm": 2, "lg": len(brushes)}, spacing="md")] if brushes else []),
                html.Div([table, side], style={"display": "flex", "flexWrap": "wrap", "gap": 14, "alignItems": "flex-start"})]
    return html.Div(dmc.MantineProvider(dmc.Stack(body, gap="md", p={"base": "sm", "sm": "lg"}, maw=1600, mx="auto", style={"minWidth": 0}), theme=REPORT_THEME, forceColorScheme="dark"),
                    style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_workbench_callbacks(application: Dash) -> None:
    """Standard Dash callbacks only: slider ranges and the strategy-type select drive the grids' filterModel, the toggle swaps grids, infinite grids fetch pages, a selection fills the panel."""
    keys = [key for key, _label in BRUSHES]

    @application.callback([Output(f"wb-hist-{key}", "figure") for key in keys] + [Output(f"wb-range-{key}", "children") for key in keys]
                          + [Output(grid_id(mode, phone), "filterModel") for mode, phone in GRIDS],
                          [Input(f"wb-slider-{key}", "value") for key in keys] + [Input("wb-type", "value"), State("wb-mode", "value")], prevent_initial_call=True)
    def brush(*args: Any):
        *ranges, strategy_type, mode = args
        frame = load_workbench()["ideas" if mode == "ideas" else "settings"]
        model: dict[str, Any] = {} if strategy_type == TYPE_ALL else {"family": {"filterType": "text", "type": "equals", "filter": strategy_type}}
        figures, labels = [], []
        for key, (low, high) in zip(keys, ranges):
            full = (float(frame[key].min()), float(frame[key].max()))
            figures.append(_histogram(frame, key, low, high))
            labels.append(_range_text(low, high, full))
            if (low, high) != full:
                model[key] = {"filterType": "number", "type": "inRange", "filter": low, "filterTo": high}
        return [*figures, *labels, *[model] * len(GRIDS)]

    @application.callback([Output(f"wb-slider-{key}", prop) for key in keys for prop in ("min", "max", "value")], Input("wb-mode", "value"), prevent_initial_call=True)
    def reset_sliders(mode: str):
        """A new mode has its own numbers: each slider spans the new data and starts fully open."""
        frame = load_workbench()["ideas" if mode == "ideas" else "settings"]
        out: list[Any] = []
        for key in keys:
            low, high = float(frame[key].min()), float(frame[key].max())
            out += [low, high, [low, high]]
        return out

    @application.callback(Output("wb-wrap-ideas", "style"), Output("wb-wrap-settings", "style"), Input("wb-mode", "value"))
    def swap(mode: str):
        return {"display": "block" if mode == "ideas" else "none"}, {"display": "block" if mode == "settings" else "none"}

    for phone in (False, True):
        @application.callback(Output(grid_id("settings", phone), "getRowsResponse"), Input(grid_id("settings", phone), "getRowsRequest"))
        def page(request: dict[str, Any] | None):
            return page_of_settings(load_workbench()["settings"].pipe(lambda frame: pd.DataFrame(grid_rows(frame, "settings"))), request or {})

    @application.callback(Output("wb-panel", "children"), Output("wb-panel", "style"), [Input(grid_id(mode, phone), "selectedRows") for mode, phone in GRIDS], State("wb-panel", "style"))
    def panel(*args: Any):
        *selections, style = args
        triggered = ctx.triggered_id
        order = [index for index, (mode, phone) in enumerate(GRIDS) if grid_id(mode, phone) == triggered] + list(range(len(GRIDS)))
        row = next((selections[index][0] for index in order if selections[index]), None)
        item = load_shortfall(row["candidate_id"]) if row else None
        return panel_body(item), {**(style or {}), "display": "block" if item else "none"}


__all__ = ["register_workbench_callbacks", "results_workbench_layout"]
