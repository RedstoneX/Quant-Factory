"""Results workbench: one dark grid of every idea (or every setting tried). Thin Dash Mantine + Plotly + AG Grid (Community) layer over results_workbench_projection."""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import quote

import dash_ag_grid as dag
import dash_mantine_components as dmc
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html

from dashboard.results_workbench_projection import chip_tone, load_shortfall, load_workbench, newest_real_idea, page_of_settings
from dashboard.ui.idea_report import AMBER, BG, FAINT, GREEN, GRID_THEME, INDIGO, INNER, LINE, MUTED, PANEL, RED, REPORT_THEME, SANS, TEXT, TONE, test_card

GRIDS = (("ideas", False), ("ideas", True), ("settings", False), ("settings", True))  # (mode, phone layout)
BRUSHES = (("sharpe", "Sharpe"), ("worst_drop", "Worst drop (%)"), ("total_return", "Return (%)"), ("trades", "Trades"))
DOT = '<span style="display:inline-block;width:16px;height:6px;border-radius:2px;margin-right:3px;background:{}"></span>'
CHIP = ('<span style="display:inline-flex;align-items:center;height:20px;padding:0 8px;border-radius:999px;font-size:11px;font-weight:600;line-height:1;text-transform:uppercase;'
        'white-space:nowrap;background:{bg};color:{fg};border:{border}">{text}</span>')
TONE_BG = {"green": "rgba(94,234,176,0.14)", "amber": "rgba(245,184,65,0.14)", "red": "rgba(242,84,91,0.14)", "grey": "rgba(155,161,171,0.14)"}
TYPE_ALL = "All strategy types"
RESULT_ALL = "Any result"
SORTS = (("new", "Newest first", "created_at", "desc"), ("sharpe_desc", "Sharpe, high to low", "sharpe", "desc"), ("sharpe_asc", "Sharpe, low to high", "sharpe", "asc"), ("result", "Result, A to Z", "result", "asc"))
SHARPE_PHONE_WIDTH = 64  # fixed, right-aligned; the header shows "Sharpe" in full with the sort icon hidden by the narrow column
RESULT_COLUMN_WIDTH = 150  # fits the longest chip, PASSED THE GATES (16 upper-case characters at 11px bold, plus padding), on one line
SHELL_HEADER = "48px"
MONO = "'Geist Mono', ui-monospace, monospace"


def grid_id(mode: str, phone: bool) -> str:
    return f"wb-{mode}-{'phone' if phone else 'desk'}"


def _markdown_safe(text: str) -> str:
    """Titles come from agents: neutralise HTML and markdown so only our own link and chips render."""
    out = escape(str(text))
    for char in "\\`*_{}[]()#+-.!|":
        out = out.replace(char, "\\" + char)
    return out


def chip_html(text: str) -> str:
    """The single overall status as a 20px chip like the idea report's header chip (Mantine light badge); Crashed is a red outline. A grid cell cannot host a Mantine component."""
    tone = chip_tone(text)
    outline = text == "Crashed"
    return CHIP.format(bg="transparent" if outline else TONE_BG[tone], fg=TONE[tone], border=f"1px solid {TONE[tone]}" if outline else "0", text=escape(text))


def _stat(label: str, value: str) -> dmc.Box:
    return dmc.Box([dmc.Text(label, size="xs", c=FAINT), dmc.Text(value, size="md", ff="monospace")], p="sm", bg=INNER, style={"borderRadius": 10, "minWidth": 0})


def stat_strip(row: dict[str, Any]) -> dmc.SimpleGrid:
    """Return, worst drop, Sharpe and trades from the row's own numbers; a dash where there is none."""
    number = lambda key, fmt: "—" if row.get(key) is None else fmt.format(row[key])  # noqa: E731
    return dmc.SimpleGrid([_stat("Return", number("total_return", "{:+.1f}%")), _stat("Worst drop", number("worst_drop", "{:.1f}%")),
                           _stat("Sharpe", number("sharpe", "{:.2f}")), _stat("Trades", number("trades", "{:,.0f}"))], cols=2, spacing="xs")


