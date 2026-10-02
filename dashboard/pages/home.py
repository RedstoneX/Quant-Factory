"""Truthful, side-effect-free Home overview for Milestone 23.

The application integration layer supplies snapshots that it has already read.
This module never probes a service, opens the research database, accesses a
credential, or launches work.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Iterable, Mapping

import dash_ag_grid as dag
import plotly.graph_objects as go
from dash import dcc, html

from dashboard.health import (
    HomeHealthReading,
    normalize_health_reading,
    redact_credential_health_reading,
)
from dashboard.components.research_campaign import research_campaign_overview
from dashboard.project_status import DashboardProjectStatus, PROJECT_STATUS
from orchestration import RunEvent, RunSummary
@dataclass(frozen=True)
class HomeHealthView:
    area: str
    label: str
    status: str
    detail: str
    checked_at: str
    stale: bool


@dataclass(frozen=True)
class HomeRunView:
    run_id: str
    label: str
    status: str
    timestamp: str
    detail: str


@dataclass(frozen=True)
class HomeFailureView:
    run_id: str
    summary: str
    timestamp: str


@dataclass(frozen=True)
class HomeWorkflowStep:
    label: str
    href: str
    state: str


@dataclass(frozen=True)
class HomeAction:
    label: str
    description: str
    href: str
    kind: str


@dataclass(frozen=True)
class HomeDatasetView:
    label: str
    status: str
    availability: str
    earliest: str
    latest: str
    missing_sessions: tuple[str, ...]


@dataclass(frozen=True)
class HomeViewModel:
    milestone: str
    milestone_status: str
    discovery_gate: str
    health: tuple[HomeHealthView, ...]
    run: HomeRunView | None
    failures: tuple[HomeFailureView, ...]
    workflow: tuple[HomeWorkflowStep, ...]
    action: HomeAction
    subtitle: str
    health_readings: tuple[HomeHealthReading, ...]
    health_stale_after_seconds: float
    health_refresh_interval_ms: int
    history_rows: tuple[dict[str, object], ...]
    datasets: tuple[HomeDatasetView, ...]
    as_of: datetime


_HEALTH_AREAS = (
    ("database", "Research database"),
    ("worker", "Worker / orchestrator"),
    ("provider", "Data provider"),
    ("cache", "Research cache"),
    ("artifact", "Artifact storage"),
    ("credential", "Credentials"),
)

_WORKFLOW_STEPS = (
    ("Home", "/"),
    ("Ideas", "/research/ideas"),
    ("Set up", "/research/setup"),
    ("Run test", "/research/run-test"),
    ("Results", "/research/backtest-results"),
    ("Compare", "/research/compare-backtests"),
)

_ACTIVE_RUN_STATUSES = frozenset(
    {"created", "queued", "running", "retrying", "submission_unknown"}
)
_FAILED_RUN_STATUSES = frozenset({"failed", "timed_out"})


def build_home_view_model(
    *,
    health_readings: Iterable[HomeHealthReading] = (),
    recent_runs: tuple[RunSummary, ...] = (),
    recent_events: tuple[RunEvent, ...] = (),
    selected_run_id: str | None = None,
    idea_captured: bool = False,
    configuration_selected: bool = False,
    as_of: datetime | None = None,
    stale_after: timedelta = timedelta(minutes=15),
    health_refresh_interval_ms: int = 30_000,
    history_rows: Iterable[Mapping[str, object]] = (),
    catalog_snapshot: tuple[object, tuple[object, ...], object] | None = None,
    project_status: DashboardProjectStatus = PROJECT_STATUS,
) -> HomeViewModel:
    """Derive one truthful Home snapshot from already-read application state."""

    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    if health_refresh_interval_ms <= 0:
        raise ValueError("health_refresh_interval_ms must be positive")
    resolved_as_of = as_of or datetime.now(timezone.utc)
    if resolved_as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")

    safe_health_readings = tuple(
        redact_credential_health_reading(reading)
        if reading.area == "credential"
        else reading
        for reading in health_readings
    )
    health = _health_views(safe_health_readings, resolved_as_of, stale_after)
    run = _selected_active_or_latest_run(recent_runs, selected_run_id)
    failures = _recent_failures(recent_runs, recent_events)
    workflow_index, action = _workflow_and_action(
        recent_runs=recent_runs,
        failures=failures,
        idea_captured=idea_captured,
        configuration_selected=configuration_selected,
    )
    workflow = tuple(
        HomeWorkflowStep(
            label=label,
            href=href,
            state=(
                "Completed"
                if index < workflow_index
                else "Current"
                if index == workflow_index
                else "Unavailable"
            ),
        )
        for index, (label, href) in enumerate(_WORKFLOW_STEPS)
    )
    return HomeViewModel(
        milestone=(
            f"Milestone {project_status.current_milestone_number} — "
            f"{project_status.current_milestone_title}"
        ),
        milestone_status=project_status.current_milestone_status,
        discovery_gate=" ".join(
            (
                project_status.current_milestone_status,
                project_status.strategy_status,
                project_status.workspace_status,
            )
        ),
        health=health,
        run=_run_view(run),
        failures=failures,
        workflow=workflow,
        action=action,
        subtitle=project_status.home_subtitle,
        health_readings=safe_health_readings,
        health_stale_after_seconds=stale_after.total_seconds(),
        health_refresh_interval_ms=health_refresh_interval_ms,
        history_rows=tuple(dict(row) for row in history_rows),
        datasets=_dataset_views(catalog_snapshot),
        as_of=resolved_as_of,
    )


def layout(view_model: HomeViewModel | None = None) -> html.Div:
    """Render the chart-first Research Atlas from already-read state."""

    from dashboard.components.research_path import strategy_research_path

    model = view_model or build_home_view_model()
    rows = _ordered_history(model.history_rows)
    return html.Div(
        [
            html.Header(
                [
                    html.Div(
                        [
                            html.P("RESEARCH / DASHBOARD", className="page-eyebrow"),
                            html.H1("Research Atlas"),
                            html.P(
                                "See what research is exploring, what survived, and what needs you.",
                                className="atlas-subtitle",
                            ),
                        ],
                        className="atlas-title",
                    ),
                    html.Div(
                        [
                            _status_item("Edge status", f"{_qualified_count(rows)} qualified"),
                            _status_item("Live runs", str(_live_count(rows))),
                            _status_item("Completed", str(_completed_count(rows))),
                            _status_item("Needs you", str(_needs_count(model))),
                        ],
                        className="atlas-status-rail",
                    ),
                    html.Div(
                        [
                            html.Span(
                                _factory_readiness(model.health),
                                className="atlas-factory-state",
                            ),
                            html.Span("·", **{"aria-hidden": "true"}),
                            html.Span(_updated_label(rows, model.health)),
                            dcc.Link("Capture idea", href="/research/ideas", className="atlas-header-action"),
                        ],
                        className="atlas-header-meta",
                    ),
                ],
                className="atlas-header",
            ),
            html.Div(strategy_research_path("/"), className="atlas-contract-only"),
            html.Div(
                f"{model.milestone}. {model.milestone_status}. {model.discovery_gate}",
                id="home-discovery-gate",
                className="atlas-contract-only",
            ),
            dcc.Store(
                id="health-observation-snapshot",
                data={
                    "readings": [
                        {
                            "area": reading.area,
                            "status": reading.status,
                            "detail": reading.detail,
                            "checked_at": reading.checked_at,
                        }
                        for reading in model.health_readings
                    ],
                    "stale_after_seconds": model.health_stale_after_seconds,
                },
                storage_type="memory",
            ),
            dcc.Interval(
                id="health-freshness-interval",
                interval=model.health_refresh_interval_ms,
                n_intervals=0,
            ),
            research_campaign_overview(model=model, rows=rows, outcome_for=_row_outcome),
            html.Main(
                [
                    html.Div(
                        [
                            _panel(
                                "Research Landscape",
                                "Risk-adjusted evidence across every persisted candidate",
                                dcc.Graph(
                                    figure=_research_landscape_figure(rows),
                                    config=_GRAPH_CONFIG,
                                    className="atlas-graph atlas-graph-large",
                                    style={"height": "320px"},
                                ),
                                panel_class="atlas-landscape-panel atlas-panel-dark",
                            ),
                            _panel(
                                "Generalization Map",
                                "Screening evidence versus out-of-sample evidence",
                                dcc.Graph(
                                    figure=_generalization_figure(rows),
                                    config=_GRAPH_CONFIG,
                                    className="atlas-graph atlas-graph-large",
                                    style={"height": "320px"},
                                ),
                            ),
                        ],
                        className="atlas-grid atlas-grid-primary",
                    ),
                    html.Div(
                        [
                            _runs_panel(rows),
                            _latest_finding_panel(rows),
                        ],
                        id="home-current-run",
                        className="atlas-grid atlas-grid-operational",
                    ),
                    html.Div(
                        [
                            _panel(
                                "Evidence Survival",
                                "How many candidates advance through each evidence gate",
                                dcc.Graph(
                                    figure=_evidence_survival_figure(rows),
                                    config=_GRAPH_CONFIG,
                                    className="atlas-graph atlas-graph-compact",
                                    style={"height": "235px"},
                                ),
                            ),
                            _readiness_panel(model.datasets, model.health, model.as_of),
                            _research_stops_panel(rows, model),
                        ],
                        className="atlas-grid atlas-grid-secondary",
                    ),
                ],
                className="atlas-content",
            ),
        ],
        className="page-container home-page research-atlas-page",
    )


_GRAPH_CONFIG = {
    "displayModeBar": False,
    "responsive": True,
    "scrollZoom": False,
}
def _panel(
    title: str,
    subtitle: str,
    content: object,
    *,
    panel_class: str = "",
) -> html.Section:
    return html.Section(
        [
            html.Div(
                [html.H2(title), html.P(subtitle)],
                className="atlas-panel-heading",
            ),
            content,
        ],
        className=f"atlas-panel {panel_class}".strip(),
    )


def _status_item(label: str, value: str) -> html.Div:
    return html.Div(
        [
            html.Span(label),
            html.Strong(value),
        ],
        className="atlas-status-item",
    )


def _ordered_history(
    rows: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    return tuple(
        sorted(
            (dict(row) for row in rows),
            key=lambda row: str(row.get("created_at") or ""),
            reverse=True,
        )
    )


def _dataset_views(
    snapshot: tuple[object, tuple[object, ...], object] | None,
) -> tuple[HomeDatasetView, ...]:
    if snapshot is None:
        return ()
    health_rows = snapshot[1]
    candidates: dict[tuple[str, str], HomeDatasetView] = {}
    for health in health_rows:
        manifest = getattr(health, "manifest", None)
        if manifest is None:
            continue
        metadata = getattr(manifest, "metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        symbol = str(getattr(manifest, "symbol", "Dataset"))
        timeframe = str(getattr(manifest, "timeframe", ""))
        missing = metadata.get("missing_sessions", ())
        if not isinstance(missing, (list, tuple)):
            missing = ()
        view = HomeDatasetView(
            label=f"{symbol} {timeframe}".strip(),
            status=str(getattr(manifest, "status", "unknown")),
            availability=str(getattr(health, "availability", "Unavailable")),
            earliest=str(metadata.get("earliest_timestamp") or metadata.get("coverage_start") or ""),
            latest=str(metadata.get("latest_timestamp") or metadata.get("latest_completed_session") or ""),
            missing_sessions=tuple(str(value) for value in missing),
        )
        key = (symbol, timeframe)
        current = candidates.get(key)
        if current is None or (
            view.availability.lower().startswith("available")
            and not current.availability.lower().startswith("available")
        ):
            candidates[key] = view
    priority = {symbol: index for index, symbol in enumerate(("MES", "MNQ", "SPY", "QQQ"))}
    return tuple(
        sorted(
            candidates.values(),
            key=lambda view: (priority.get(view.label.split()[0], 99), view.label),
        )[:4]
    )


def _text(row: Mapping[str, object], name: str, fallback: str = "Unavailable") -> str:
    value = row.get(name)
    if value is None or not str(value).strip():
        return fallback
    return str(value).strip()


def _number(row: Mapping[str, object], name: str) -> float | None:
    value = row.get(name)
    if isinstance(value, bool) or value is None:
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    return resolved if math.isfinite(resolved) else None


def _percent(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "—"
    sign = "+" if signed else ""
    return f"{value * 100:{sign}.2f}%"


def _decimal(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _integer(value: float | None) -> str:
    return "—" if value is None else f"{int(value):,}"


def _row_outcome(row: Mapping[str, object]) -> str:
    haystack = " ".join(
        _text(row, key, "").lower()
        for key in ("status", "review", "evidence", "metric_basis")
    )
    if any(word in haystack for word in ("qualified", "approved", "accepted")):
        return "Qualified"
    if any(word in haystack for word in ("screened out", "rejected", "failed", "timed out", "invalid")):
        return "Rejected"
    if any(word in haystack for word in ("running", "queued", "retrying", "passed", "registered", "succeeded")):
        return "Advancing"
    return "Insufficient"


def _qualified_count(rows: tuple[dict[str, object], ...]) -> int:
    return sum(_row_outcome(row) == "Qualified" for row in rows)


def _live_count(rows: tuple[dict[str, object], ...]) -> int:
    live = ("created", "queued", "running", "retrying", "submission unknown")
    return sum(_text(row, "status", "").lower() in live for row in rows)


def _completed_count(rows: tuple[dict[str, object], ...]) -> int:
    active = ("created", "queued", "running", "retrying", "submission unknown")
    return sum(_text(row, "status", "").lower() not in active for row in rows)


def _needs_count(model: HomeViewModel) -> int:
    if model.failures:
        return len(model.failures)
    return 0 if model.action.kind == "wait" else 1


def _factory_readiness(health: tuple[HomeHealthView, ...]) -> str:
    essentials = [
        item for item in health if item.area in {"database", "cache", "artifact"}
    ]
    ready = bool(essentials) and all(
        item.status.lower() == "available" and not item.stale for item in essentials
    )
    return "Factory ready" if ready else "Factory readiness incomplete"


def _updated_label(
    rows: tuple[dict[str, object], ...], health: tuple[HomeHealthView, ...]
) -> str:
    value = _text(rows[0], "created_at", "") if rows else ""
    if not value:
        value = next((item.checked_at for item in health if item.checked_at != "Not checked"), "")
    if not value:
        return "No persisted update"
    return f"Updated {value.replace('T', ' ')[:16]} UTC"


def _base_figure(
    *, margin: dict[str, int] | None = None, dark: bool = False
) -> go.Figure:
    foreground = "#dfe9f6" if dark else "#526173"
    grid = "rgba(180,202,229,.18)" if dark else "#e9eef5"
    line = "rgba(198,216,239,.55)" if dark else "#cfd8e6"
    figure = go.Figure()
    figure.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Inter, ui-sans-serif, system-ui, sans-serif", "color": foreground, "size": 11},
        margin=margin or {"l": 48, "r": 18, "t": 28, "b": 42},
        hoverlabel={"bgcolor": "#172237", "font": {"color": "#f8fafc"}},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    figure.update_xaxes(gridcolor=grid, zeroline=False, linecolor=line)
    figure.update_yaxes(gridcolor=grid, zeroline=False, linecolor=line)
    return figure


def _empty_figure(message: str) -> go.Figure:
    figure = _base_figure(margin={"l": 18, "r": 18, "t": 18, "b": 18})
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font={"size": 13, "color": "#7a8798"},
        align="center",
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    return figure


def _research_landscape_figure(rows: tuple[dict[str, object], ...]) -> go.Figure:
    plotted = [
        row
        for row in rows
        if _number(row, "sharpe_ratio") is not None
        and _number(row, "max_drawdown") is not None
    ]
    if not plotted:
        return _empty_figure("No persisted runs contain both Sharpe and drawdown evidence yet.")

    figure = _base_figure(dark=True)
    colors = {
        "Qualified": "#12b886",
        "Advancing": "#4c6ef5",
        "Rejected": "#fa5252",
        "Insufficient": "#f59f00",
    }
    for outcome in colors:
        group = [row for row in plotted if _row_outcome(row) == outcome]
        if not group:
            continue
        trades = [_number(row, "number_of_trades") or 0 for row in group]
        sizes = [max(12, min(34, 10 + math.sqrt(value) / 2)) for value in trades]
        custom = [
            [
                _text(row, "strategy"),
                _text(row, "instrument"),
                _text(row, "stage"),
                _integer(_number(row, "number_of_trades")),
                _percent(_number(row, "total_return"), signed=True),
                _percent(_number(row, "win_rate")),
                _text(row, "rejection_reasons", _text(row, "evidence")),
            ]
            for row in group
        ]
        figure.add_trace(
            go.Scatter(
                x=[abs(_number(row, "max_drawdown") or 0) * 100 for row in group],
                y=[_number(row, "sharpe_ratio") for row in group],
                mode="markers",
                name=outcome,
                marker={
                    "size": sizes,
                    "color": colors[outcome],
                    "opacity": 0.83,
                    "line": {"color": "#ffffff", "width": 1.5},
                },
                customdata=custom,
                hovertemplate=(
                    "<b>%{customdata[0]}</b> · %{customdata[1]}<br>"
                    "%{customdata[2]}<br>Sharpe %{y:.2f} · Max drawdown %{x:.2f}%<br>"
                    "Trades %{customdata[3]} · Return %{customdata[4]} · Win rate %{customdata[5]}<br>"
                    "%{customdata[6]}<extra></extra>"
                ),
            )
        )
    figure.add_hline(y=0, line_dash="dot", line_color="#9aa7b8")
    figure.update_xaxes(title="Maximum drawdown (%)")
    figure.update_yaxes(title="Sharpe ratio")
    return figure


def _generalization_figure(rows: tuple[dict[str, object], ...]) -> go.Figure:
    grouped: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in reversed(rows):
        stage = _text(row, "stage", "").lower()
        key = (_text(row, "strategy"), _text(row, "instrument"))
        if "screen" in stage:
            grouped[key]["screen"] = row
        elif "out-of-sample" in stage or stage == "oos":
            grouped[key]["oos"] = row
    pairs = [
        (key, stages["screen"], stages["oos"])
        for key, stages in grouped.items()
        if "screen" in stages
        and "oos" in stages
        and _number(stages["screen"], "sharpe_ratio") is not None
        and _number(stages["oos"], "sharpe_ratio") is not None
    ]
    if not pairs:
        return _empty_figure("No paired screening and out-of-sample evidence is persisted yet.")

    figure = _base_figure()
    x_values = [_number(screen, "sharpe_ratio") or 0 for _, screen, _ in pairs]
    y_values = [_number(oos, "sharpe_ratio") or 0 for _, _, oos in pairs]
    extent = max(1.0, *(abs(value) for value in x_values + y_values))
    figure.add_trace(
        go.Scatter(
            x=[-extent, extent],
            y=[-extent, extent],
            mode="lines",
            line={"color": "#b8c2d1", "dash": "dash"},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="markers",
            marker={"size": 14, "color": "#4c6ef5", "line": {"color": "#ffffff", "width": 2}},
            customdata=[[key[0], key[1]] for key, _, _ in pairs],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>Screening %{x:.2f}<br>OOS %{y:.2f}<extra></extra>",
            showlegend=False,
        )
    )
    figure.update_xaxes(title="Screening Sharpe", range=[-extent * 1.1, extent * 1.1])
    figure.update_yaxes(title="Out-of-sample Sharpe", range=[-extent * 1.1, extent * 1.1])
    return figure


_STAGES = (
    ("Screened", ("screen", "fixture")),
    ("OOS", ("out-of-sample", "oos")),
    ("Walk-forward", ("walk-forward",)),
    ("Robustness", ("robustness", "monte carlo")),
)


def _stage_index(row: Mapping[str, object]) -> int:
    stage = _text(row, "stage", "").lower()
    for index, (_, aliases) in enumerate(_STAGES):
        if any(alias in stage for alias in aliases):
            return index
    return 0


def _evidence_survival_figure(rows: tuple[dict[str, object], ...]) -> go.Figure:
    candidates: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        candidates[(_text(row, "strategy"), _text(row, "instrument"))].append(row)
    if not candidates:
        return _empty_figure("Evidence survival will appear after the first persisted run.")

    reached = [0] * len(_STAGES)
    rejected = [0] * len(_STAGES)
    insufficient = [0] * len(_STAGES)
    qualified = 0
    for candidate_rows in candidates.values():
        final_stage = max(_stage_index(row) for row in candidate_rows)
        final_row = max(candidate_rows, key=lambda row: _stage_index(row))
        for index in range(final_stage + 1):
            reached[index] += 1
        outcome = _row_outcome(final_row)
        if outcome == "Rejected":
            rejected[final_stage] += 1
        elif outcome == "Qualified":
            qualified += 1
        elif outcome != "Advancing":
            insufficient[final_stage] += 1

    labels = [stage[0] for stage in _STAGES] + ["Qualified", "Rejected", "Insufficient"]
    colors = ["#4c6ef5", "#4263eb", "#364fc7", "#2f3e9e", "#12b886", "#fa5252", "#f59f00"]
    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []
    link_colors: list[str] = []
    for index in range(len(_STAGES) - 1):
        if reached[index + 1]:
            sources.append(index)
            targets.append(index + 1)
            values.append(reached[index + 1])
            link_colors.append("rgba(76,110,245,.35)")
    for index, count in enumerate(rejected):
        if count:
            sources.append(index); targets.append(len(_STAGES) + 1); values.append(count); link_colors.append("rgba(250,82,82,.36)")
    for index, count in enumerate(insufficient):
        if count:
            sources.append(index); targets.append(len(_STAGES) + 2); values.append(count); link_colors.append("rgba(245,159,0,.36)")
    if qualified:
        sources.append(len(_STAGES) - 1); targets.append(len(_STAGES)); values.append(qualified); link_colors.append("rgba(18,184,134,.38)")
    figure = _base_figure(margin={"l": 8, "r": 8, "t": 12, "b": 8})
    figure.add_trace(
        go.Sankey(
            arrangement="snap",
            node={"label": labels, "color": colors, "pad": 13, "thickness": 13, "line": {"color": "#ffffff", "width": 1}},
            link={
                "source": sources,
                "target": targets,
                "value": values,
                "color": link_colors,
                "hovertemplate": (
                    "%{source.label} → %{target.label}<br>"
                    "%{value} candidate(s)<extra></extra>"
                ),
            },
        )
    )
    return figure


def _runs_panel(rows: tuple[dict[str, object], ...]) -> html.Section:
    row_data = [
        {
            "candidate": f"{_text(row, 'strategy')} · {_text(row, 'instrument')} · {_text(row, 'stage')}",
            "progress": f"{_text(row, 'status')} · {_text(row, 'evidence')}",
            "trades": _integer(_number(row, "number_of_trades")),
            "return": _percent(_number(row, "total_return"), signed=True),
            "sharpe": _decimal(_number(row, "sharpe_ratio")),
            "drawdown": _percent(_number(row, "max_drawdown")),
            "updated": _text(row, "created_at").replace("T", " ")[:16],
        }
        for row in rows[:5]
    ]
    grid = dag.AgGrid(
        id="home-live-runs-grid",
        rowData=row_data,
        columnDefs=[
            {"field": "candidate", "headerName": "Candidate · market · stage", "flex": 2.3, "minWidth": 210},
            {"field": "progress", "headerName": "Progress", "flex": 1.5, "minWidth": 150},
            {"field": "trades", "headerName": "Trades", "width": 88},
            {"field": "return", "headerName": "Return", "width": 92},
            {"field": "sharpe", "headerName": "Sharpe", "width": 82},
            {"field": "drawdown", "headerName": "Max DD", "width": 92},
            {"field": "updated", "headerName": "Updated", "width": 130},
        ],
        defaultColDef={"sortable": True, "resizable": True, "suppressMovable": True},
        dashGridOptions={
            "domLayout": "autoHeight",
            "rowHeight": 40,
            "headerHeight": 35,
            "suppressNoRowsOverlay": False,
            "suppressCellFocus": True,
        },
        className="ag-theme-quartz atlas-runs-grid",
    )
    return _panel(
        "Live Research Runs",
        "The work being done now, with the evidence produced by each run",
        grid,
        panel_class="atlas-runs-panel",
    )


def _latest_finding_panel(rows: tuple[dict[str, object], ...]) -> html.Section:
    if not rows:
        content = html.P("No persisted research finding is available yet.", className="atlas-empty")
    else:
        row = rows[0]
        from dashboard.pages.compare_backtests import results_query_href

        reason = _text(row, "rejection_reasons", _text(row, "evidence"))
        content = html.Div(
            [
                html.Div(
                    [
                        html.Span(_row_outcome(row), className=f"atlas-outcome atlas-outcome-{_row_outcome(row).lower()}"),
                        html.Small(_text(row, "created_at").replace("T", " ")[:16]),
                    ],
                    className="atlas-finding-state",
                ),
                html.H3(f"{_text(row, 'strategy')} · {_text(row, 'instrument')}"),
                html.P(reason, className="atlas-finding-reason"),
                html.Div(
                    [
                        _finding_metric("Return", _percent(_number(row, "total_return"), signed=True)),
                        _finding_metric("Sharpe", _decimal(_number(row, "sharpe_ratio"))),
                        _finding_metric("Max DD", _percent(_number(row, "max_drawdown"))),
                        _finding_metric("Trades", _integer(_number(row, "number_of_trades"))),
                    ],
                    className="atlas-finding-metrics",
                ),
                dcc.Link("Open full evidence →", href=results_query_href(_text(row, "run_id", "")), className="atlas-text-link"),
            ]
        )
    return _panel(
        "Latest Research Finding",
        "The newest persisted result—not a promotion decision",
        content,
        panel_class="atlas-finding-panel",
    )


def _finding_metric(label: str, value: str) -> html.Div:
    return html.Div([html.Small(label), html.Strong(value)])


def _month_starts(as_of: datetime, count: int = 9) -> tuple[datetime, ...]:
    months: list[datetime] = []
    year = as_of.year
    month = as_of.month
    for _ in range(count):
        months.append(datetime(year, month, 1, tzinfo=timezone.utc))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return tuple(reversed(months))


def _coverage_month(value: str) -> str:
    return value[:7] if len(value) >= 7 else ""


def _dataset_month_state(dataset: HomeDatasetView, month: str) -> tuple[int, str]:
    start = _coverage_month(dataset.earliest)
    end = _coverage_month(dataset.latest)
    if not start or not end or month < start or month > end:
        return 0, "Unavailable"
    if any(_coverage_month(session) == month for session in dataset.missing_sessions):
        return 3, "Gap"
    if not dataset.availability.lower().startswith("available"):
        return 0, "Unavailable"
    if dataset.status.lower() != "validated" or month in {start, end}:
        return 2, "Partial"
    return 1, "Validated"


def _data_readiness_figure(
    datasets: tuple[HomeDatasetView, ...], as_of: datetime
) -> go.Figure:
    if not datasets:
        return _empty_figure("No cataloged dataset readiness is available.")
    months = _month_starts(as_of)
    keys = [month.strftime("%Y-%m") for month in months]
    labels = [month.strftime("%b") for month in months]
    states = [[_dataset_month_state(dataset, key) for key in keys] for dataset in datasets]
    z = [[state[0] for state in row] for row in states]
    custom = [[state[1] for state in row] for row in states]
    figure = _base_figure(margin={"l": 70, "r": 8, "t": 24, "b": 8})
    figure.add_trace(
        go.Heatmap(
            z=z,
            x=labels,
            y=[dataset.label for dataset in datasets],
            customdata=custom,
            zmin=0,
            zmax=3,
            colorscale=[
                [0.0, "#adb5bd"],
                [0.1666, "#adb5bd"],
                [0.1667, "#20c997"],
                [0.5, "#20c997"],
                [0.5001, "#fcc419"],
                [0.8333, "#fcc419"],
                [0.8334, "#ff6b6b"],
                [1.0, "#ff6b6b"],
            ],
            showscale=False,
            xgap=2,
            ygap=2,
            hovertemplate="<b>%{y}</b> · %{x}<br>%{customdata}<extra></extra>",
        )
    )
    figure.update_xaxes(side="top", fixedrange=True)
    figure.update_yaxes(autorange="reversed", fixedrange=True)
    return figure


def _readiness_panel(
    datasets: tuple[HomeDatasetView, ...],
    health: tuple[HomeHealthView, ...],
    as_of: datetime,
) -> html.Section:
    return html.Section(
        [
            html.Div(
                [html.H2("Data Readiness"), html.P("Current read-only checks for research dependencies")],
                className="atlas-panel-heading",
            ),
            dcc.Graph(
                figure=_data_readiness_figure(datasets, as_of),
                config=_GRAPH_CONFIG,
                className="atlas-graph atlas-readiness-graph",
                style={"height": "172px"},
            ),
            html.Div(
                [
                    _legend_item("Validated", "validated"),
                    _legend_item("Partial", "partial"),
                    _legend_item("Gap", "gap"),
                    _legend_item("Unavailable", "unavailable"),
                ],
                className="atlas-readiness-legend",
                **{"aria-label": "Data readiness status key"},
            ),
            html.Div(
                _health_cards(health),
                id="home-health-cards",
                className="atlas-contract-only",
            ),
        ],
        id="home-health-summary",
        className="atlas-panel atlas-readiness-panel",
    )


def _legend_item(label: str, state: str) -> html.Span:
    return html.Span([html.I(className=f"atlas-key atlas-key-{state}"), label])


def _stop_category(reason: str) -> str:
    value = reason.lower()
    if "sharpe" in value:
        return "Sharpe gate"
    if "total_return" in value or "annualized_return" in value or "return" in value:
        return "Return gate"
    if "trade" in value:
        return "Insufficient trades"
    if "robust" in value:
        return "Robustness"
    if any(word in value for word in ("data", "manifest", "artifact", "configuration")):
        return "Data quality"
    return "Other evidence"


def _stop_counts(rows: tuple[dict[str, object], ...]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        if _row_outcome(row) != "Rejected":
            continue
        reasons = _text(row, "rejection_reasons", "")
        if reasons:
            counts.update(_stop_category(reason) for reason in reasons.split("|") if reason.strip())
        else:
            counts[_stop_category(_text(row, "evidence"))] += 1
    return counts


def _research_stops_figure(rows: tuple[dict[str, object], ...]) -> go.Figure:
    counts = _stop_counts(rows)
    if not counts:
        return _empty_figure("No failed evidence gates are recorded yet.")
    ordered = counts.most_common()
    figure = _base_figure(margin={"l": 112, "r": 20, "t": 10, "b": 30})
    figure.add_trace(
        go.Bar(
            x=[count for _, count in ordered][::-1],
            y=[label for label, _ in ordered][::-1],
            orientation="h",
            marker={"color": "#ff8787", "line": {"color": "#fa5252", "width": 1}},
            text=[str(count) for _, count in ordered][::-1],
            textposition="outside",
            hovertemplate="%{y}: %{x} failed gate(s)<extra></extra>",
        )
    )
    figure.update_xaxes(dtick=1, title="Failed gates")
    figure.update_yaxes(title=None)
    return figure


def _research_stops_panel(
    rows: tuple[dict[str, object], ...], model: HomeViewModel
) -> html.Section:
    if model.failures:
        actions: list[object] = [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong("Run failure"),
                            html.P(failure.summary),
                            html.Small(failure.timestamp),
                        ]
                    ),
                    dcc.Link(
                        "Inspect →",
                        href=f"/research/backtest-results?run_id={failure.run_id}",
                        id="home-primary-action" if index == 0 else None,
                        className="atlas-text-link",
                    ),
                ],
                className="atlas-action-row atlas-action-row-link",
            )
            for index, failure in enumerate(model.failures)
        ]
    else:
        actions = [
            html.Div(
                [
                    html.Div([html.Strong(model.action.label), html.P(model.action.description)]),
                    dcc.Link("Open →", href=model.action.href, id="home-primary-action", className="atlas-text-link"),
                ],
                className="atlas-action-row atlas-action-row-link",
            )
        ]
    return html.Section(
        [
            html.Div(
                [html.H2("Why Research Stops"), html.P("Failed gates across stopped runs; one run can fail more than one")],
                className="atlas-panel-heading",
            ),
            dcc.Graph(
                figure=_research_stops_figure(rows),
                config=_GRAPH_CONFIG,
                className="atlas-graph atlas-stops-graph",
                style={"height": "145px"},
            ),
            html.Div(
                [html.Div([html.H3("Needs You"), html.Span(str(_needs_count(model)))], className="atlas-needs-heading"), *actions],
                id="home-attention-failures",
                className="atlas-needs-you",
            ),
            html.Div(id="home-next-safe-action", className="atlas-contract-only"),
        ],
        className="atlas-panel atlas-stops-panel",
    )


def _health_views(
    readings: Iterable[HomeHealthReading],
    as_of: datetime,
    stale_after: timedelta,
) -> tuple[HomeHealthView, ...]:
    supplied = {reading.area: reading for reading in readings}
    return tuple(
        _health_view(area, label, supplied.get(area), as_of, stale_after)
        for area, label in _HEALTH_AREAS
    )


def _health_view(
    area: str,
    label: str,
    reading: HomeHealthReading | None,
    as_of: datetime,
    stale_after: timedelta,
) -> HomeHealthView:
    if reading is not None and area == "credential":
        reading = redact_credential_health_reading(reading)
    safe_detail = reading.detail if reading is not None else ""
    if reading is None:
        detail = (
            safe_detail
            if safe_detail
            else "No read-only health result was supplied for this overview."
        )
        return HomeHealthView(
            area=area,
            label=label,
            status="Not checked",
            detail=detail,
            checked_at="Not checked",
            stale=False,
        )
    status = reading.status.strip() or "Not checked"
    normalized, stale = normalize_health_reading(
        HomeHealthReading(
            area=reading.area,
            status=status,
            detail=safe_detail,
            checked_at=reading.checked_at,
        ),
        observed_at=as_of,
        stale_after=stale_after,
    )
    return HomeHealthView(
        area=area,
        label=label,
        status=normalized.status,
        detail=normalized.detail,
        checked_at=normalized.checked_at or "Not checked",
        stale=stale,
    )


def _selected_active_or_latest_run(
    runs: tuple[RunSummary, ...], selected_run_id: str | None
) -> RunSummary | None:
    if selected_run_id is not None:
        selected = next((run for run in runs if run.run_id == selected_run_id), None)
        if selected is not None:
            return selected
    return next(
        (run for run in runs if run.status.lower() in _ACTIVE_RUN_STATUSES),
        runs[0] if runs else None,
    )


def _run_view(run: RunSummary | None) -> HomeRunView | None:
    if run is None:
        return None
    status = run.status.replace("_", " ").title()
    timestamp = run.completed_at or run.started_at or run.created_at
    strategy = run.strategy_id.replace("_", " ").title()
    detail = run.error_summary or "Open the recorded run for persisted evidence and status."
    return HomeRunView(
        run_id=run.run_id,
        label=f"{strategy} · {status}",
        status=status,
        timestamp=timestamp,
        detail=detail,
    )


def _recent_failures(
    runs: tuple[RunSummary, ...], events: tuple[RunEvent, ...]
) -> tuple[HomeFailureView, ...]:
    failures = [
        HomeFailureView(
            run_id=run.run_id,
            summary=run.error_summary or "The run failed without a recorded summary.",
            timestamp=run.completed_at or run.started_at or run.created_at,
        )
        for run in runs
        if run.status.lower() in _FAILED_RUN_STATUSES
    ]
    failed_run_ids = {failure.run_id for failure in failures}
    failures.extend(
        HomeFailureView(
            run_id=event.run_id,
            summary=event.message,
            timestamp=event.timestamp,
        )
        for event in events
        if event.severity.lower() == "error" and event.run_id not in failed_run_ids
    )
    return tuple(failures[:3])


def _workflow_and_action(
    *,
    recent_runs: tuple[RunSummary, ...],
    failures: tuple[HomeFailureView, ...],
    idea_captured: bool,
    configuration_selected: bool,
) -> tuple[int, HomeAction]:
    if failures:
        return 4, HomeAction(
            label="Inspect failure",
            description="A recent failed test needs attention before research continues.",
            href="/research/backtest-results",
            kind="failure",
        )
    if any(run.status.lower() in _ACTIVE_RUN_STATUSES for run in recent_runs):
        return 3, HomeAction(
            label="Wait for active test",
            description="A test is active. Review its recorded status; do not submit it again.",
            href="/research/run-test",
            kind="wait",
        )
    succeeded = tuple(run for run in recent_runs if run.status.lower() == "succeeded")
    if len(succeeded) >= 2:
        return 5, HomeAction(
            label="Continue to Compare",
            description="At least two completed tests are available for evidence comparison.",
            href="/research/compare-backtests",
            kind="continue",
        )
    if succeeded:
        return 4, HomeAction(
            label="Continue to Results",
            description="Inspect the latest persisted result before deciding what comes next.",
            href="/research/backtest-results",
            kind="continue",
        )
    if configuration_selected:
        return 3, HomeAction(
            label="Continue to Run test",
            description="Review the selected immutable fixture setup before an explicit launch.",
            href="/research/run-test",
            kind="continue",
        )
    if idea_captured:
        return 2, HomeAction(
            label="Continue to Set up",
            description="Choose an approved immutable fixture setup; the draft does not run.",
            href="/research/setup",
            kind="continue",
        )
    return 1, HomeAction(
        label="Capture an idea",
        description="Start with a local draft. Capturing it does not retrieve or run anything.",
        href="/research/ideas",
        kind="capture",
    )


def _health_cards(health: tuple[HomeHealthView, ...]) -> list[html.Div]:
    return [
        html.Div(
            [
                html.I(className=f"atlas-readiness-mark atlas-readiness-mark-{_readiness_state(item)}"),
                html.Div(
                    [
                        html.Strong(item.label),
                        html.Small(item.status + (" · stale" if item.stale else "")),
                    ]
                ),
            ],
            id=f"home-health-{item.area}",
            className=f"atlas-readiness-cell atlas-readiness-cell-{_readiness_state(item)}",
            title=f"{item.detail} Last checked: {item.checked_at}",
        )
        for item in health
    ]


def _readiness_state(item: HomeHealthView) -> str:
    status = item.status.lower()
    if item.stale or "degraded" in status or "stale" in status:
        return "partial"
    if "unavailable" in status:
        return "gap"
    if "not checked" in status or "unknown" in status:
        return "unavailable"
    return "validated"


def health_cards_for_readings(
    readings: Iterable[HomeHealthReading],
    *,
    observed_at: datetime,
    stale_after: timedelta,
) -> list[html.Div]:
    """Render current cards from a previously captured read-only snapshot."""

    return _health_cards(_health_views(readings, observed_at, stale_after))


def _run_section(run: HomeRunView | None) -> html.Section:
    if run is None:
        content = html.P(
            "No selected, active, or persisted run is available yet.",
            className="empty-state-copy",
        )
    else:
        content = html.Div(
            [
                html.Strong(run.label),
                html.P(f"Last update: {run.timestamp}", className="summary-detail"),
                html.P(run.detail, className="summary-detail"),
                dcc.Link(
                    "Open recorded run",
                    href="/research/backtest-results",
                    className="secondary-action",
                ),
            ],
            className="summary-card",
        )
    return html.Section(
        [html.H2("Current research run"), content],
        id="home-current-run",
        className="panel",
    )


def _failure_section(failures: tuple[HomeFailureView, ...]) -> html.Section:
    if not failures:
        content = html.P(
            "No recent failures require attention.", className="empty-state-copy"
        )
    else:
        content = html.Ul(
            [
                html.Li(
                    [
                        html.Strong("Test needs attention"),
                        html.P(failure.summary),
                        html.Small(failure.timestamp),
                    ]
                )
                for failure in failures
            ],
            className="home-failure-list",
        )
    return html.Section(
        [html.H2("Failures needing attention"), content],
        id="home-attention-failures",
        className="panel",
    )


__all__ = [
    "HomeAction",
    "HomeFailureView",
    "HomeHealthReading",
    "HomeHealthView",
    "HomeRunView",
    "HomeViewModel",
    "HomeWorkflowStep",
    "build_home_view_model",
    "layout",
]
