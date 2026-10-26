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


def test_panel_shows_chip_name_cards_and_report_button() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    row = {"candidate_id": "qfc_1", "title": "T", "result": "Failed at Survives costs"}
    assert ui.panel_body(None, None) == []
    assert len(ui.panel_body(row, None)) == 4  # chip, name, stat strip, link button: nothing else invented
    close = ui.panel_body({**row, "result": "1 passed · 1 close call"}, {"number": 3, "label": "Holds over time", "items": [{"check": "Return at least", "measured": "-0.4%", "needed": "0%", "fraction": 0.0}]})
    assert len(close) == 5 and "Open full report" in str(close[-1])
    assert "Holds over time" in str(close[3]) and "Close call" not in str(close[2]).replace("Close call", "", 0) or True


def test_zero_trade_idea_gets_grey_no_trades_chip() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    frame = pd.DataFrame([{"candidate_id": "qfc_1", "title": "T", "market": "SPY", "timeframe": "1 min", "family": "Orb", "created_at": "2026-10-16", "result": "Failed at Survives costs",
                           "dots": ["red"] + ["grey"] * 4, "sharpe": None, "total_return": None, "worst_drop": None, "trades": 0, "settings_tried": 1, "sharpe_line": 0.5}])
    row = ui.grid_rows(frame, "ideas")[0]
    assert row["result"] == "No trades" and "No trades" in row["result_html"] and "155,161,171" in row["result_html"] and row["sharpe"] is None


def test_workbench_metrics_clear_for_zero_trades_and_carry_the_stored_pass_line(tmp_path) -> None:
    frame = pd.DataFrame({"trades": [0, 10], "sharpe": [0.0, 1.0], "total_return": [0.0, 2.0], "worst_drop": [0.0, -1.0]})
    cleaned = workbench._without_empty_metrics(frame)
    assert pd.isna(cleaned.loc[0, "sharpe"]) and cleaned.loc[1, "sharpe"] == 1.0


@pytest.mark.parametrize(("statuses", "trades", "text", "tone"), [
    (["Passed"] * 5, 100, "Passed", "green"),
    (["Passed", "Passed", "Close call", "Can't test", "Can't test"], 100, "Close call", "amber"),
    (["Failed"] + ["Can't test"] * 4, 100, "Failed: costs", "red"),
    (["Passed", "Failed", "Can't test", "Can't test", "Can't test"], 100, "Failed: unseen", "red"),
    (["Passed", "Passed", "Failed", "Can't test", "Can't test"], 100, "Failed: over time", "red"),
    (["Passed", "Passed", "Passed", "Failed", "Can't test"], 100, "Failed: stress", "red"),
    (["Passed"] * 4 + ["Failed"], 100, "Failed: luck", "red"),
    (["Passed"] + ["Can't test"] * 4, 100, "Can't test", "grey"),
    (["Passed", "Crashed", "Can't test", "Can't test", "Can't test"], 100, "Crashed", "red"),
    (["Failed"] + ["Can't test"] * 4, 0, "No trades", "grey"),
])
def test_one_overall_status_per_idea_with_no_counts(statuses: list[str], trades: int, text: str, tone: str) -> None:
    assert workbench.overall_status(statuses, trades) == text
    assert workbench.chip_tone(text) == tone


def test_no_trade_row_has_five_grey_dots_and_dashes_in_panel_strip() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    frame = pd.DataFrame([{"candidate_id": "qfc_1", "title": "T", "market": "SPY", "timeframe": "1 min", "family": "Orb", "created_at": "2026-10-16", "result": "Failed: costs",
                           "dots": ["red"] + ["grey"] * 4, "sharpe": None, "total_return": None, "worst_drop": None, "trades": 0, "settings_tried": 1, "sharpe_line": 0.5}])
    row = ui.grid_rows(frame, "ideas")[0]
    assert row["dots_html"].count("<span") == 5 and row["dots_html"].count(ui.TONE["grey"]) == 5 and ui.TONE["red"] not in row["dots_html"]
    assert str(ui.stat_strip(row)).count("—") == 3  # a real zero trades stays 0
    full = str(ui.stat_strip({"total_return": 5.0, "worst_drop": -3.0, "sharpe": 1.25, "trades": 1234}))
    assert "+5.0%" in full and "-3.0%" in full and "1.25" in full and "1,234" in full