def grid_rows(frame: pd.DataFrame, mode: str) -> list[dict[str, Any]]:
    """The frame as plain grid rows: idea link with market, timeframe and strategy type, result chip, five test dots; no-trade ideas get a grey chip."""
    if frame.empty:
        return []
    out = frame.copy()
    link = out["candidate_id"].map(lambda value: f"/report?candidate_id={quote(str(value), safe='')}")
    sub = out["market"].astype(str) + " · " + out["timeframe"].astype(str) + " · " + out["family"].astype(str) + (" · " + out["setting"].astype(str) if mode == "settings" else "")
    out["idea_md"] = ["[" + _markdown_safe(title) + "](" + url + ")\n\n" + _markdown_safe(text) for title, url, text in zip(out["title"], link, sub)]
    no_trades = out["trades"].fillna(0) == 0
    out["result"] = ["No trades" if empty else text for empty, text in zip(no_trades, out["result"])]
    out["dots_html"] = [("".join(DOT.format(TONE["grey"]) for _ in tones) if empty else "".join(DOT.format(TONE[tone]) for tone in tones)) for empty, tones in zip(no_trades, out["dots"])]  # no trades: five grey dots
    out["result_html"] = [chip_html(text) for text in out["result"]]
    out["idea_phone_md"] = [name.split("\n\n")[0] + "\n\n" + chip + " " + _markdown_safe(text) for name, chip, text in zip(out["idea_md"], out["result_html"], sub)]  # phone cell: name, then chip and details on one line
    out = out.drop(columns=["dots"]).astype(object).where(out.notna(), None)
    return out.to_dict("records")


def _expression(body: str) -> dict[str, str]:
    """dash-ag-grid's documented function-string form: a JavaScript expression with `params` in scope."""
    return {"function": body}


NO_BAR = "(params.value == null || (params.data && params.data.trades === 0))"
ZERO_LINE = "linear-gradient(90deg, transparent calc(50% - 0.5px), #3A3F48 0, #3A3F48 calc(50% + 0.5px), transparent 0) left bottom / 100% 4px no-repeat"


def _return_bar(scale: float) -> dict[str, Any]:
    """4px bar along the cell bottom (CSS gradient in cellStyle): grows from a centre zero line, green to the right, red to the left."""
    w = f"Math.min(50, Math.abs(params.value) / {scale:.6f} * 50)"
    right = f"'linear-gradient(90deg, transparent 50%, {GREEN} 50%, {GREEN} ' + (50 + {w}) + '%, transparent 0) left bottom / 100% 4px no-repeat'"
    left = f"'linear-gradient(90deg, transparent ' + (50 - {w}) + '%, {RED} ' + (50 - {w}) + '%, {RED} 50%, transparent 0) left bottom / 100% 4px no-repeat'"
    return _expression(f"{NO_BAR} ? {{}} : {{background: (params.value >= 0 ? {right} : {left}) + ', {ZERO_LINE}'}}")


def _drop_bar(scale: float) -> dict[str, Any]:
    """4px red bar along the cell bottom, from the left, scaled to the column maximum."""
    w = f"Math.min(100, Math.abs(params.value) / {scale:.6f} * 100)"
    return _expression(f"{NO_BAR} ? {{}} : {{background: 'linear-gradient(90deg, {RED} 0, {RED} ' + {w} + '%, transparent 0) left bottom / 100% 4px no-repeat'}}")


# Sharpe in mono: green at or above the pass line stored with the idea's screening rules, amber within 0.2 below it, grey otherwise.
SHARPE_STYLE = _expression(
    f"(params.value == null || !params.data || params.data.sharpe_line == null || params.data.trades === 0) ? {{fontFamily: \"{MONO}\", display: 'flex', alignItems: 'center'}} : "
    f"{{fontFamily: \"{MONO}\", display: 'flex', alignItems: 'center', color: params.value >= params.data.sharpe_line ? '{GREEN}' : params.value >= params.data.sharpe_line - 0.2 ? '{AMBER}' : '{MUTED}'}}")


