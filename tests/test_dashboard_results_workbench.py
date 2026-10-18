"""Data mapping for the Results workbench: real-idea selection, five-test dots, row projection, close-call shortfall, paging."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import results_workbench_projection as workbench


@pytest.mark.parametrize(("title", "attribution", "expected"), [
    ("SPY 0DTE bot replica", "Agent grok-remote (xai) · source: Terry · rules read from code", True),
    ("Opening range breakout", "Agent codex-local (openai) · source: Toby Crabel · Day Trading (1990)", True),
    ("Connection test idea", "Agent grok-remote (xai) · source: Claude for Rex", False),
    ("Real looking title", "Agent grok-remote (xai) · source: Claude for Rex · Research-login connection test, 2026-10-14", False),
    ("Real looking title", "Agent codex-local (openai) · source: Claude (usability test) · TEST ONLY - submit flow", False),
    ("Smoke test run", "Agent grok-remote (xai) · source: Terry", False),
    ("Terry's ORB trail test notes", "Agent grok-remote (xai) · source: Terry · Terry's ORB trail test notes, 2026-10-14", True),
])
def test_real_idea_filter(title: str, attribution: str, expected: bool) -> None:
    assert workbench.is_real_idea(title, attribution) is expected


def test_opens_on_newest_real_idea() -> None:
    ideas = pd.DataFrame([{"candidate_id": "old", "created_at": "2026-10-14T10:00:00Z"}, {"candidate_id": "new", "created_at": "2026-10-16T10:00:00Z"},
                          {"candidate_id": "mid", "created_at": "2026-10-15T10:00:00Z"}])
    assert workbench.newest_real_idea(ideas) == "new"
    assert workbench.newest_real_idea(pd.DataFrame()) is None


def test_five_dots_follow_the_five_statuses() -> None:
    statuses = ["Passed", "Close call", "Failed", "Can't test", "Crashed"]
    assert workbench.five_dots(statuses) == ["green", "amber", "red", "grey", "red"]


def test_shortfall_for_a_minimum_and_a_maximum_rule() -> None:
    results = [
        {"threshold_id": "minimum_sharpe", "status": "failed", "observed": 0.25, "threshold": 0.5},
        {"threshold_id": "maximum_drawdown", "status": "failed", "observed": -0.2, "threshold": -0.1},
        {"threshold_id": "minimum_return", "status": "failed", "observed": -0.004, "threshold": 0.0},
        {"threshold_id": "minimum_observations", "status": "passed", "observed": 900, "threshold": 500},
        {"threshold_id": "minimum_valid_neighbors", "status": "failed", "observed": None, "threshold": 3},
    ]
    items = workbench.shortfall_items("Holds over time", results)
    assert [item["fraction"] for item in items] == [pytest.approx(0.5), pytest.approx(0.5), 0.0]  # passed and unmeasured rules are left out
    assert all(item["label"] == "Holds over time" and item["measured"] and item["needed"] for item in items)


def test_settings_paging_sorts_filters_and_slices() -> None:
    frame = pd.DataFrame({"sharpe": [0.5, 1.5, -0.2, 0.9], "idea_md": ["a", "b", "c", "d"], "trades": [10, 20, 30, 40]})
    page = workbench.page_of_settings(frame, {"startRow": 0, "endRow": 2, "sortModel": [{"colId": "sharpe", "sort": "desc"}]})
    assert [row["idea_md"] for row in page["rowData"]] == ["b", "d"] and page["rowCount"] == 4
    ranged = workbench.page_of_settings(frame, {"startRow": 0, "endRow": 10, "filterModel": {"sharpe": {"filterType": "number", "type": "inRange", "filter": 0.0, "filterTo": 1.0}}})
    assert sorted(row["idea_md"] for row in ranged["rowData"]) == ["a", "d"] and ranged["rowCount"] == 2
    text = workbench.page_of_settings(frame, {"filterModel": {"idea_md": {"filterType": "text", "type": "contains", "filter": "C"}}})
    assert [row["idea_md"] for row in text["rowData"]] == ["c"]


def test_grid_rows_link_escape_and_dots() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    frame = pd.DataFrame([{"candidate_id": "qfc_1", "title": "<b>Bad</b> [x](y) title", "market": "SPY", "timeframe": "1 min", "family": "Orb", "created_at": "2026-10-16",
                           "result": "Passed", "dots": ["green"] * 5, "sharpe": 1.2, "total_return": 5.0, "worst_drop": -3.0, "trades": 100, "settings_tried": 3}])
    row = ui.grid_rows(frame, "ideas")[0]
    assert "](/report?candidate_id=qfc_1)" in row["idea_md"] and "<b>" not in row["idea_md"] and "SPY" in row["idea_md"]
    assert row["dots_html"].count("<span") == 5 and row["sharpe"] == 1.2
    assert ui.grid_rows(frame.iloc[0:0], "ideas") == []


def test_close_call_panel_has_bar_card_and_report_button_only() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    assert ui.panel_body(None) == []
    body = ui.panel_body({"candidate_id": "qfc_1", "title": "T", "number": 3, "label": "Holds over time",
                          "items": [{"check": "Return at least", "measured": "-0.4%", "needed": "0%", "fraction": 0.0}]})
    assert len(body) == 4  # badge, title, one test card, link button
    assert "Open full report" in str(body[-1])
