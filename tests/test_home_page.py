"""Focused tests for the side-effect-free Milestone 23 Home component."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import pytest

from dashboard.pages.home import HomeHealthReading, build_home_view_model, layout
from orchestration import RunEvent, RunSummary


NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _run(
    run_id: str,
    status: str,
    *,
    error_summary: str | None = None,
    created_at: str = "2026-09-18T11:00:00Z",
) -> RunSummary:
    terminal = status in {"succeeded", "failed", "cancelled", "timed_out"}
    active = status in {"running", "retrying"}
    return RunSummary(
        run_id=run_id,
        configuration_id="a" * 64,
        strategy_id="spym_fixture_strategy",
        strategy_version="1.0.0",
        stage="fixture",
        status=status,
        created_at=created_at,
        started_at="2026-09-18T11:00:01Z" if active or terminal else None,
        completed_at="2026-09-18T11:00:02Z" if terminal else None,
        error_summary=error_summary,
        prefect_flow_run_id=None,
        prefect_api_url=None,
        attempt_count=1,
    )


def _walk(component: Any) -> Iterator[Any]:
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _text(component: Any) -> str:
    children = getattr(component, "children", component)
    if isinstance(children, (list, tuple)):
        return " ".join(_text(child) for child in children)
    if children is None:
        return ""
    if hasattr(children, "children"):
        return _text(children)
    return str(children)


def _component(component: Any, component_id: str) -> Any:
    return next(item for item in _walk(component) if getattr(item, "id", None) == component_id)


def test_home_no_data_has_honest_empty_states_and_one_capture_action() -> None:
    page = layout(build_home_view_model(as_of=NOW))
    rendered = _text(page)

    assert "No selected, active, or persisted run is available yet." in rendered
    assert "No recent failures require attention." in rendered
    assert rendered.count("Not checked") >= 12
    assert "Capture an idea" in rendered
    actions = [
        item
        for item in _walk(page)
        if getattr(item, "id", None) == "home-primary-action"
    ]
    assert len(actions) == 1
    assert actions[0].href == "/research/ideas"
    workflow_steps = [
        item
        for item in _walk(page)
        if "research-path-card" in str(getattr(item, "className", ""))
    ]
    assert len(workflow_steps) == 6
    assert [item.children[1].children for item in workflow_steps] == [
        "Home",
        "Ideas",
        "Set up",
        "Run test",
        "Results",
        "Compare",
    ]


def test_home_timestamp_less_health_is_not_presented_as_healthy() -> None:
    model = build_home_view_model(
        health_readings=(
            HomeHealthReading(
                area="database",
                status="Available",
                detail="A caller supplied a status without observation time.",
            ),
            HomeHealthReading(
                area="credential",
                status="Available: SENSITIVE_SENTINEL",
                detail="SENSITIVE_SENTINEL",
                checked_at="2026-09-18T11:59:00Z",
            ),
        ),
        as_of=NOW,
    )
    page = layout(model)
    database = _component(page, "home-health-database")

    assert model.health[0].status == "Not checked"
    assert "Available" not in _text(database)
    assert "Last checked: Not checked" in _text(database)
    for area in ("worker", "provider", "cache", "artifact"):
        assert "Not checked" in _text(_component(page, f"home-health-{area}"))
    credential = _text(_component(page, "home-health-credential"))
    assert "Not checked" in credential
    assert "Credential values are never displayed." in credential
    assert "SENSITIVE_SENTINEL" not in credential


def test_home_marks_old_health_stale_and_keeps_observation_timestamp() -> None:
    observed = "2026-09-18T10:00:00Z"
    model = build_home_view_model(
        health_readings=(
            HomeHealthReading(
                area="database",
                status="Available",
                detail="Read-only integrity check passed.",
                checked_at=observed,
            ),
        ),
        as_of=NOW,
        stale_after=timedelta(minutes=30),
    )
    database = _component(layout(model), "home-health-database")

    assert model.health[0].stale is True
    assert model.health[0].status == "Stale — Available"
    assert observed in _text(database)
    assert "stale" in _text(database).lower()


def test_home_rejects_future_health_timestamp_instead_of_claiming_current_state() -> None:
    model = build_home_view_model(
        health_readings=(
            HomeHealthReading(
                area="database",
                status="Available",
                detail="A clock-skewed observation must fail closed.",
                checked_at="2026-09-18T12:00:01Z",
            ),
        ),
        as_of=NOW,
    )

    database = _component(layout(model), "home-health-database")

    assert model.health[0].status == "Not checked"
    assert model.health[0].checked_at == "Not checked"
    assert "future" in _text(database).lower()


@pytest.mark.parametrize(
    "checked_at",
    (
        "not-a-timestamp",
        "2026-09-18T11:59:00",
    ),
)
def test_home_rejects_malformed_or_timezoneless_health_timestamps(
    checked_at: str,
) -> None:
    model = build_home_view_model(
        health_readings=(
            HomeHealthReading(
                area="database",
                status="Available",
                detail="An invalid observation time must fail closed.",
                checked_at=checked_at,
            ),
        ),
        as_of=NOW,
    )

    database = _component(layout(model), "home-health-database")

    assert model.health[0].status == "Not checked"
    assert model.health[0].checked_at == "Not checked"
    assert "invalid" in _text(database).lower()


def test_home_active_run_is_selected_and_requires_waiting_not_resubmission() -> None:
    completed = _run("completed", "succeeded", created_at="2026-09-18T11:30:00Z")
    active = _run("active", "running", created_at="2026-09-18T11:00:00Z")
    model = build_home_view_model(recent_runs=(completed, active), as_of=NOW)
    page = layout(model)

    assert model.run is not None and model.run.run_id == "active"
    assert model.action.kind == "wait"
    assert model.action.label == "Wait for active test"
    assert model.action.href == "/research/run-test"
    assert "do not submit it again" in model.action.description
    assert model.workflow[3].state == "Current"
    assert "Running" in _text(_component(page, "home-current-run"))


def test_home_recent_failure_takes_precedence_over_active_run() -> None:
    failed = _run("failed", "failed", error_summary="Fixture input could not be read.")
    active = _run("active", "running")
    unrelated_event = RunEvent(
        event_id=1,
        run_id="active",
        event_type="run_started",
        timestamp="2026-09-18T11:00:01Z",
        severity="info",
        message="Run started.",
        source="fixture",
    )
    model = build_home_view_model(
        recent_runs=(active, failed), recent_events=(unrelated_event,), as_of=NOW
    )
    page = layout(model)

    assert model.run is not None and model.run.run_id == "active"
    assert model.action.kind == "failure"
    assert model.action.label == "Inspect failure"
    assert model.action.href == "/research/backtest-results"
    assert model.workflow[4].state == "Current"
    assert "Fixture input could not be read." in _text(
        _component(page, "home-attention-failures")
    )


def test_home_keeps_discovery_blocked_while_milestone_23_is_pending() -> None:
    model = build_home_view_model(
        recent_runs=(_run("first", "succeeded"), _run("second", "succeeded")),
        as_of=NOW,
    )
    page = layout(model)
    discovery = _text(_component(page, "home-discovery-gate"))

    assert model.milestone.startswith("Milestone 23")
    assert model.milestone_status == "Pending - hard discovery gate"
    assert "Discovery blocked" in discovery
    assert "strategy discovery remains unavailable" in discovery
    assert model.action.label == "Continue to Compare"
    assert "discover" not in model.action.label.lower()
