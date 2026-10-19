"""Factory oversight projection: pill states, grouped old runs, submitter names, measured-vs-needed, typical test time."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.factory_history import event_sentence, is_close_call, parse_measured_needed, short_reason, is_restart, crash_label, submitter_label, timeline_rows, clock
from dashboard.factory_overview import (
    crash_alerts, drain_state, group_abandoned, header_pill, median_minutes, memory_health, price_data_rows, run_outcome,
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


def test_timeline_block_is_capped_at_three_times_typical_and_marked() -> None:
    crashed = {**_run("a", "failed", "failed", "2026-10-19T08:00:00Z"), "completed_at": "2026-10-19T14:00:00Z", "outcome": "crashed"}
    quick = {**_run("b", "succeeded", "completed", "2026-10-19T14:10:00Z"), "completed_at": "2026-10-19T14:12:00Z", "outcome": "failed"}
    rows = timeline_rows([crashed, quick], NOW, 5.0)
    assert rows[0]["capped"] is True and rows[0]["minutes"] == 15
    assert rows[1]["capped"] is False and rows[1]["minutes"] == 2


def _crash(run_id: str, cid: str, when: str, error: str = "Test process lost in a deploy restart") -> dict:
    return {**_run(run_id, "failed", "failed", "2026-10-19T08:00:00Z"), "candidate_id": cid, "completed_at": when, "error_summary": error, "stage": "screening", "outcome": "crashed"}


def test_crash_alerts_collapse_duplicates_and_skip_handled_ideas() -> None:
    oom = "Ran out of memory"
    crashes = [_crash("r1", "c1", "2026-10-19T10:00:00Z", oom), _crash("r2", "c1", "2026-10-19T11:00:00Z", oom), _crash("r3", "c2", "2026-10-19T09:00:00Z", oom),
               _crash("r4", "c3", "2026-10-19T09:00:00Z")]  # c3: a server-restart stop is history, never an alert
    later = [{"candidate_id": "c2", "state": "queued", "created_at": "2026-10-19T09:30:00+00:00"},
             {"candidate_id": "c1", "state": "failed", "created_at": "2026-10-19T11:00:05+00:00"}]  # a crash event itself does not count as handling
    alerts = crash_alerts(crashes, later)
    assert [a["title"] for a in alerts] == ["Crashed: ran out of computer memory and was stopped ×2"]


def test_short_reason_is_sentence_case_plain_words() -> None:
    assert short_reason("Test process lost in a deploy restart on 14 Oct") == "stopped by a server restart"
    assert short_reason("Ran out of memory") == "ran out of computer memory and was stopped"


def test_utc_event_time_renders_in_eastern() -> None:
    assert clock("2026-10-18T23:18:48.806955+00:00") == "19:18"  # EDT is UTC-4
    assert clock("2026-12-18T23:18:00Z") == "18:18"  # EST is UTC-5
    rows = timeline_rows([{**_run("a", "succeeded", "completed", "2026-10-19T14:00:00Z"), "completed_at": "2026-10-19T14:02:00Z", "outcome": "failed"}], NOW)
    assert rows[0]["start"].hour == 10  # timeline hours are Eastern wall time


def test_restart_stops_are_history_and_crash_tile_names_main_reason() -> None:
    assert is_restart("Test process lost in a deploy restart")
    assert not is_restart("Ran out of memory")
    sentence, tone = event_sentence({"state": "failed", "reason_code": "run_error", "reason_detail": "Stopped by a server restart"}, "SPY ORB", "Grok")
    assert sentence == "“SPY ORB” stopped by a server restart, safe to re-run." and tone == "grey"
    assert crash_label("stopped by a server restart") == "server restarts"
