"""Plain-English labels for auto-tester idea states, shared by dashboard pages.

The auto-tester writes campaign events (state, reason_code); the latest event per
idea decides its state. This module only translates; it never decides.
"""

from __future__ import annotations

import re
from typing import Any

TESTING = "Testing"
CANT_TEST = "Can't test yet"
DUPLICATE = "Duplicate"
FAILED_TESTING = "Screened out"
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
    ("survivor", "awaiting_owner_review"): "Passed the gates; waiting for you",
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


# Screening rule messages look like
# "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.08." joined by " | ".
_RULE_MESSAGE = re.compile(r"(?P<metric>\w+) failed: expected (?P<op>[<>]=?) (?P<need>\S+) \((?:inclusive|exclusive)\); observed (?P<seen>.+?)\.?\s*$")
_METRIC_WORDS: dict[str, tuple[str, str]] = {
    "number_of_trades": ("Trades", "count"),
    "total_return": ("Return", "percent"),
    "annualized_return": ("Yearly return", "percent"),
    "sharpe_ratio": ("Sharpe", "ratio"),
    "max_drawdown": ("Biggest drop", "drop"),
    "win_rate": ("Win rate", "percent"),
}


def _number(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def _show(value: float | None, kind: str) -> str:
    if value is None:
        return "no value"
    if kind == "count":
        return f"{value:,.0f}"
    if kind == "ratio":
        return f"{value:.2f}"
    return f"{abs(value) * 100 if kind == 'drop' else value * 100:.1f}%"


def plain_rejection_reasons(text: Any) -> list[str]:
    """Plain sentences for stored screening rejection reasons: which rule missed, by how much."""
    sentences: list[str] = []
    for part in str(text or "").split("|"):
        part = part.strip()
        if not part:
            continue
        if part.endswith("the entry rule never fired in this period"):
            sentences.append("No trades: the entry rule never fired in this period")
            continue
        match = _RULE_MESSAGE.match(part)
        if not match or match["metric"] not in _METRIC_WORDS:
            sentences.append(part)
            continue
        name, kind = _METRIC_WORDS[match["metric"]]
        need, seen = _show(_number(match["need"]), kind), _show(_number(match["seen"]), kind)
        if kind == "drop":
            sentences.append(f"{name} {seen} vs {need} allowed")
        else:
            sentences.append(f"{name} {seen} vs {need} needed after costs" if kind in {"ratio", "percent"} and match["metric"] != "win_rate" else f"{name} {seen} vs {need} needed")
    return sentences


def plain_reason_detail(text: Any) -> str:
    """Owner-facing wording for stored campaign notes that name internal locks."""
    value = str(text or "")
    if "Protected test remains locked" in value:
        return "Passed the gates. Paper trading is parked, so nothing is traded."
    return value


def stage_verdict(status: Any, passed: int | None, results: int | None, *, idea_passed: bool = False) -> tuple[str, str]:
    """(word, colour) saying whether a test was passed, not merely whether it ran."""
    status = str(status or "")
    if status in {"created", "running"}:
        return "Running", "blue"
    if status != "succeeded":
        return "Crashed", "red"
    if results:
        return ("Passed", "teal") if passed else ("Failed", "red")
    return ("Passed", "teal") if idea_passed else ("Done", "gray")


__all__ = [
    "plain_reason_detail", "plain_rejection_reasons", "stage_verdict",
    "LIFECYCLE_LABELS", "LIFECYCLE_ORDER", "STATE_LABELS", "REASON_WORDS",
    "lifecycle_label", "plain_status", "reason_words", "state_label",
]
