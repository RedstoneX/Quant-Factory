"""Plain-English labels for auto-tester idea states, shared by dashboard pages.

The auto-tester writes campaign events (state, reason_code); the latest event per
idea decides its state. This module only translates; it never decides.
"""

from __future__ import annotations

from typing import Any

TESTING = "Testing"
CANT_TEST = "Can't test yet"
DUPLICATE = "Duplicate"
FAILED_TESTING = "Failed testing"
PASSED = "Passed — needs your review"
CRASHED = "Test crashed"

STATE_LABELS: dict[str, str] = {
    "queued": TESTING,
    "running": TESTING,
    "admitted": TESTING,
    "implementation_blocked": CANT_TEST,
    "duplicate_closed": DUPLICATE,
    "screened_out": FAILED_TESTING,
    "survivor": PASSED,
    "failed": CRASHED,
}

REASON_WORDS: dict[tuple[str, str], str] = {
    ("queued", "waiting"): "Waiting for its turn to be tested",
    ("queued", "requeued_after_restart"): "Put back in line after a restart",
    ("running", "started"): "Test is running now",
    ("implementation_blocked", "rules_missing"): "No trading rules",
    ("implementation_blocked", "rules_invalid"): "Rules have an error",
    ("implementation_blocked", "data_unavailable"): "No data for this market",
    ("duplicate_closed", "same_rules"): "Same rules as an idea already tested",
    ("screened_out", "stage"): "Did not pass a testing stage",
    ("survivor", "awaiting_owner_review"): "Passed every test; waiting for you",
    ("failed", "run_error"): "The test hit an error",
    ("failed", "run_timeout"): "The test ran out of time",
}

# Dashboard grouping keys (internal) -> plain labels.
LIFECYCLE_LABELS: dict[str, str] = {
    "survivor": PASSED,
    "advancing": TESTING,
    "blocked": CANT_TEST,
    "duplicate": DUPLICATE,
    "crashed": CRASHED,
    "needs_review": "Needs review",
    "rejected": FAILED_TESTING,
    "received": "Received",
    "all": "All",
}

LIFECYCLE_ORDER = ("survivor", "advancing", "blocked", "duplicate", "crashed", "needs_review", "rejected", "all")


def state_label(state: Any) -> str | None:
    """Plain label for a campaign state, or None when the state is not known."""
    return STATE_LABELS.get(str(state or ""))


def reason_words(state: Any, reason_code: Any) -> str | None:
    """Plain words for a (state, reason_code) pair, or None when not known."""
    return REASON_WORDS.get((str(state or ""), str(reason_code or "")))


def plain_status(state: Any, reason_code: Any = None) -> tuple[str, str]:
    """Return (label, reason in words) for the latest campaign event of an idea."""
    label = state_label(state)
    if label is None:
        return "Not in testing", ""
    return label, reason_words(state, reason_code) or ""


def lifecycle_label(key: Any) -> str:
    text = str(key or "received")
    return LIFECYCLE_LABELS.get(text, text.replace("_", " ").title())


__all__ = [
    "LIFECYCLE_LABELS", "LIFECYCLE_ORDER", "STATE_LABELS", "REASON_WORDS",
    "lifecycle_label", "plain_status", "reason_words", "state_label",
]
