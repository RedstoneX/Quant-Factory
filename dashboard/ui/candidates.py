"""Production Candidates workspace in the accepted Quant Factory shell."""

from __future__ import annotations

import json

from typing import Any
from urllib.parse import parse_qs

import dash_ag_grid as dag
import dash_mantine_components as dmc
from dash import Input, Output, State, ctx, dcc, html, no_update
from dash_iconify import DashIconify

from dashboard.plain_labels import (
    CANT_TEST, FAILED_TESTING, LIFECYCLE_LABELS, LIFECYCLE_ORDER, lifecycle_label, plain_status,
)
from dashboard.candidates_projection import (
    load_candidate_detail,
    load_candidates_page,
    load_candidates_summary,
)
from dashboard.ui.layout import copy_id, page_header
from dashboard.ui.theme import COLUMN_DEFAULTS, grid_options, hide_when_narrow


HUMAN_LABELS = {
    "needs_review": "Needs review",
    "not_run": "Not run",
    "oos": "Out of sample",
    "walk_forward": "Walk-forward",
    "monte_carlo": "Monte Carlo",
}


def _human_label(value: Any) -> str:
    text = str(value or "not_run")
    return HUMAN_LABELS.get(text, text.replace("_", " ").title())


CANDIDATE_COLUMNS = [
    {"field": "title", "headerName": "Idea", "flex": 2, "filter": "agTextColumnFilter", "tooltipField": "candidate_id"},
    {"field": "symbol", "headerName": "Market", "flex": .6, "filter": "agTextColumnFilter"},
    {"field": "lifecycle", "headerName": "Status", "flex": .9, "filter": "agTextColumnFilter", "valueFormatter": {"function": "(" + json.dumps(LIFECYCLE_LABELS) + ")[params.value] || (params.value ? params.value.charAt(0).toUpperCase() + params.value.slice(1) : '—')"}},
    {"field": "sharpe", "headerName": "Out-of-sample Sharpe", "type": "numericColumn", "flex": 1, "filter": "agNumberColumnFilter", "sort": "desc", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(2)"}},
    {"field": "max_drawdown", "headerName": "Max drawdown", "type": "numericColumn", "flex": .8, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "retained", "headerName": "Kept out-of-sample", "type": "numericColumn", "flex": .9, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : params.value.toFixed(1) + '%'"}},
    {"field": "net_return", "headerName": "Net return", "type": "numericColumn", "flex": .75, "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '—' : (params.value > 0 ? '+' : '') + params.value.toFixed(1) + '%'"}},
    {"field": "robustness", "headerName": "Robustness", "flex": .78, "filter": "agTextColumnFilter"},
    {"field": "paper", "headerName": "Paper", "flex": .8, "filter": "agTextColumnFilter"},
]
MARKETS = [{"value": "all", "label": "All markets"}, {"value": "futures", "label": "Futures"}, {"value": "equities", "label": "Equities"}, {"value": "crypto", "label": "Crypto"}, {"value": "unclassified", "label": "Unclassified"}]
EVIDENCE = [{"value": "any", "label": "Any test result"}, {"value": "all_gates", "label": "Passed every test"}, {"value": "failed_oos", "label": "Failed on unseen data"}, {"value": "semantic_exception", "label": "Rules unclear"}]
STATE_COLORS = {"survivor": "teal", "rejected": "red", "crashed": "red", "blocked": "yellow", "needs_review": "yellow", "advancing": "blue"}


def _lifecycle_tabs(counts: dict[str, Any]) -> list[dict[str, str]]:
    return [{"value": key, "label": f"{LIFECYCLE_LABELS[key]} · {int(counts.get(key, 0)):,}"} for key in LIFECYCLE_ORDER]


def _icon(name: str) -> DashIconify:
    return DashIconify(icon=f"tabler:{name}", width=14)


def candidates_layout(search: str | None = None) -> html.Div:
    summary = load_candidates_summary()
    counts = summary.get("counts", {})
    requested_candidate = parse_qs((search or "").lstrip("?")).get("candidate_id", [None])[0]
    initial_detail = load_candidate_detail(requested_candidate) if requested_candidate else None
    # Open on the first tab that has ideas in it, unless a link asked for one idea.
    first_filled = next((key for key in LIFECYCLE_ORDER if int(counts.get(key, 0) or 0) > 0), "all")
    initial_lifecycle = str((initial_detail or {}).get("lifecycle") or first_filled)
    # Deep links select the exact record without narrowing the surrounding
    # universe. Operators must retain ranking and neighborhood context.
    initial_search = ""
    family_options = [{"value": "all", "label": "All families"}] + [{"value": family, "label": family} for family in summary.get("families", [])]
    saved_views = dmc.Menu([
        dmc.MenuTarget(dmc.Button("Saved views", leftSection=_icon("bookmark"), variant="default")),
        dmc.MenuDropdown([dmc.MenuItem("Passed, best first", id="view-survivors"), dmc.MenuItem("All ideas", id="view-all"), dmc.MenuItem("Failed testing", id="view-rejected")]),
    ], position="bottom-end")
    header = page_header(
        "Ideas", "Every idea the factory has received, best out-of-sample Sharpe first", saved_views,
        dmc.Button("Columns", id="candidate-columns", leftSection=_icon("columns"), variant="default"),
        dmc.Button("Submit an idea", id="candidate-submit"),
    )
    lifecycle = dmc.ScrollArea(dmc.SegmentedControl(id="candidate-lifecycle", value=initial_lifecycle, data=_lifecycle_tabs(counts), size="xs"), type="never", mb="sm")
    filters = dmc.Group([
        dmc.TextInput(id="candidate-search", value=initial_search, placeholder="Search idea, market, family…", leftSection=_icon("search"), size="xs", w=240, debounce=True, persistence=True, persistence_type="local", **{"aria-label": "Search ideas"}),
        dmc.Select(id="candidate-market", data=MARKETS, value="all", allowDeselect=False, size="xs", w=140, persistence=True, persistence_type="local", **{"aria-label": "Market"}),
        dmc.Select(id="candidate-family", data=family_options, value="all", allowDeselect=False, size="xs", w=160, persistence=True, persistence_type="local", **{"aria-label": "Family"}),
        dmc.Select(id="candidate-evidence", data=EVIDENCE, value="any", allowDeselect=False, size="xs", w=170, persistence=True, persistence_type="local", **{"aria-label": "Test result"}),
        dmc.Button("Compare selected · 0", id="compare-selected", variant="default", disabled=True, ml="auto"),
    ], gap="xs", mb="sm")
    grid = dag.AgGrid(
        id="candidate-grid", columnDefs=CANDIDATE_COLUMNS, rowModelType="infinite",
        defaultColDef={**COLUMN_DEFAULTS, "filter": True, "floatingFilter": False},
        dashGridOptions=grid_options(
            "No ideas match these filters.",
            rowSelection={"mode": "multiRow", "checkboxes": True, "headerCheckbox": False, "enableClickSelection": True},
            selectionColumnDef={"pinned": "left", "width": 38, "minWidth": 38, "maxWidth": 38, "resizable": False, "sortable": False},
            cacheBlockSize=50, maxBlocksInCache=4, rowBuffer=10, animateRows=False,
            suppressCellFocus=False, enableCellTextSelection=True, suppressPropertyNamesCheck=True,
        ),
        getRowId="params.data.candidate_id", className="candidates-grid", columnSize="responsiveSizeToFit",
        eventListeners=hide_when_narrow("symbol", "lifecycle", "max_drawdown", "retained", "net_return", "robustness", "paper"),
        persistence=True, persisted_props=["filterModel"], persistence_type="local",
    )
    detail = dmc.Paper([
        dmc.Stack([
            dmc.Badge("No selection", id="candidate-detail-state", color="gray"),
            dmc.Title("Pick an idea", id="candidate-detail-name", order=5, lineClamp=2),
            dmc.Text("Choose a row to see its results here.", id="candidate-detail-meta", size="xs", c="dimmed"),
        ], gap=6, p="md"),
        dmc.ScrollArea(dmc.Tabs(
            dmc.TabsList([dmc.TabsTab("Overview", value="overview"), dmc.TabsTab("Results", value="evidence"), dmc.TabsTab("History", value="history"), dmc.TabsTab("Origin", value="lineage")]),
            id="candidate-detail-tab", value="overview",
        ), type="never", px="md"),
        html.Div(id="candidate-detail-body", className="candidate-detail-body"),
    ], className="candidate-detail")
    workspace = html.Div([
        html.Div([grid, html.Footer([html.Span(id="candidate-page-count"), html.Span(id="candidate-total-count")], className="candidate-grid-footer")], className="candidate-grid-region"),
        detail,
    ], className="candidate-workspace")
    stores = [
        dcc.Store(id="candidate-summary", data=summary), dcc.Store(id="candidate-query", data={"lifecycle": initial_lifecycle, "market": "all", "family": "all", "evidence": "any", "search": initial_search}),
        dcc.Store(id="candidate-selection", data={"candidate_id": requested_candidate, "run_id": (initial_detail or {}).get("run_id")} if requested_candidate else None, storage_type="local"),
        dcc.Store(id="candidate-compare-selection", storage_type="local"),
        dcc.Store(id="candidate-detail-record"),
        dcc.Store(id="candidate-cache-reset"),
    ]
    return html.Div([*stores, header, html.Div([lifecycle, filters, workspace], className="candidates-body")], className="candidates-app")


def _fmt(value: Any, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1f}%" if percent else f"{float(value):.2f}"


def _outcome(record: dict[str, Any]) -> tuple[str, str]:
    lifecycle = record.get("lifecycle")
    campaign_state = record.get("campaign_state")
    label, why = plain_status(campaign_state, record.get("campaign_reason_code"))
    known = label != "Not in testing"
    if lifecycle == "survivor":
        if known:
            return label, why or "Needs your review before anything else happens"
        return "Passed — needs your review", "Paper trading is off; nothing is traded"
    if lifecycle == "advancing":
        if known:
            return label, why
        return f"Testing · {_human_label(record.get('stage'))} · {_human_label(record.get('run_status'))}", "Carries on automatically"
    if lifecycle == "duplicate":
        return label if known else "Duplicate", why or "Same rules as an idea already tested"
    if lifecycle == "crashed":
        return label if known else "Test crashed", why or "The test did not finish; this is not a result"
    if lifecycle == "blocked":
        return CANT_TEST, why or "The tester could not set this idea up"
    if lifecycle == "needs_review":
        return "Needs review", "Something in this idea needs your call"
    if lifecycle == "rejected":
        if known:
            return label, why
        if record.get("run_id") and record.get("screening_status") == "screened_out":
            return (
                f"{FAILED_TESTING} · {int(record.get('screened_out_count') or 0):,} of {int(record.get('screening_count') or 0):,} settings failed",
                "Stopped at the first check; later tests did not run",
            )
        return FAILED_TESTING, "Its results are kept"
    return "Idea received", "Next step not recorded yet"


def _screening_summary(record: dict[str, Any]) -> str:
    return (
        f"All {int(record.get('screening_count') or 0):,} settings tried failed the first check. "
        f"The best one returned {_fmt(record.get('screening_return'), percent=True)} "
        f"with Sharpe {_fmt(record.get('screening_sharpe'))} and "
        f"{_fmt(record.get('screening_max_drawdown'), percent=True)} maximum drawdown. "
        "Open Results for every setting and why each one failed."
    )


def _item(label: str, value: Any, note: Any = "") -> html.Div:
    return html.Div([html.Span(label), html.Strong(value) if isinstance(value, str) else value, html.Span(note)], className="candidate-evidence-item")


def _detail_body(record: dict[str, Any] | None, tab: str) -> list[Any]:
    if not record:
        return [dmc.Text("Pick an idea to see its results.", size="xs", c="dimmed", ta="center", py="xl")]
    outcome, next_state = _outcome(record)
    progression = record.get("progression") or []
    if tab == "evidence":
        screening = record.get("stage") == "screening"
        return [
            dmc.Title("Test results", order=5),
            _item("First-check Sharpe" if screening else "Out-of-sample Sharpe", _fmt(record.get("screening_sharpe") if screening else record.get("sharpe")), "Best setting" if screening else ""),
            _item("Maximum drawdown", _fmt(record.get("screening_max_drawdown") if screening else record.get("max_drawdown"), percent=True), "Best setting" if screening else ""),
            _item("Net return", _fmt(record.get("screening_return") if screening else record.get("net_return"), percent=True), "After trading costs"),
            _item("Settings", f"{int(record.get('screened_out_count') or 0):,} / {int(record.get('screening_count') or 0):,} failed" if screening else "—", "First check" if screening else ""),
            _item("Kept out-of-sample", _fmt(record.get("retained"), percent=True)),
            _item("Robustness", str(record.get("robustness"))),
        ]
    if tab == "history":
        return [dmc.Title("Test history", order=5), *[
            html.Div([html.Span(className=f"candidate-dot{' failed' if item.get('status') == 'failed' else ''}"), html.Div([html.Strong(_human_label(item.get("stage"))), copy_id(item.get("run_id"))]), html.Time(_human_label(item.get("status")))], className="candidate-stage-row")
            for item in progression
        ], *([] if progression else [dmc.Text("No test runs yet.", size="xs", c="dimmed")])]
    if tab == "lineage":
        return [
            dmc.Title("Where it came from", order=5),
            _item("Idea ID", copy_id(record.get("candidate_id"))),
            _item("Version", copy_id(record.get("candidate_version")), "Fingerprint of the rules"),
            _item("Settings ID", copy_id(record.get("configuration_id"))),
            _item("Latest run", copy_id(record.get("run_id")), _human_label(record.get("stage"))),
        ]
    return [
        _item("Outcome", outcome),
        _item("Next", next_state),
        html.Div(_screening_summary(record) if record.get("run_id") and record.get("screening_status") == "screened_out" else record.get("campaign_reason_detail") or record.get("error_summary") or record.get("description") or "No further notes.", className=f"candidate-explanation {record.get('lifecycle') or ''}"),
        dmc.Group([dmc.Button("Open Results", id="candidate-open-results", disabled=not record.get("run_id")), dmc.Button("See test results", id="candidate-open-evidence", variant="default")], gap=8, className="candidate-detail-actions"),
        dmc.Title("Tests passed so far", order=5, className="candidate-progression-title"),
        *[_item(_human_label(item.get("stage")), _human_label(item.get("status")), "✓" if item.get("status") == "succeeded" else "") for item in progression],
        *([] if progression else [dmc.Text("No tests have run yet.", size="xs", c="dimmed")]),
    ]


def register_candidate_callbacks(application: Any) -> None:
    application.clientside_callback(
        """async function(query) {
            const api = await dash_ag_grid.getApiAsync('candidate-grid');
            api.purgeInfiniteCache();
            return Date.now();
        }""",
        Output("candidate-cache-reset", "data"), Input("candidate-query", "data"),
        prevent_initial_call=True,
    )

    @application.callback(Output("candidate-lifecycle", "data"), Output("candidate-family", "data"), Input("candidate-summary", "data"))
    def render_summary(summary: dict[str, Any] | None):
        summary = summary or {}
        families = [{"value": "all", "label": "All families"}] + [{"value": family, "label": family} for family in summary.get("families", [])]
        return _lifecycle_tabs(summary.get("counts", {})), families

    @application.callback(
        Output("candidate-lifecycle", "value"), Output("candidate-market", "value"), Output("candidate-family", "value"), Output("candidate-evidence", "value"), Output("candidate-search", "value"),
        Input("view-survivors", "n_clicks"), Input("view-all", "n_clicks"), Input("view-rejected", "n_clicks"), Input("router-location", "search"), prevent_initial_call=True,
    )
    def apply_saved_view(*_clicks: Any):
        if ctx.triggered_id == "router-location":
            candidate_id = parse_qs(str(_clicks[-1] or "").lstrip("?")).get("candidate_id", [None])[0]
            detail = load_candidate_detail(candidate_id) if candidate_id else None
            if detail:
                return detail.get("lifecycle") or "all", "all", "all", "any", ""
            return no_update, no_update, no_update, no_update, no_update
        if ctx.triggered_id == "view-survivors":
            return "survivor", "all", "all", "all_gates", ""
        if ctx.triggered_id == "view-all":
            return "all", "all", "all", "any", ""
        if ctx.triggered_id == "view-rejected":
            return "rejected", "all", "all", "any", ""
        return no_update, no_update, no_update, no_update, no_update

    @application.callback(Output("candidate-query", "data"), Input("candidate-lifecycle", "value"), Input("candidate-market", "value"), Input("candidate-family", "value"), Input("candidate-evidence", "value"), Input("candidate-search", "value"))
    def update_query(lifecycle: str, market: str, family: str, evidence: str, search: str | None) -> dict[str, Any]:
        return {"lifecycle": lifecycle or "survivor", "market": market or "all", "family": family or "all", "evidence": evidence or "any", "search": search or ""}

    @application.callback(Output("candidate-grid", "getRowsResponse"), Output("candidate-page-count", "children"), Output("candidate-total-count", "children"), Input("candidate-grid", "getRowsRequest"), Input("candidate-query", "data"))
    def load_grid(request: dict[str, Any] | None, query: dict[str, Any] | None):
        if not request or not query:
            return no_update, no_update, no_update
        page = load_candidates_page(start=int(request.get("startRow") or 0), end=int(request.get("endRow") or 50), sort_model=request.get("sortModel"), filter_model=request.get("filterModel"), **query)
        total = int(page["rowCount"])
        return page, "" if total else "No ideas match these filters.", f"{total:,} ideas" if total else ""

    @application.callback(Output("candidate-selection", "data"), Input("candidate-grid", "selectedRows"), Input("candidate-grid", "getRowsResponse"), Input("router-location", "search"), State("candidate-selection", "data"), prevent_initial_call=True)
    def persist_primary_selection(selected_rows: list[dict[str, Any]] | None, response: dict[str, Any] | None, search: str | None, current: dict[str, Any] | None):
        if "router-location.search" in ctx.triggered_prop_ids:
            candidate_id = parse_qs((search or "").lstrip("?")).get("candidate_id", [None])[0]
            detail = load_candidate_detail(candidate_id) if candidate_id else None
            if detail:
                return {"candidate_id": candidate_id, "run_id": detail.get("run_id")}
        if "candidate-grid.selectedRows" in ctx.triggered_prop_ids and selected_rows:
            row = selected_rows[-1]; return {"candidate_id": row.get("candidate_id"), "run_id": row.get("run_id")}
        if current:
            return current
        rows = (response or {}).get("rowData") or []
        return {"candidate_id": rows[0].get("candidate_id"), "run_id": rows[0].get("run_id")} if rows else None

    @application.callback(Output("candidate-compare-selection", "data"), Input("candidate-grid", "selectedRows"), Input("router-location", "search"), State("candidate-compare-selection", "data"), prevent_initial_call=True)
    def persist_compare_selection(rows: list[dict[str, Any]] | None, search: str | None, current: list[dict[str, Any]] | None):
        if "router-location.search" in ctx.triggered_prop_ids and search == "?clear_compare=1":
            return []
        if rows is None:
            return current or []
        return [{"candidate_id": row.get("candidate_id"), "run_id": row.get("run_id"), "title": row.get("title")} for row in rows if row.get("lifecycle") == "survivor"]

    @application.callback(Output("compare-selected", "children"), Output("compare-selected", "disabled"), Input("candidate-compare-selection", "data"))
    def compare_state(rows: list[dict[str, Any]] | None):
        valid = [row for row in (rows or []) if row.get("run_id")]
        count = len(valid)
        return f"Compare selected · {count}", not 2 <= count <= 4

    @application.callback(Output("candidate-detail-record", "data"), Input("candidate-selection", "data"))
    def load_detail(selection: dict[str, Any] | None):
        return load_candidate_detail((selection or {}).get("candidate_id"))

    @application.callback(Output("candidate-detail-state", "children"), Output("candidate-detail-state", "color"), Output("candidate-detail-name", "children"), Output("candidate-detail-meta", "children"), Output("candidate-detail-body", "children"), Input("candidate-detail-record", "data"), Input("candidate-detail-tab", "value"))
    def render_detail(record: dict[str, Any] | None, tab: str):
        if not record:
            return "No selection", "gray", "Pick an idea", "Choose a row to see its results here.", _detail_body(None, tab)
        state = lifecycle_label(record.get("lifecycle") or "received")
        rank = f"Rank {record.get('rank')}" if record.get("rank") else ""
        meta = " · ".join(str(part) for part in (record.get("symbol"), record.get("family"), rank) if part)
        return state, STATE_COLORS.get(str(record.get("lifecycle")), "gray"), record.get("title") or "Untitled idea", meta, _detail_body(record, tab)

    @application.callback(Output("candidate-detail-tab", "value"), Input("candidate-open-evidence", "n_clicks", allow_optional=True), prevent_initial_call=True)
    def open_evidence(_clicks: int | None):
        return "evidence" if _clicks else no_update

    @application.callback(Output("candidate-grid", "columnDefs"), Input("candidate-columns", "n_clicks"), prevent_initial_call=True)
    def toggle_columns(clicks: int | None):
        compact = bool((clicks or 0) % 2)
        return [{**column, **({"hide": compact} if column["field"] in {"retained", "robustness", "paper"} else {})} for column in CANDIDATE_COLUMNS]


__all__ = ["candidates_layout", "register_candidate_callbacks"]