def columns(phone: bool, bounds: dict[str, tuple[float, float]]) -> list[dict[str, Any]]:
    empty = "(params.data && params.data.trades === 0) || params.value == null"
    fmt = lambda pattern, suffix="": _expression(f"{empty} ? '—' : d3.format('{pattern}')(params.value) + '{suffix}'")  # noqa: E731  (dash-ag-grid documented d3 formatter)
    mono = {"fontFamily": MONO}
    scale_return = max(abs(bounds["total_return"][0]), abs(bounds["total_return"][1])) or 1.0
    scale_drop = max(abs(bounds["worst_drop"][0]), abs(bounds["worst_drop"][1])) or 1.0
    idea = {"field": "idea_md", "headerName": "Idea", "cellRenderer": "markdown", "minWidth": 110 if phone else 200, "flex": 1, "filter": "agTextColumnFilter", "tooltipField": "title",
            "cellStyle": {"lineHeight": "1.35", "paddingTop": "6px", **({"display": "flex", "alignItems": "center"} if phone else {})}, **({"wrapText": True, "autoHeight": True} if phone else {})}
    sharpe = {"field": "sharpe", "headerName": "Sharpe", "width": 92, "filter": "agNumberColumnFilter", "valueFormatter": fmt(".2f"), "cellStyle": SHARPE_STYLE}
    chip = {"field": "result_html", "headerName": "Result", "width": RESULT_COLUMN_WIDTH + (14 if phone else 0), "cellStyle": {"display": "flex", "alignItems": "center", **({"paddingRight": "14px"} if phone else {})}, "cellRenderer": "markdown", "filter": "agTextColumnFilter", "filterValueGetter": _expression("params.data.result")}
    hidden = [{"field": "family", "hide": True, "filter": "agTextColumnFilter"}, {"field": "created_at", "headerName": "Submitted", "hide": True, "sort": "desc"}]  # newest first
    if phone:  # phone: Idea (name, then chip and details) and Sharpe; Result is hidden and sorted or filtered from the Filters drawer
        idea.update(valueGetter=_expression("params.data ? params.data.idea_phone_md : null"), filterValueGetter=_expression("params.data ? params.data.idea_md : null"), minWidth=110)
        sharpe.update(width=SHARPE_PHONE_WIDTH, suppressHeaderFilterButton=True, type="rightAligned", cellStyle=_expression(SHARPE_STYLE["function"].replace("alignItems: 'center'", "alignItems: 'center', justifyContent: 'flex-end'")))
        return [idea, sharpe, {"field": "result", "hide": True, "filter": "agTextColumnFilter"}, *hidden]
    return [idea, sharpe,
            {"field": "total_return", "headerName": "Return", "width": 100, "filter": "agNumberColumnFilter", "valueFormatter": fmt("+.1f", "%"), "cellStyle": _return_bar(scale_return)},
            {"field": "worst_drop", "headerName": "Worst drop", "width": 118, "filter": "agNumberColumnFilter", "valueFormatter": fmt(".1f", "%"), "cellStyle": _drop_bar(scale_drop)},
            {"field": "trades", "headerName": "Trades", "width": 92, "filter": "agNumberColumnFilter", "valueFormatter": fmt(","), "cellStyle": mono},
            {"field": "dots_html", "headerName": "Five tests", "width": 100, "cellRenderer": "markdown", "sortable": False, "filter": False}, chip, *hidden]


def _bounds(frame: pd.DataFrame) -> dict[str, tuple[float, float]]:
    return {key: (float(frame[key].min()), float(frame[key].max())) if not frame.empty and frame[key].notna().any() else (0.0, 1.0) for key, _label in BRUSHES}


def _grid(mode: str, phone: bool, frame: pd.DataFrame, first: str | None) -> dag.AgGrid:
    options: dict[str, Any] = {"theme": GRID_THEME, "rowHeight": 54, "animateRows": False, "rowSelection": {"mode": "singleRow", "checkboxes": False, "enableClickSelection": True},
                               "tooltipShowDelay": 300, "pagination": True, "paginationPageSize": 50, "paginationPageSizeSelector": False}
    props: dict[str, Any] = {}
    if mode == "ideas":
        rows = grid_rows(frame, mode)
        props.update(rowData=rows, getRowId="params.data.candidate_id")
        if not phone:  # opens on the newest real idea; the phone grid starts with nothing selected so its drawer stays shut
            props.update(selectedRows=[row for row in rows if row["candidate_id"] == first])
    else:
        options.update(cacheBlockSize=50, maxBlocksInCache=10)
        props.update(rowModelType="infinite", getRowId="params.data.row_id")
    return dag.AgGrid(id=grid_id(mode, phone), columnDefs=columns(phone, _bounds(frame)), defaultColDef={"sortable": True, "resizable": True, "filter": True}, className="wb-grid",
                      dashGridOptions=options, dangerously_allow_code=True, style={"height": f"calc(100vh - {SHELL_HEADER})"}, **props)


def _histogram(frame: pd.DataFrame, key: str, low: float, high: float) -> go.Figure:
    values = frame[key].dropna() if not frame.empty else pd.Series(dtype=float)
    figure = go.Figure()
    bins = dict(start=float(values.min()) if len(values) else 0, end=float(values.max()) if len(values) else 1, size=float((values.max() - values.min()) / 20) or 1.0)
    for part, opacity in ((values[(values < low) | (values > high)], 0.3), (values[(values >= low) & (values <= high)], 1.0)):  # bars outside the range fade to 30%
        figure.add_trace(go.Histogram(x=part, marker=dict(color=INDIGO, opacity=opacity), xbins=bins))
    figure.update_layout(barmode="stack", bargap=0.1, showlegend=False, height=70, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         xaxis=dict(visible=False), yaxis=dict(visible=False), hovermode=False)
    return figure


