"""Crashed-run wording: class from the reason code, follow-up only from the record."""

from __future__ import annotations

from datetime import datetime, timezone

from dashboard.factory_history import crash_sentence, event_sentence, log_rows

T0 = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 19, 14, 30, tzinfo=timezone.utc)


def _event(state: str, code: str, detail: str, at: datetime) -> dict:
    return {"candidate_id": "c1", "state": state, "reason_code": code, "reason_detail": detail, "created_at": at, "run_id": None}


def test_our_side_class_with_stage_and_blocked_followup() -> None:
    text = crash_sentence("Idea", "run_error", "FilterStageInvocationUnknownError: automatic rerun is blocked pending owner investigation", "robustness")
    assert text == "“Idea” crashed in the Stress test — our side; re-run blocked until checked."


def test_data_problem_class_with_no_followup() -> None:
    assert crash_sentence("Idea", "data_unavailable", "Verified local data could not be read", "screening") == "“Idea” crashed in the Survives costs — data problem."


def test_rerunning_only_when_later_queued_event_exists() -> None:
    failed = _event("failed", "run_error", "ValueError: bad rule", T0)
    assert event_sentence(failed, "Idea", "Grok", requeued=True)[0] == "“Idea” crashed — our side; re-running."
    assert event_sentence(failed, "Idea", "Grok")[0] == "“Idea” crashed — our side."
    rows = log_rows([_event("queued", "waiting", "", T1), failed], {"c1": "Idea"}, {}, [], now=T1)
    assert any(r["text"] == "“Idea” crashed — our side; re-running." and r["tone"] == "red" for r in rows)
