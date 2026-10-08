"""Focused proof for the Survivors-first Candidate Universe."""

from __future__ import annotations

from typing import Any

from dash import Dash

from dashboard.callbacks.candidates import register_candidates_callbacks
from dashboard.pages.candidates import (
    candidate_columns,
    candidate_population,
    candidate_rows,
    layout,
)
from dashboard.routing import NAVIGATION_LINKS, ROUTE_REGISTRY
from orchestration import survivor_read_model


def _walk(component: Any):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _component(component: Any, component_id: str) -> Any:
    return next(item for item in _walk(component) if getattr(item, "id", None) == component_id)


def _row(**changes: object) -> dict[str, object]:
    return {
        "run_id": "run-1",
        "strategy": "Opening range breakout",
        "instrument": "MES",
        "interval": "1m",
        "stage": "Monte Carlo validation",
        "status": "Succeeded",
        "review": "Not reviewed",
        "evidence": "Screened out",
        "reproducibility": "Manifest verified",
        "total_return": 0.12,
        "sharpe_ratio": 1.4,
        "max_drawdown": -0.08,
        "number_of_trades": 52,
        "created_at": "2026-10-07T12:00:00Z",
        "rejection_reasons": "sharpe gate",
        "factory_outcome": None,
        **changes,
    }


def test_survivor_requires_explicit_persisted_survival_evidence() -> None:
    assert candidate_population(_row(review="Accepted", evidence="Succeeded", rejection_reasons="")) == "Needs review"
    assert candidate_population(_row(evidence="Passed", rejection_reasons="", factory_outcome="ready_for_protected_test")) == "Survivor"
    assert candidate_population(_row(evidence="Passed", rejection_reasons="rejected", factory_outcome="ready_for_protected_test")) == "Rejected"
    assert candidate_population(_row()) == "Rejected"
    assert candidate_population(_row(status="Running", evidence="", rejection_reasons="")) == "Advancing"


def test_candidate_grid_defaults_to_survivors_and_keeps_missing_metrics_unavailable() -> None:
    survivor = _row(
        run_id="gold-1",
        evidence="Qualified survivor",
        rejection_reasons="",
        factory_outcome="ready_for_protected_test",
    )
    rejected = _row(run_id="rejected-1")
    page = layout(history_rows=(survivor, rejected))
    grid = _component(page, "candidate-universe-grid")
    population = _component(page, "candidate-population")

    assert population.value == "Survivor"
    assert [row["run_id"] for row in grid.rowData] == ["gold-1"]
    assert grid.rowData[0]["oos_retention"] is None
    assert grid.rowData[0]["robustness"] is None
    assert grid.rowData[0]["paper_eligibility"] == "Lane inactive"
    assert grid.persisted_props == ["filterModel", "columnState"]


def test_candidate_grid_exposes_required_ranking_fields_and_primary_navigation() -> None:
    fields = {column["field"] for column in candidate_columns()}
    assert {
        "sharpe",
        "net_return",
        "max_drawdown",
        "oos_retention",
        "robustness",
        "trades",
        "paper_eligibility",
    } <= fields
    assert dict(NAVIGATION_LINKS)["/research/candidates"] == "Candidates"
    assert "/research/candidates" in dict(ROUTE_REGISTRY)
    assert "/research/ideas" not in dict(NAVIGATION_LINKS)
    assert "/research/setup" not in dict(NAVIGATION_LINKS)
    assert "/research/run-test" not in dict(NAVIGATION_LINKS)


def test_candidate_projection_preserves_persisted_metrics_without_invention() -> None:
    projected = candidate_rows((_row(evidence="Passed", rejection_reasons="", factory_outcome="ready_for_protected_test"),))[0]
    assert projected["sharpe"] == 1.4
    assert projected["net_return"] == 0.12
    assert projected["oos_retention"] is None
    assert projected["robustness"] is None


def test_candidate_selection_opens_results_first_and_compare_second() -> None:
    app = Dash(__name__)
    register_candidates_callbacks(app)
    entry = next(
        value
        for key, value in app.callback_map.items()
        if "candidate-selection-message.children" in key
    )
    action = getattr(entry["callback"], "__wrapped__", entry["callback"])

    single = action([{"run_id": "gold-1", "population": "Survivor"}])
    assert single[1] == "/research/backtest-results?run_id=gold-1"
    assert single[3] is None

    compared = action([
        {"run_id": "gold-1", "population": "Survivor"},
        {"run_id": "gold-2", "population": "Survivor"},
    ])
    assert compared[1] is None
    assert compared[3] == "/research/compare-backtests?run_id=gold-1&run_id=gold-2"

    mixed = action([
        {"run_id": "gold-1", "population": "Survivor"},
        {"run_id": "rejected-1", "population": "Rejected"},
    ])
    assert mixed[3] is None
    assert "only when every selection is an explicit survivor" in mixed[0]


def test_factory_outcome_annotation_marks_only_verified_final_run(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        survivor_read_model,
        "verified_survivor_run_ids",
        lambda **_kwargs: frozenset({"gold-1"}),
    )
    rows = survivor_read_model.annotate_factory_outcomes(
        ({"run_id": "gold-1"}, {"run_id": "other"}),
        database="unused.sqlite",
    )

    assert rows[0]["factory_outcome"] == "ready_for_protected_test"
    assert rows[1]["factory_outcome"] is None