def _range_text(low: float, high: float, full: tuple[float, float]) -> str:
    return "All" if (low, high) == full else f"{low:,.3g} – {high:,.3g}"


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


def panel_body(row: dict[str, Any] | None, item: dict[str, Any] | None) -> list[Any]:
    """Side panel for the selected row: the chip, the name, for a close call how far it fell short (the idea report's bar card, bar only), and the full-width link."""
    if not row:
        return []
    chip = dmc.Badge(row["result"], color=TONE[chip_tone(row["result"])], variant="outline" if row["result"] == "Crashed" else "light", h=20, size="sm")
    cards = [test_card(item["number"], {"stage": "shortfall", "label": item["label"], "status": "Close call", "run_id": None, "value": f"{entry['measured']}, needed {entry['needed']}",
                                        "fraction": entry["fraction"], "pass_line": 1.0, "line": entry["check"], "detail": {"periods": [1]}}) for entry in (item or {}).get("items", [])]
    return [chip, dmc.Text(row["title"], fw=600, size="md"), stat_strip(row), *cards,
            html.A(dmc.Button("Open full report →", fullWidth=True, color="indigo", size="md"), href=f"/report?candidate_id={quote(row['candidate_id'], safe='')}", style={"display": "block", "textDecoration": "none"})]


def results_workbench_layout(search: str | None = None) -> html.Div:
    data = load_workbench()
    ideas, settings = data["ideas"], data["settings"]
    if ideas.empty:
        body: list[Any] = [dmc.Paper(dmc.Text("No ideas have saved results yet.", size="sm", c=MUTED), p="lg", radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}"})]
    else:
        first = newest_real_idea(ideas)
        head = dmc.Stack([dmc.Text("Results", size="xs", c=FAINT), dmc.Title("Results", order=1, size=26, fw=600)], gap=4)
        controls = dmc.Group([
            dmc.SegmentedControl(id="wb-mode", value="ideas", data=[{"value": "ideas", "label": f"Ideas · {len(ideas):,}"}, {"value": "settings", "label": f"Every setting tried · {len(settings):,}"}]),
            dmc.Select(id="wb-type", value=TYPE_ALL, data=[TYPE_ALL, *sorted(ideas["family"].unique())], allowDeselect=False, w=260),
            dmc.Button("Filters", id="wb-filters-button", variant="default", hiddenFrom="sm"),
        ], gap="sm")
        brushes = brush_cards(ideas)
        results = sorted({"No trades" if empty else text for empty, text in zip(ideas["trades"].fillna(0) == 0, ideas["result"])})
        phone_filters = dmc.SimpleGrid([dmc.Select(id="wb-result", label="Result", value=RESULT_ALL, data=[RESULT_ALL, *results], allowDeselect=False),
                                        dmc.Select(id="wb-sort", label="Sort by", value=SORTS[0][0], data=[{"value": value, "label": label} for value, label, *_ in SORTS], allowDeselect=False)],
                                       cols=2, spacing="md", hiddenFrom="sm")  # phone only: the Result column is hidden, so its sort and filter live here
        filters = dmc.Collapse(dmc.Stack([phone_filters, dmc.SimpleGrid(brushes, cols={"base": 1, "sm": 2, "lg": len(brushes)}, spacing="md")], gap="md"), id="wb-filters", opened=False, className="wb-filters") if brushes else None

        def wrap(mode: str) -> dmc.Box:
            return dmc.Box([dmc.Box(_grid(mode, False, ideas if mode == "ideas" else settings, first), visibleFrom="sm"),
                            dmc.Box(_grid(mode, True, ideas if mode == "ideas" else settings, first), hiddenFrom="sm")], id=f"wb-wrap-{mode}", style={"display": "block" if mode == "ideas" else "none"})
        table = dmc.Paper([wrap("ideas"), wrap("settings")], radius="lg", bg=PANEL, style={"border": f"1px solid {LINE}", "minWidth": 0, "overflow": "hidden", "flex": "1 1 0"})
        side = dmc.Box(dmc.Paper(id="wb-panel", p="lg", radius="lg", bg=PANEL, style={"border": "1px solid #2A2E36", "display": "none"}), visibleFrom="sm", style={"flex": "0 0 300px", "minWidth": 0})
        drawer = dmc.Drawer(dmc.Stack(id="wb-drawer-body", gap="sm"), id="wb-drawer", position="bottom", size="auto", styles={"content": {"flex": "0 0 auto", "height": "auto", "maxHeight": "70vh"}}, opened=False, withCloseButton=True, hiddenFrom="sm")
        body = [head, controls, *([filters] if filters else []), html.Div([table, side], style={"display": "flex", "gap": 14, "alignItems": "flex-start"}), drawer]
    return html.Div(dmc.MantineProvider(dmc.Stack(body, gap="md", p={"base": "sm", "sm": "lg"}, maw=1600, mx="auto", style={"minWidth": 0}), theme=REPORT_THEME, forceColorScheme="dark"),
                    style={"background": BG, "minHeight": "100vh", "fontFamily": SANS, "color": TEXT})


def register_workbench_callbacks(application: Dash) -> None:
    """Standard Dash callbacks only: slider ranges and the strategy-type select drive the grids' filterModel, the toggle swaps grids, infinite grids fetch pages, a selection fills the panel or the phone drawer."""
    keys = [key for key, _label in BRUSHES]

    @application.callback([Output(f"wb-hist-{key}", "figure") for key in keys] + [Output(f"wb-range-{key}", "children") for key in keys]
                          + [Output(grid_id(mode, phone), "filterModel") for mode, phone in GRIDS] + [Output("wb-filters-button", "children")],
                          [Input(f"wb-slider-{key}", "value") for key in keys] + [Input("wb-type", "value"), Input("wb-result", "value"), State("wb-mode", "value")], prevent_initial_call=True)
    def brush(*args: Any):
        *ranges, strategy_type, result, mode = args
        frame = load_workbench()["ideas" if mode == "ideas" else "settings"]
        model: dict[str, Any] = {} if strategy_type == TYPE_ALL else {"family": {"filterType": "text", "type": "equals", "filter": strategy_type}}
        if result != RESULT_ALL:
            model["result"] = {"filterType": "text", "type": "equals", "filter": result}
        figures, labels = [], []
        for key, (low, high) in zip(keys, ranges):
            full = (float(frame[key].min()), float(frame[key].max()))
            figures.append(_histogram(frame, key, low, high))
            labels.append(_range_text(low, high, full))
            if (low, high) != full:
                model[key] = {"filterType": "number", "type": "inRange", "filter": low, "filterTo": high}
        return [*figures, *labels, *[model] * len(GRIDS), f"Filters · {len(model)}" if model else "Filters"]

    @application.callback([Output(grid_id(mode, True), "columnState") for mode in ("ideas", "settings")], Input("wb-sort", "value"), prevent_initial_call=True)
    def sort_phone(choice: str):
        """AG Grid's documented column state: one hidden-or-shown state per phone column with the chosen sort on one of them."""
        _value, _label, field, direction = next(item for item in SORTS if item[0] == choice)
        state = [{"colId": col, "hide": col not in ("idea_md", "sharpe"), "sort": direction if col == field else None} for col in ("idea_md", "sharpe", "result", "family", "created_at")]
        return [state] * 2

    @application.callback(Output("wb-filters", "opened"), Input("wb-filters-button", "n_clicks"), State("wb-filters", "opened"), prevent_initial_call=True)
    def toggle_filters(_clicks: int, opened: bool):
        return not opened

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

    @application.callback(Output("wb-panel", "children"), Output("wb-panel", "style"), Output("wb-drawer-body", "children"), Output("wb-drawer", "opened"),
                          [Input(grid_id(mode, phone), "selectedRows") for mode, phone in GRIDS], State("wb-panel", "style"))
    def panel(*args: Any):
        *selections, style = args
        triggered = ctx.triggered_id
        order = [index for index, (mode, phone) in enumerate(GRIDS) if grid_id(mode, phone) == triggered] + list(range(len(GRIDS)))
        row = next((selections[index][0] for index in order if selections[index]), None)
        body = panel_body(row, load_shortfall(row["candidate_id"]) if row else None)
        from_phone = isinstance(triggered, str) and triggered.endswith("phone")  # a tap on the phone grid opens the bottom drawer
        return body, {**(style or {}), "display": "block" if row else "none"}, body, bool(row) and from_phone

    @application.callback([Output(grid_id(mode, True), "deselectAll") for mode in ("ideas", "settings")], Input("wb-drawer", "opened"), prevent_initial_call=True)
    def release_selection(opened: bool):
        """Closing the drawer clears the phone selection so the same row can be tapped again."""
        return [not opened] * 2


__all__ = ["register_workbench_callbacks", "results_workbench_layout"]
