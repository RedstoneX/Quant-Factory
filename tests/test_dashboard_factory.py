"""Factory oversight projection: pill states, grouped old runs, submitter names, measured-vs-needed, typical test time."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.factory_projection import (
    drain_state, event_sentence, group_abandoned, header_pill, is_close_call, median_minutes, memory_health,
    parse_measured_needed, price_data_rows, run_outcome, submitter_label,
)

NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def test_pill_states_in_priority_order() -> None:
    assert header_pill(running=1, draining=False, last_finished_crashed=False) == {"label": "Running", "tone": "green"}
    assert header_pill(running=0, draining=False, last_finished_crashed=False) == {"label": "Idle", "tone": "grey"}
    assert header_pill(running=0, draining=True, last_finished_crashed=False) == {"label": "Paused for update", "tone": "amber"}
    assert header_pill(running=0, draining=False, last_finished_crashed=True) == {"label": "Last test crashed", "tone": "red"}
    assert header_pill(running=1, draining=False, last_finished_crashed=True)["label"] == "Running"  # the next test replaces the crash state


def test_drain_marker_must_exist_and_be_under_two_hours_old(tmp_path: Path) -> None:
    marker = tmp_path / "deploy-drain"
    assert drain_state(marker) is False
    marker.write_text("x")
    assert drain_state(marker) is True
    old = time.time() - 3 * 3600
    os.utime(marker, (old, old))
    assert drain_state(marker) is False


def _run(run_id: str, status: str, cohort: str, started: str, title: str = "Idea") -> dict:
    return {"run_id": run_id, "status": status, "cohort": cohort, "started_at": started, "title": title, "candidate_id": "c-" + run_id, "survivor_count": 0}


def test_old_unclosed_runs_become_one_grouped_alert() -> None:
    runs = [_run(f"r{i}", "running", "failed", f"2026-10-1{i}T10:00:00Z") for i in range(1, 5)]
    runs.append(_run("fresh", "running", "failed", "2026-10-19T14:00:00Z"))  # under a day: not grouped
    runs.append(_run("live", "running", "open", "2026-10-10T10:00:00Z"))  # the factory still owns it
    group = group_abandoned(runs, NOW)
    assert group["count"] == 4 and group["title"] == "4 old runs were never closed (oldest Oct 11)"
    assert len(group["items"]) == 4
    assert group_abandoned(runs[4:], NOW) is None


def test_submitter_is_exactly_as_recorded() -> None:
    assert submitter_label("grok-remote") == "Grok"
    assert submitter_label("codex-local") == "Codex"
    assert submitter_label("claude-local") == "claude-local"
    assert submitter_label(None) == "Unknown"


def test_measured_vs_needed_parsing_and_close_call() -> None:
    detail = "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.33128."
    parsed = parse_measured_needed(detail)
    assert parsed["text"] == "Sharpe 0.33, needed 0.50"
    assert not is_close_call(detail)
    assert is_close_call("sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.46.")
    assert parse_measured_needed("requires at least 10 observations; received 8") is None
    sentence, tone = event_sentence({"state": "screened_out", "reason_code": "screening", "reason_detail": detail}, "SPY ORB", "Grok")
    assert sentence == "“SPY ORB” failed Survives costs (Sharpe 0.33, needed 0.50)." and tone == "grey"
    assert event_sentence({"state": "queued", "reason_code": "waiting", "reason_detail": ""}, "SPY ORB", "Codex")[0] == "Codex queued “SPY ORB”."


def test_median_test_time_uses_last_50_finished_runs() -> None:
    base = datetime(2026, 10, 19, 10, 0)
    pairs = [(base.isoformat() + "Z", (base + timedelta(minutes=m)).isoformat() + "Z") for m in (2, 4, 10)]
    assert median_minutes(pairs) == 4
    assert median_minutes([]) is None
    assert median_minutes([("2026-10-19T10:00:00Z", None)]) is None
    many = [(base.isoformat() + "Z", (base + timedelta(minutes=1)).isoformat() + "Z")] * 50 + [(base.isoformat() + "Z", (base + timedelta(minutes=99)).isoformat() + "Z")] * 60
    assert median_minutes(many) == 1  # only the newest 50 count


def test_run_outcome_and_memory_and_prices(tmp_path: Path) -> None:
    assert run_outcome({**_run("a", "failed", "failed", "x")}, set()) == "crashed"
    assert run_outcome(_run("b", "succeeded", "completed", "x"), {"b"}) == "close"
    assert run_outcome({**_run("c", "succeeded", "completed", "x"), "survivor_count": 1}, set()) == "passed"
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:  1000 kB\nMemAvailable:  500 kB\n")
    assert memory_health(1, meminfo) == {"tone": "amber", "value": "50% free · 1 crash today"}
    (tmp_path / "spy.json").write_text('{"symbol": "SPY", "latest_timestamp": "2026-10-16T20:00:00Z"}')
    assert price_data_rows([tmp_path]) == [{"market": "SPY", "last": "Fri 16 Oct"}]
