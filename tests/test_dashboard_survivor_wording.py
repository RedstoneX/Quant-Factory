"""A survivor passed the two gates only; Holds over time, Stress test and Luck test are recorded scores (owner ruling 15 Oct)."""
from __future__ import annotations

from dashboard.factory_history import event_sentence, score_text
from dashboard.plain_labels import REASON_WORDS

SURVIVOR = {"state": "survivor", "reason_code": "awaiting_owner_review", "reason_detail": ""}


def test_log_line_with_mixed_scores() -> None:
    text, tone = event_sentence(SURVIVOR, "SPY ORB", "Codex", {"walk_forward": "Passed", "robustness": "Close call", "monte_carlo": "Can't test"})
    assert text == "“SPY ORB” passed the gates (costs, unseen data); scores: Holds over time ✓, Stress test ✗, Luck test — not enough data."
    assert tone == "green"


def test_missing_scores_show_a_dash_and_no_line_says_every_test() -> None:
    assert score_text(None) == "Holds over time —, Stress test —, Luck test — not enough data"
    assert score_text({"walk_forward": "Failed", "robustness": "Passed", "monte_carlo": "Passed"}) == "Holds over time ✗, Stress test ✓, Luck test ✓"
    assert "every test" not in event_sentence(SURVIVOR, "X", "Codex")[0]


def test_survivor_status_label() -> None:
    assert REASON_WORDS[("survivor", "awaiting_owner_review")] == "Passed the gates; waiting for you"
