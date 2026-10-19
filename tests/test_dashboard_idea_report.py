"""Data mapping for the Idea report page: test labels, the five statuses, the never-ran card, series shaping."""

from __future__ import annotations

import pandas as pd
import pytest

from dashboard import idea_report_projection as report


def test_labels_are_the_agreed_plain_words() -> None:
    assert report.TEST_LABELS == {"screening": "Survives costs", "oos": "Unseen data", "walk_forward": "Holds over time",
                                  "robustness": "Stress test", "monte_carlo": "Luck test"}


@pytest.mark.parametrize(("stage", "stored", "run", "expected"), [
    ("screening", "passed", "succeeded", "Passed"),
    ("oos", "failed", "succeeded", "Failed"),
    ("screening", "failed", "succeeded", "Failed"),
    ("walk_forward", "failed", "succeeded", "Close call"),
    ("robustness", "failed", "succeeded", "Close call"),
    ("monte_carlo", "failed", "succeeded", "Close call"),
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
    assert report.overall_chip(_tests(["Passed", "Can't test", "Can't test", "Can't test", "Can't test"], 1)) == ("1 passed · 4 can't test", "grey")
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
    assert report.apply_campaign_verdict(stored, ("failed", "run_error"))[1] == "Crashed"
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
    assert out["rule"] == "Unseen data: made money on years it never saw (after costs)"
    assert out["scores"] == ["Built-on years: made money ✓ (Sharpe 0.48)", "Unseen years: made money ✓ (Sharpe -0.20)"]
