"""Truthful, side-effect-free Home overview for Milestone 23.

The application integration layer supplies snapshots that it has already read.
This module never probes a service, opens the research database, accesses a
credential, or launches work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from dash import dcc, html

from dashboard.health import (
    HomeHealthReading,
    normalize_health_reading,
    redact_credential_health_reading,
)
from dashboard.pages.common import page_heading
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
    project_status: DashboardProjectStatus = PROJECT_STATUS,
) -> HomeViewModel:
    """Derive one truthful Home snapshot from already-read application state."""

    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    resolved_as_of = as_of or datetime.now(timezone.utc)
    if resolved_as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")

    health = _health_views(health_readings, resolved_as_of, stale_after)
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
        discovery_gate=(
            "Blocked — strategy discovery remains unavailable until Milestone 23 "
            "passes every objective acceptance gate."
        ),
        health=health,
        run=_run_view(run),
        failures=failures,
        workflow=workflow,
        action=action,
        subtitle=project_status.home_subtitle,
    )


def layout(view_model: HomeViewModel | None = None) -> html.Div:
    """Render the Home overview without performing any read or write."""

    from dashboard.application import _strategy_research_path

    model = view_model or build_home_view_model()
    return html.Div(
        [
            page_heading("RESEARCH / HOME", "Home", model.subtitle),
            _strategy_research_path("/"),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span("Current milestone", className="summary-label"),
                            html.Strong(model.milestone),
                            html.P(model.milestone_status, className="summary-detail"),
                        ],
                        className="summary-card",
                    ),
                    html.Div(
                        [
                            html.Span("Discovery gate", className="summary-label"),
                            html.Strong("Discovery blocked"),
                            html.P(model.discovery_gate, className="summary-detail"),
                        ],
                        id="home-discovery-gate",
                        className="summary-card",
                    ),
                ],
                className="summary-grid",
            ),
            html.Section(
                [
                    html.H2("Research readiness"),
                    html.Div(_health_cards(model.health), className="summary-grid"),
                ],
                id="home-health-summary",
                className="panel",
            ),
            _run_section(model.run),
            _failure_section(model.failures),
            html.Section(
                [
                    html.H2("Continue research"),
                    html.P(model.action.description, className="summary-detail"),
                    dcc.Link(
                        model.action.label,
                        href=model.action.href,
                        id="home-primary-action",
                        className="primary-action",
                        title=model.action.description,
                    ),
                ],
                id="home-next-safe-action",
                className=f"panel home-action home-action-{model.action.kind}",
            ),
        ],
        className="page-container home-page",
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
                html.Span(item.label, className="metric-label"),
                html.Strong(item.status),
                html.P(item.detail, className="summary-detail"),
                html.Small(
                    f"Last checked: {item.checked_at}"
                    + (" — stale" if item.stale else "")
                ),
            ],
            id=f"home-health-{item.area}",
            className=(
                "metric-card home-health-card"
                + (" home-health-card-stale" if item.stale else "")
            ),
        )
        for item in health
    ]


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
