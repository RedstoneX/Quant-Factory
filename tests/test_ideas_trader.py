"""Ideas page for the trader: plain reasons, pass/fail per test, multi-select, no junk."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dashboard.candidates_projection import load_candidate_detail, load_candidates_page, load_candidates_summary
from dashboard.plain_labels import plain_reason_detail, plain_rejection_reasons, stage_verdict
from dashboard.ui import candidates as ui
from tests.test_candidates_projection import _candidate_database

SHARPE = "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.08."
DROP = "max_drawdown failed: expected <= 0.2 (inclusive); observed -0.31."


def test_rejection_reasons_say_which_rule_missed_and_by_how_much() -> None:
    assert plain_rejection_reasons(f"{SHARPE} | {DROP}") == [
        "Sharpe 0.08 vs 0.50 needed after costs",
        "Biggest drop 31.0% vs 20.0% allowed",
    ]
    assert plain_rejection_reasons("") == []
    assert plain_rejection_reasons("something odd") == ["something odd"]


def test_test_verdict_is_pass_or_fail_not_run_status() -> None:
    assert stage_verdict("succeeded", 0, 6) == ("Failed", "red")
    assert stage_verdict("succeeded", 2, 6) == ("Passed", "teal")
    assert stage_verdict("succeeded", None, 0, idea_passed=True) == ("Passed", "teal")
    assert stage_verdict("running", 0, 0)[0] == "Running"
    assert stage_verdict("failed", 0, 0)[0] == "Crashed"


def test_locked_paper_wording_is_plain() -> None:
    assert "separate authority" not in plain_reason_detail("Protected test remains locked until separate authority is granted.")


def test_projection_paper_junk_and_test_results(tmp_path: Path) -> None:
    path = tmp_path / "quant_factory.sqlite3"
    _candidate_database(path)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE parameter_results SET rejection_reasons=? WHERE row_id='closed-row'", (SHARPE,))
    connection.execute("INSERT INTO idea_drafts VALUES ('junk','Connection test','probe',?,NULL,'2026-10-09T00:00:00+00:00')", (json.dumps({"candidate": {"title": "Connection test", "status": "received"}}),))
    connection.commit(); connection.close()

    visible = {row["candidate_id"]: row for row in load_candidates_page(lifecycle="all", database=path)["rowData"]}
    assert "junk" not in visible
    assert "junk" in {row["candidate_id"] for row in load_candidates_page(lifecycle="all", show_test=True, database=path)["rowData"]}
    assert load_candidates_summary(database=path)["counts"]["all"] == len(visible)
    assert visible["gold"]["paper"] == "Not started"
    assert visible["closed"]["paper"] == ""

    closed = load_candidate_detail("closed", database=path)
    assert plain_rejection_reasons(closed["screening_reasons"]) == ["Sharpe 0.08 vs 0.50 needed after costs"]
    oos = next(item for item in closed["progression"] if item["stage"] == "oos")
    assert stage_verdict(oos["status"], oos["passed_count"], oos["result_count"]) == ("Failed", "red")
    gold = load_candidate_detail("gold", database=path)
    oos = next(item for item in gold["progression"] if item["stage"] == "oos")
    assert stage_verdict(oos["status"], oos["passed_count"], oos["result_count"]) == ("Passed", "teal")


def test_detail_panel_has_one_results_button_and_a_reason() -> None:
    record = {"lifecycle": "rejected", "campaign_state": "screened_out", "run_id": "r1", "screening_status": "screened_out", "screening_count": 6, "screened_out_count": 6, "screening_reasons": SHARPE, "progression": [{"stage": "screening", "status": "succeeded", "passed_count": 0, "result_count": 6}]}
    rendered = repr(ui._detail_body(record, "overview"))
    assert "candidate-open-results" in rendered and "candidate-open-evidence" not in rendered
    assert "Sharpe 0.08 vs 0.50 needed after costs" in rendered
    assert "Failed" in rendered and "Succeeded" not in rendered
    assert ui._outcome(record)[1] == "Sharpe 0.08 vs 0.50 needed after costs"


def test_grid_uses_checkbox_multi_select_and_keeps_key_columns_on_phones() -> None:
    layout = repr(ui.candidates_layout())
    assert "'mode': 'multiRow'" in layout and "'enableClickSelection': False" in layout
    columns = {c["field"]: c for c in ui.CANDIDATE_COLUMNS}
    assert columns["title"]["wrapText"] and columns["title"]["tooltipField"] == "title"
    assert 'setColumnsVisible(["symbol", "max_drawdown", "retained", "robustness", "paper"]' in layout