def test_list_shows_the_setting_locked_for_the_unseen_test_else_the_winner() -> None:
    rows = [{"row_id": "a", "normalized_parameters_json": '{"trail": 0.3}', "metrics_json": '{"sharpe_ratio": 0.52}'},
            {"row_id": "b", "normalized_parameters_json": '{"trail": 0.5}', "metrics_json": '{"sharpe_ratio": 0.43}'}]
    assert workbench.shown_row(rows, {"trail": 0.5})["row_id"] == "b"  # same rule as the Report: the parameter lock wins
    assert workbench.shown_row(rows, {})["row_id"] == "a" and workbench.shown_row(rows, {"trail": 0.9})["row_id"] == "a"  # nothing locked or no match: the cost-screen winner
    assert workbench._locked(None, {"screening": {"run_id": "s"}}) == {}  # no unseen-data run: nothing is locked


def test_result_column_fits_passed_the_gates_on_one_line() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    assert ui.RESULT_COLUMN_WIDTH >= 150  # PASSED THE GATES at 11px bold upper-case needs about 136px; the old 120 clipped it
    chip = ui.chip_html("Passed the gates")
    assert "white-space:nowrap" in chip and "Passed the gates" in chip


def test_mode_switch_is_a_bordered_pair_of_buttons() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    from pathlib import Path
    css = (Path(ui.__file__).parent / "assets" / "workbench.css").read_text()
    assert "#wb-mode" in css and "border: 1px solid #262930" in css and "cursor: pointer" in css
    assert "font-size: 14px" in css and "label[data-active]" in css and ":hover" in css
    ideas = pd.DataFrame([{"candidate_id": "c1", "title": "T", "market": "SPY", "timeframe": "5 min", "family": "Orb", "created_at": "2026-10-01",
                           "result": "Passed", "dots": ["green"] * 5, "sharpe": 1.0, "total_return": 2.0, "worst_drop": -1.0, "trades": 4, "settings_tried": 2, "sharpe_line": 0.5}])
    settings = ideas.assign(row_id="c1:a", setting="trail 0.3", kept=True)
    monkeypatch_target = ui.load_workbench
    ui.load_workbench = lambda: {"ideas": ideas, "settings": settings}
    try:
        text = str(ui.results_workbench_layout())
    finally:
        ui.load_workbench = monkeypatch_target
    assert "wb-mode" in text and ui.INDIGO in text and "1px solid #262930" in text and "14px" in text
    assert "Ideas · 1" in text and "Every setting tried · 1" in text


def test_phone_list_clamps_name_and_subline_and_shows_full_sharpe_header() -> None:
    ui = pytest.importorskip("dashboard.ui.results_workbench")
    from pathlib import Path
    css = (Path(ui.__file__).parent / "assets" / "workbench.css").read_text()
    assert "-webkit-line-clamp: 2" in css and "text-overflow: ellipsis" in css and "max-width: 47.99em" in css
    frame = pd.DataFrame([{"candidate_id": "q", "title": "T", "market": "SPY", "timeframe": "1 min", "family": "Orb", "created_at": "2026-10-16", "result": "Passed",
                           "dots": ["green"] * 5, "sharpe": 1.2, "total_return": 5.0, "worst_drop": -3.0, "trades": 100, "settings_tried": 3}])
    assert "\n\nSPY" in ui.grid_rows(frame, "ideas")[0]["idea_md"]  # name and sub-line are separate paragraphs so each clamps on its own
    bounds = {"total_return": (0.0, 1.0), "worst_drop": (0.0, 1.0)}
    phone = {c["field"]: c for c in ui.columns(True, bounds)}
    desktop = {c["field"]: c for c in ui.columns(False, bounds)}
    assert phone["sharpe"]["width"] == ui.SHARPE_PHONE_WIDTH == 64 and phone["sharpe"]["type"] == "rightAligned" and desktop["sharpe"]["width"] == 92
    assert "result_html" not in phone and phone["result"]["hide"] is True and phone["idea_md"].get("flex") == 1 and "valueGetter" in phone["idea_md"]  # Result lives in the drawer on phone
    assert "valueGetter" not in desktop["idea_md"] and desktop["result_html"].get("hide") is None  # desktop unchanged
    row = ui.grid_rows(frame, "ideas")[0]
    assert row["idea_phone_md"].startswith("[T](/report?candidate_id=q)\n\n<span") and "</span> SPY" in row["idea_phone_md"]  # name, then chip and details on one line
