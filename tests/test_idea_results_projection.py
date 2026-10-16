"""One-page-per-idea Results projection: plain words, verdict, bar size and whole-period trades."""

from __future__ import annotations

from dashboard import idea_results_projection as projection


def _test(stage: str, status: str | None) -> dict:
    return {"stage": stage, "label": dict(projection.STAGES)[stage], "status": status}


def test_weak_scores_never_fail_an_idea_that_passed_costs_and_unseen_data() -> None:
    tests = [_test("screening", "passed"), _test("oos", "passed"), _test("walk_forward", "failed"),
             _test("robustness", "failed"), _test("monte_carlo", "insufficient_evidence")]
    assert projection._verdict(tests) == ("Passed the costs and unseen-data tests", "teal")
    tests[1]["status"] = "failed"
    assert projection._verdict(tests) == ("Failed at: unseen data", "red")
    tests[1]["failure"] = "scored 0.48, needed 0.50"
    assert projection._verdict(tests) == ("Failed at: unseen data — scored 0.48, needed 0.50", "red")


def test_failure_score_reads_the_best_training_result_saved_rejection() -> None:
    report = {"training_results": [
        {"sharpe_ratio": 0.31, "screening_rejection_reasons": "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.31."},
        {"sharpe_ratio": 0.4766, "screening_rejection_reasons": "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.47664662150289044."},
    ]}
    assert projection.failure_score(report) == "scored 0.48, needed 0.50"
    assert projection.failure_score({}) == ""


def test_stage_runs_follow_the_newest_campaign_and_never_mix_in_older_runs() -> None:
    import sqlite3

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE experiment_runs (run_id, configuration_id, stage, status, created_at, environment_json)")
    rows = [  # an older campaign that reached the shuffle test, then a newer one that stopped at unseen data
        ("s1", "screening", "t1", None), ("o1", "oos", "t2", "s1"), ("w1", "walk_forward", "t3", "o1"), ("m1", "monte_carlo", "t4", "w1"),
        ("s2", "screening", "t5", None), ("o2", "oos", "t6", "s2"),
    ]
    for run_id, stage, created, source in rows:
        environment = '{"filter_handoff": {"source_run_id": "%s"}}' % source if source else "{}"
        connection.execute("INSERT INTO experiment_runs VALUES (?, 'c', ?, 'succeeded', ?, ?)", [run_id, stage, created, environment])
    runs = projection._stage_runs(connection, "c")
    assert {stage: run["run_id"] for stage, run in runs.items()} == {"screening": "s2", "oos": "o2"}
    assert projection._verdict([_test("screening", "passed"), _test("oos", None)]) == ("Still being tested", "blue")


def test_saved_reasons_and_check_names_read_as_plain_words() -> None:
    assert projection.plain_reason("requires at least 10 observations; received 8") == "Needs at least 10 results to shuffle; it had 8."
    assert "training years" in projection.plain_reason("training screening produced no passing candidates; selection was not evaluated")
    assert projection._check_name("bearish|high_volatility:minimum_return") == "Falling market, big swings: return at least"
    assert projection._check_name("worst_drawdown") == "Worst drop from peak"


def test_bar_size_is_the_finest_that_fits_the_chart() -> None:
    assert projection._auto_interval(1_500) == "5m"
    assert projection._auto_interval(5_000) == "15m"
    assert projection._auto_interval(7_000) == "1h"
    assert projection._auto_interval(95_000) == "1D"


def test_trade_list_carries_a_running_total_in_trade_order() -> None:
    rows = projection._with_cumulative([{"trade_id": "0", "pnl": 10.0}, {"trade_id": "1", "pnl": None}, {"trade_id": "2", "pnl": -4.5}])
    assert [row["cum_pnl"] for row in rows] == [10.0, 10.0, 5.5]
    assert rows[1]["pnl"] is None


def test_long_account_curves_are_thinned_but_keep_the_whole_period() -> None:
    rows = [{"timestamp": f"t{index:05d}", "value": float(index)} for index in range(5_001)]
    thinned = projection._thin(rows)
    assert len(thinned) <= projection.EQUITY_LIMIT + 1
    assert thinned[0] == rows[0] and thinned[-1] == rows[-1]


def test_a_test_that_never_ran_has_no_trade_view() -> None:
    assert projection.load_trade_view({"runs": {}}, "oos")["available"] is False
    assert projection.load_trade_view({"runs": {"walk_forward": {"run_id": "r"}}}, "walk_forward")["available"] is False


def test_check_numbers_read_in_their_own_unit() -> None:
    value = projection._check_value
    assert [value("worst_drawdown", .0173), value("bearish|high_volatility:minimum_return", -.0024), value("x:maximum_drawdown", .35)] == ["1.73%", "-0.24%", "35%"]
    assert [value("required_pass_proportion", .6), value("locked_point", 1), value("locked_point", None)] == ["60%", "100%", "—"]
    assert [value("a:minimum_sharpe", -13.2269), value("a:minimum_observations", 91893.0), value("minimum_valid_neighbors", 3)] == ["-13.23", "91,893", "3"]
