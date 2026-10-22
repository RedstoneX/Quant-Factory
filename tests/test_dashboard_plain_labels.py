from __future__ import annotations

import pytest

from dashboard.plain_labels import (
    LIFECYCLE_LABELS,
    LIFECYCLE_ORDER,
    REASON_WORDS,
    STATE_LABELS,
    lifecycle_label,
    plain_status,
)
from dashboard.ui.candidates import _outcome

CONTRACT = {
    "queued": ("Testing", ["waiting", "requeued_after_restart"]),
    "running": ("Testing", ["started"]),
    "implementation_blocked": ("Can't test yet", ["rules_missing", "rules_invalid", "data_unavailable"]),
    "duplicate_closed": ("Duplicate", ["same_rules"]),
    "screened_out": ("Screened out", ["stage"]),
    "survivor": ("Passed — needs your review", ["awaiting_owner_review"]),
    "failed": ("Test crashed", ["run_error", "run_timeout"]),
}
CASES = [(state, reason, label) for state, (label, reasons) in CONTRACT.items() for reason in reasons]


@pytest.mark.parametrize(("state", "reason", "label"), CASES)
def test_every_state_and_reason_has_a_plain_label_and_words(state, reason, label):
    got_label, words = plain_status(state, reason)
    assert got_label == label
    assert words and "_" not in words
    assert (state, reason) in REASON_WORDS


def test_blocked_reasons_are_the_requested_words():
    assert plain_status("implementation_blocked", "rules_missing")[1] == "No trading rules"
    assert plain_status("implementation_blocked", "rules_invalid")[1] == "Rules have an error"
    assert plain_status("implementation_blocked", "data_unavailable")[1] == "No data for this market"


def test_unknown_state_is_not_dressed_up_as_a_known_one():
    assert plain_status("something_new", "x") == ("Not in testing", "")
    assert plain_status(None) == ("Not in testing", "")


def test_rejected_bucket_is_relabelled_and_blocked_group_exists():
    assert lifecycle_label("rejected") == "Screened out"
    assert lifecycle_label("blocked") == "Can't test yet"
    assert lifecycle_label("advancing") == "Testing"
    assert lifecycle_label("survivor") == "Passed — needs your review"
    assert "blocked" in LIFECYCLE_ORDER
    assert all(key in LIFECYCLE_LABELS for key in LIFECYCLE_ORDER)
    assert "Rejected" not in LIFECYCLE_LABELS.values()


@pytest.mark.parametrize(("state", "reason", "label"), CASES)
def test_candidate_page_outcome_uses_the_plain_label(state, reason, label):
    lifecycle = {
        "queued": "advancing", "running": "advancing", "implementation_blocked": "blocked",
        "duplicate_closed": "duplicate", "screened_out": "rejected", "survivor": "survivor", "failed": "crashed",
    }[state]
    headline, detail = _outcome({"lifecycle": lifecycle, "campaign_state": state, "campaign_reason_code": reason})
    assert headline == label
    assert detail == plain_status(state, reason)[1]


def test_crashed_and_duplicate_have_their_own_groups_and_failed_testing_is_only_screened_out():
    assert lifecycle_label("duplicate") == "Duplicate"
    assert lifecycle_label("crashed") == "Test crashed"
    assert "duplicate" in LIFECYCLE_ORDER and "crashed" in LIFECYCLE_ORDER
    groups = {state: label for state, label in STATE_LABELS.items()}
    assert [s for s, label in groups.items() if label == "Screened out"] == ["screened_out"]


def test_projection_sql_sends_each_state_to_its_own_group():
    from dashboard.candidates_projection import COUNT_KEYS, _candidate_source

    sql = _candidate_source()
    assert "campaign_state='duplicate_closed' THEN 'duplicate'" in sql
    assert "campaign_state='failed' THEN 'crashed'" in sql
    assert "campaign_state='implementation_blocked' THEN 'blocked'" in sql
    rejected_line = next(line for line in sql.splitlines() if "THEN 'rejected'" in line and "campaign_state IN" in line)
    assert "duplicate_closed" not in rejected_line and "'failed'" not in rejected_line
    assert {"duplicate", "crashed", "blocked"} <= set(COUNT_KEYS)


def test_unseen_data_reasons_never_show_source_lock_text() -> None:
    from dashboard.plain_labels import plain_reason_detail, plain_unseen_reason, unseen_loss_text

    saved = {"total_return": -0.019, "sharpe_ratio": -0.18, "_training_metrics": {"total_return": 0.32}}
    assert unseen_loss_text(saved) == "lost money on years it never saw (−1.9%, Sharpe −0.18); built-on years +32%"
    assert unseen_loss_text(None) == "lost money on years it never saw"
    raw = ("out-of-sample run has no single valid source-lock artifact: source-lock evidence is invalid: test did not pass",
           "out-of-sample run has no single valid source-lock artifact: source-lock evidence is invalid: training screening produced no passing candidates; ",
           "out-of-sample run must contain exactly one valid source-lock artifact",
           "source-lock parameters do not match the run configuration")
    for text in raw:
        assert "source-lock" not in plain_reason_detail(text) and plain_unseen_reason(text)
    assert plain_reason_detail(raw[3]) == "Couldn't be checked — a settings mismatch on our side"
