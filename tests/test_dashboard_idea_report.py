"""Data mapping for the Idea report page: test labels, the five statuses, the never-ran card, series shaping."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import idea_report_projection as report


def test_labels_are_the_agreed_plain_words() -> None:
    assert report.TEST_LABELS == {"screening": "Survives costs", "oos": "Unseen data", "walk_forward": "Holds over time",
                                  "robustness": "Stress test", "monte_carlo": "Shuffle test"}


@pytest.mark.parametrize(("stage", "stored", "run", "expected"), [
    ("screening", "passed", "succeeded", "Passed"),
    ("oos", "failed", "succeeded", "Failed"),
    ("screening", "failed", "succeeded", "Failed"),
    ("walk_forward", "failed", "succeeded", "Failed"),  # the recorded status wins: never upgraded to a close call
    ("robustness", "failed", "succeeded", "Failed"),
    ("monte_carlo", "failed", "succeeded", "Failed"),
    ("oos", None, None, "Can't test"),
    ("robustness", None, "succeeded", "Can't test"),
    ("walk_forward", None, "failed", "Crashed"),
])
def test_status_mapping(stage: str, stored: str | None, run: str | None, expected: str) -> None:
    assert report.report_status(stage, stored, run) == expected


def test_every_status_has_a_tone() -> None:
    assert set(report.STATUS_TONE) == {"Passed", "Close call", "Failed", "Can't test", "Crashed", "Not scored"}


@pytest.mark.parametrize(("states", "reason_part"), [
    ([], "no test has been started"),
    (["running"], "still running"),
    (["failed"], "crashed"),
    (["succeeded"], "did not save an account-value history"),
])
def test_never_ran_card_gives_reason_and_fix(states: list[str], reason_part: str) -> None:
    tests = [{"run_status": state} for state in states] + [{"run_status": None}]
    card = report.never_ran_card({}, tests)
    assert reason_part in card["reason"]
    assert card["fix"]


def test_missing_idea_reports_unavailable(tmp_path) -> None:
    assert report.load_report("qfc_missing", database=tmp_path / "none.sqlite3")["available"] is False


def test_hero_series_joins_unseen_onto_built_on() -> None:
    whole = [{"timestamp": f"2024-01-0{day}T10:00:00", "value": 100.0 + day} for day in range(1, 6)]
    unseen = [{"timestamp": "2024-01-04T10:00:00", "value": 50.0}, {"timestamp": "2024-01-05T10:00:00", "value": 55.0}]
    series = report.hero_series(whole, unseen)
    assert list(series["built"]) == [101.0, 102.0, 103.0]
    assert series["unseen"].iloc[0] == pytest.approx(103.0)
    assert series["unseen"].iloc[1] == pytest.approx(103.0 * 1.1)
    assert report.hero_series(whole, [])["unseen"].empty


def test_drawdown_and_monthly_returns() -> None:
    values = pd.Series([100.0, 110.0, 99.0, 121.0], index=pd.to_datetime(["2024-01-02", "2024-01-31", "2024-02-15", "2024-02-29"]))
    assert report.drawdown(values).min() == pytest.approx(-10.0)
    monthly = report.monthly_returns(values)
    assert monthly.loc[2024, 1] == pytest.approx(10.0)
    assert monthly.loc[2024, 2] == pytest.approx(10.0)
    assert report.monthly_returns(pd.Series(dtype=float)).empty


def test_settings_grid_marks_chosen_setting() -> None:
    rows = [{"row_id": f"r{i}{j}", "parameters": {"stop": s, "range": r}, "sharpe_ratio": i - j} for i, s in enumerate([0.2, 0.4]) for j, r in enumerate([5, 10])]
    grid = report.settings_grid(rows, "r10")
    assert grid["count"] == 4 and grid["chosen"] == ("0.4", "5") and grid["down"] == "stop"
    assert report.settings_grid([], None) is None


def _tests(statuses: list[str], ran: int) -> list[dict]:
    stages = ["screening", "oos", "walk_forward", "robustness", "monte_carlo"]
    return [{"stage": stage, "label": report.TEST_LABELS[stage], "status": status, "run_id": "r" if index < ran else None}
            for index, (stage, status) in enumerate(zip(stages, statuses))]


def test_header_chip() -> None:
    assert report.overall_chip(_tests(["Passed"] * 5, 5)) == ("Passed", "green")
    assert report.overall_chip(_tests(["Passed", "Can't test", "Can't test", "Can't test", "Can't test"], 1)) == ("1 passed · 4 not run", "grey")
    assert report.overall_chip(_tests(["Failed", "Can't test", "Can't test", "Can't test", "Can't test"], 1)) == ("Failed at Survives costs", "red")
    assert report.overall_chip(_tests(["Can't test"] * 5, 0)) == ("Not tested yet", "grey")


def test_summary_strip_leaves_out_what_cannot_be_computed() -> None:
    values = pd.Series([100.0, 110.0, 99.0], index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))
    items = dict(report.summary_strip(values, [{"pnl": 5.0}, {"pnl": -1.0}, {"pnl": 2.0}], 0.456))
    assert items == {"Return": "-1.0%", "Worst drop": "-10.0%", "Sharpe after costs": "0.46", "Trades": "3", "Win rate": "67%"}
    assert report.summary_strip(pd.Series(dtype=float), [], None) == []


def test_unseen_run_that_succeeded_with_a_saved_failed_verdict_shows_failed(monkeypatch, tmp_path) -> None:
    from dashboard import idea_results_projection as results

    monkeypatch.setattr(results, "oos_report_metrics", lambda **_: None)  # the saved report holds no metrics, only the verdict
    for saved, word in (("failed", "Failed"), ("screened_out", "Failed"), ("passed", "Passed"), ("not_run", "Can't test")):
        monkeypatch.setattr(results, "_artifact_document", lambda saved=saved, **_: {"artifact_kind": "out_of_sample", "test_status": saved})
        card = results._test_card(tmp_path / "db.sqlite3", "oos", "Unseen data", {"run_id": "run_x", "status": "succeeded"}, {})
        assert report.report_status("oos", card["status"], "succeeded") == word
    monkeypatch.setattr(results, "_artifact_document", lambda **_: {})
    card = results._test_card(tmp_path / "db.sqlite3", "oos", "Unseen data", {"run_id": "run_x", "status": "succeeded"}, {})
    assert report.report_status("oos", card["status"], "succeeded") == "Can't test"  # no saved verdict: still unknown, never guessed


def test_factory_verdict_overrides_research_statuses_and_falls_back_without_one() -> None:
    from dashboard import results_workbench_projection as workbench

    stored = ["Passed", "Can't test", "Can't test", "Can't test", "Can't test"]  # the research DB has no unseen-data run for this idea
    failed_unseen = report.apply_campaign_verdict(stored, ("screened_out", "oos"))
    assert failed_unseen == ["Passed", "Failed", "Can't test", "Can't test", "Can't test"] and workbench.overall_status(failed_unseen) == "Failed: unseen"
    assert report.apply_campaign_verdict(stored, ("screened_out", "screening"))[0] == "Failed"
    assert report.apply_campaign_verdict(stored, ("screened_out", "walk_forward")) == ["Passed", "Passed", "Failed", "Can't test", "Can't test"]
    assert report.apply_campaign_verdict(stored, ("survivor", "passed_all")) == ["Passed", "Passed", "Not scored", "Not scored", "Not scored"]  # a survivor passed the two gates only
    assert report.apply_campaign_verdict(stored, ("failed", "run_error")) == stored  # the campaign crash never paints a card; each card crashes from its own stage run
    assert report.apply_campaign_verdict(stored, None) == stored  # no event: the research-DB statuses stand
    assert report.apply_campaign_verdict(stored, ("queued", "waiting")) == stored  # waiting or running is no verdict yet


def test_survivor_keeps_its_own_score_statuses() -> None:
    from dashboard import results_workbench_projection as workbench

    stored = ["Passed", "Passed", "Failed", "Close call", "Can't test"]
    statuses = report.apply_campaign_verdict(stored, ("survivor", "awaiting_owner_review"))
    assert statuses == ["Passed", "Passed", "Failed", "Close call", "Not scored"]  # Holds over time = Failed, not overwritten with Passed
    assert report.STATUS_TONE["Not scored"] == report.STATUS_TONE["Can't test"]
    assert workbench.overall_status(report.apply_campaign_verdict(["Passed", "Can't test", "Can't test", "Can't test", "Can't test"], ("survivor", "x")), survivor=True) == "Passed"


def test_survivor_never_overwrites_a_recorded_gate_result() -> None:
    from dashboard import results_workbench_projection as workbench

    # the research DB recorded a failed unseen-data result: the recorded result stands, the survivor verdict does not paper over it
    statuses = report.apply_campaign_verdict(["Passed", "Failed", "Can't test", "Can't test", "Can't test"], ("survivor", "awaiting_owner_review"))
    assert statuses[:2] == ["Passed", "Failed"]
    assert report.gates_chip(statuses) is None
    # no recorded result for a gate: the survivor verdict fills it with Passed
    assert report.apply_campaign_verdict(["Can't test"] * 5, ("survivor", "x"))[:2] == ["Passed", "Passed"]


def test_survivor_with_failed_scores_keeps_gates_chip_and_stays_in_review() -> None:
    from dashboard import results_workbench_projection as workbench

    statuses = report.apply_campaign_verdict(["Passed", "Passed", "Failed", "Passed", "Can't test"], ("survivor", "awaiting_owner_review"))
    assert report.gates_chip(statuses) == "Passed the gates · Holds over time: failed"
    result = workbench.overall_status(statuses, survivor=True)
    assert result == "Passed the gates · Holds over time: failed" and workbench.chip_tone(result) == "amber"


def test_close_call_score_reads_close_call_in_the_chip() -> None:
    assert report.gates_chip(["Passed", "Passed", "Passed", "Close call", "Passed"]) == "Passed the gates · Stress test: close call"


def test_unseen_card_states_the_19_oct_rule_and_both_sharpes(monkeypatch, tmp_path) -> None:
    saved = {"total_return": 0.04, "sharpe_ratio": -0.2, "_training_metrics": {"total_return": 0.12, "sharpe_ratio": 0.477}}
    monkeypatch.setattr(report, "oos_report_metrics", lambda **_: saved)
    out = report._test_measure("oos", {"run_id": "run_x"}, {}, {}, tmp_path / "db.sqlite3", 0.1)
    assert out["rule"] == "Passes if it made money on years it never saw, after costs"
    assert out["scores"] == [("Built-on years", "0.48"), ("Unseen years", "-0.20")]
    saved["_training_metrics"] = {}
    out = report._test_measure("oos", {"run_id": "run_x"}, {}, {}, tmp_path / "db.sqlite3", 0.1)
    assert out["scores"][0] == ("Built-on years", None)


def test_chip_counts_never_ran_as_not_run_and_recorded_stops_as_cant_test() -> None:
    tests = _tests(["Passed", "Passed", "Can't test", "Can't test", "Can't test"], 3)
    assert report.overall_chip(tests) == ("2 passed · 1 can't test · 2 not run", "grey")


def test_recorded_failed_walk_forward_with_3_of_18_windows_reads_failed_everywhere() -> None:
    from dashboard import results_workbench_projection as workbench
    from dashboard.factory_history import score_text

    stored = [report.report_status(stage, status, "succeeded") for stage, status in
              (("screening", "passed"), ("oos", "passed"), ("walk_forward", "failed"), ("robustness", "failed"), ("monte_carlo", None))]
    statuses = report.apply_campaign_verdict(stored, ("survivor", "awaiting_owner_review", ""))
    assert statuses[2:4] == ["Failed", "Failed"]
    chip = report.gates_chip(statuses, {"walk_forward": "3 of 18 windows"})  # Report header
    assert chip == "Passed the gates · Holds over time: failed (3 of 18 windows made money) · Stress test: failed"
    assert "close call" not in chip.lower()
    assert score_text(dict(zip(report.SCORE_STAGES, statuses[2:]))).startswith("Holds over time: failed, Stress test: failed")  # Factory log line
    today_chip = workbench.overall_status(statuses, survivor=True)  # the Today / grid chip
    assert today_chip == "Passed the gates · Holds over time: failed · Stress test: failed"


def test_our_side_settings_mismatch_is_cant_test_never_failed() -> None:
    row = ("screened_out", "oos", "source-lock parameters do not match the run configuration")
    statuses = report.apply_campaign_verdict(["Passed", "Failed", "Can't test", "Can't test", "Can't test"], row)
    assert statuses == ["Passed", "Can't test", "Can't test", "Can't test", "Can't test"]
    assert report.apply_campaign_verdict(["Passed"] * 5, ("screened_out", "oos", "test did not pass"))[1] == "Failed"


def test_survivor_log_line_reads_the_same_recorded_stages_as_the_report(monkeypatch) -> None:
    from dashboard.factory_history import event_sentence

    seen = {}

    def fake_idea(candidate_id, *, run_id=None, database=None):
        seen["run_id"] = run_id
        tests = [{"stage": "walk_forward", "status": "failed"}, {"stage": "robustness", "status": "failed"}, {"stage": "monte_carlo", "status": "passed"}]
        return {"available": True, "tests": tests, "runs": {stage: {"run_id": f"run_{stage}", "status": "succeeded"} for stage in report.SCORE_STAGES}}

    monkeypatch.setattr(report, "load_idea", fake_idea)
    scores = report.score_statuses("qfc_a", "unused.sqlite3", run_id="run_screening")
    assert seen["run_id"] == "run_screening"  # that test's own stage runs
    event = {"state": "survivor", "reason_code": "awaiting_owner_review", "reason_detail": ""}
    assert event_sentence(event, "SPY inside-bar", "Codex", scores)[0].endswith("scores: Holds over time: failed, Stress test: failed, Shuffle test: passed.")


def test_unscored_luck_test_has_one_phrase_from_the_recorded_numbers() -> None:
    assert report.too_few_phrase("Needs at least 10 results to shuffle; it had 5.") == "Not scored — not enough data (5 of 10 needed)"
    tests = [{"stage": "walk_forward", "label": "Holds over time", "status": "Failed", "value": "3 of 18 windows", "fraction": 3 / 18},
             {"stage": "robustness", "label": "Stress test", "status": "Failed", "value": "19 of 29 checks", "fraction": 19 / 29},
             {"stage": "monte_carlo", "label": "Shuffle test", "status": "Not scored", "value": "Not scored — not enough data (5 of 10 needed)", "fraction": None}]
    assert report.gates_line(tests) == [("Passed the gates", "green"), (" · Holds over time: failed (3 of 18 windows made money)", "red"),
                                        (" · Stress test: failed (19 of 29 checks passed)", "red"), (" · Shuffle test: not scored — not enough data (5 of 10 needed)", "grey")]


def test_every_test_card_states_its_passes_if_rule() -> None:
    assert set(report.RULES) == {stage for stage, _label in report.STAGES}
    assert all(rule.startswith("Passes if") for rule in report.RULES.values())
    for stage in report.RULES:
        measure = report._test_measure(stage, {"run_id": None}, {}, {"periods": [], "checks": []}, None, None)
        assert measure["rule"] == report.RULES[stage]


def test_shuffle_card_line_is_the_measured_result_not_the_rule() -> None:
    from dashboard.idea_results_projection import check_rows, shuffle_result_line
    normalized = {"threshold_results": [{"threshold_id": "loss_probability", "status": "passed", "observed": 0.08, "threshold": 0.25},
                                        {"threshold_id": "lower_percentile_return", "status": "passed", "observed": -0.012, "threshold": -0.05}]}
    line = shuffle_result_line(check_rows(normalized))
    assert "Shuffles that lost money 8% (needs 25%)" in line and "Worst-case shuffle return" in line
    assert "Shuffled trades still made money" not in line and shuffle_result_line([]) == ""


def test_shuffle_panel_names_the_test_and_keeps_the_luck_score_on_its_own_line() -> None:
    ui = pytest.importorskip("dashboard.ui.idea_report")
    test = {"stage": "monte_carlo", "run_id": "r", "detail": {"checks": [{"check": "Shuffles that lost money", "measured": "8.0%", "needed": "25.0%"}]}}
    panel = str(ui.luck_panel({"tests": [test], "luck": 0.874}))
    assert "Shuffle test" in panel and "Is it luck?" not in panel and "Luck score" in panel and "0.87" in panel
    assert "not scored" in str(ui.luck_panel({"tests": [test], "luck": None}))


def test_cost_screen_line_names_the_screen_not_a_positive_sharpe() -> None:
    from dashboard import idea_results_projection as results
    card = results._test_card(None, "screening", "Survives costs", {"run_id": "r"}, {"screening_count": 3, "screened_out_count": 2})
    assert card["line"].startswith("1 of 3 settings cleared the cost screen") and "made money" not in card["line"]
