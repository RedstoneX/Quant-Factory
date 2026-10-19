"""Each Report card crashes only from its own stage's run; the campaign's failed state never paints a card."""
from __future__ import annotations

from dashboard import idea_report_projection as report
from dashboard import idea_results_projection as results


def test_walk_forward_scored_robustness_crashed_monte_carlo_not_run(monkeypatch, tmp_path) -> None:
    folds = [{"test_metrics": {"total_return": 0.1 if i < 10 else -0.1}} for i in range(46)]
    monkeypatch.setattr(results, "_evidence", lambda database, run_id, stage: {"folds": folds, "normalized_evidence": {"status": "failed"}} if stage == "walk_forward" else {})
    wf = results._test_card(tmp_path, "walk_forward", "Holds over time", {"run_id": "w", "status": "succeeded"}, {})
    rb = results._test_card(tmp_path, "robustness", "Stress test", {"run_id": "r", "status": "failed"}, {})
    mc = results._test_card(tmp_path, "monte_carlo", "Luck test", None, {})
    assert wf["line"] == "10 of 46 rolling periods made money."
    assert (rb["status"], rb["status_text"]) == ("crashed", "Crashed")
    assert mc["status"] is None and mc["run_id"] is None
    statuses = [report.report_status(stage, card["status"] if card["status"] in ("passed", "failed") else None, run)
                for stage, card, run in (("walk_forward", wf, "succeeded"), ("robustness", rb, "failed"), ("monte_carlo", mc, None))]
    assert statuses == ["Failed", "Crashed", "Can't test"]  # the walk-forward score keeps its own recorded status
    assert report.apply_campaign_verdict(statuses, ("failed", "run_error", "Filter-stage adapter outcome is unknown")) == statuses
