"""Factory oversight projection: pill states, grouped old runs, submitter names, measured-vs-needed, typical test time."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard.factory_history import event_sentence, is_close_call, parse_measured_needed, short_reason, is_restart, crash_label, submitter_label, timeline_rows, clock
from dashboard.factory_overview import (
    crash_alerts, drain_state, group_abandoned, header_pill, headline_for, latest_not_after, median_minutes, not_after, memory_health, price_data_rows, run_outcome,
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


def _event(event_id: int, cid: str, state: str, at: str, code: str = "", detail: str = "") -> dict:
    return {"event_id": event_id, "candidate_id": cid, "state": state, "reason_code": code, "reason_detail": detail, "run_id": None, "created_at": at}


def test_old_unclosed_runs_become_one_grouped_alert() -> None:
    from dashboard.factory_history import unclosed_starts

    events = [_event(i, f"c{i}", "running", f"2026-10-1{i}T10:00:00Z") for i in range(1, 5)]
    events.append(_event(10, "fresh", "running", "2026-10-19T14:50:00Z"))  # under 3x the typical time: not grouped
    events += [_event(11, "requeued", "running", "2026-10-14T10:00:00Z"), _event(12, "requeued", "queued", "2026-10-14T11:00:00Z", "requeued_after_restart")]  # the record says how it ended
    events += [_event(13, "again", "running", "2026-10-15T10:00:00Z"), _event(14, "again", "running", "2026-10-15T12:00:00Z"), _event(15, "again", "survivor", "2026-10-15T12:30:00Z")]
    group = group_abandoned(unclosed_starts(events), {}, NOW, typical=20)
    assert group["count"] == 4 and group["title"] == "4 old runs were never closed (oldest Oct 11)"
    assert len(group["items"]) == 4
    assert group_abandoned(unclosed_starts(events[4:]), {}, NOW, typical=20) is None


def test_a_start_followed_by_a_requeue_or_a_new_start_is_interrupted_not_failed() -> None:
    from dashboard.factory_history import OUTCOME_WORDS, tests_from_events

    events = [_event(1, "a", "running", "2026-10-19T10:00:00Z"), _event(2, "a", "queued", "2026-10-19T10:30:00Z", "requeued_after_restart"),
              _event(3, "b", "running", "2026-10-19T11:00:00Z"), _event(4, "b", "running", "2026-10-19T11:20:00Z"), _event(5, "b", "screened_out", "2026-10-19T11:40:00Z", "oos", "x"),
              _event(6, "c", "running", "2026-10-19T12:00:00Z"), _event(7, "c", "screened_out", "2026-10-19T12:10:00Z", "oos", "source-lock parameters do not match the run configuration")]
    tests = tests_from_events(events, {}, NOW)
    assert [(t["candidate_id"], t["outcome"]) for t in tests] == [("a", "interrupted"), ("b", "interrupted"), ("b", "failed"), ("c", "unchecked")]
    assert tests[0]["completed_at"] == "2026-10-19T10:30:00Z" and OUTCOME_WORDS["interrupted"] == "Interrupted — re-queued"


def test_unseen_loss_and_our_side_mismatch_log_lines() -> None:
    loss = _event(1, "a", "screened_out", "2026-10-19T10:00:00Z", "oos", "out-of-sample run has no single valid source-lock artifact: source-lock evidence is invalid: test did not pass")
    saved = {"total_return": -0.019, "sharpe_ratio": -0.18, "_training_metrics": {"total_return": 0.32}}
    assert event_sentence(loss, "SPY ORB", "Codex", None, saved) == ("“SPY ORB” lost money on years it never saw (−1.9%, Sharpe −0.18); built-on years +32%.", "grey")
    assert event_sentence(loss, "SPY ORB", "Codex")[0] == "“SPY ORB” lost money on years it never saw."
    mismatch = _event(2, "b", "screened_out", "2026-10-19T10:00:00Z", "oos", "source-lock parameters do not match the run configuration")
    assert event_sentence(mismatch, "QQQ", "Codex") == ("“QQQ”: couldn't be checked — a settings mismatch on our side.", "grey")


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
    assert memory_health(meminfo) == {"tone": "green", "value": "50% free"}
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


def test_headline_says_all_clear_only_when_nothing_needs_a_look_and_every_check_is_green() -> None:
    assert headline_for(running=0, waiting=0, looks=0, warnings=0) == ("All clear", "green")
    assert headline_for(running=0, waiting=0, looks=0, warnings=2) == ("Idle. 2 health warnings.", "amber")
    assert headline_for(running=0, waiting=0, looks=1, warnings=1) == ("Idle. 1 thing needs a look. 1 health warning.", "amber")
    assert headline_for(running=1, waiting=2, looks=0, warnings=0) == ("1 test running, 2 waiting. All clear.", "text")
    assert headline_for(running=1, waiting=0, looks=0, warnings=1)[1] == "amber"


def test_nothing_is_shown_after_the_as_of_time() -> None:
    rows = [{"created_at": "2026-10-19T14:59:00Z"}, {"created_at": "2026-10-19T15:00:00+00:00"}, {"created_at": "2026-10-19T15:00:01Z"}, {"created_at": None}]
    assert [r["created_at"] for r in not_after(rows, "created_at", NOW)] == ["2026-10-19T14:59:00Z", "2026-10-19T15:00:00+00:00", None]
    assert latest_not_after(["2026-10-19T14:00:00Z", "2026-10-19T16:30:00Z", None], NOW) == "2026-10-19T14:00:00Z"  # a Grok request after the as-of time is ignored
    assert latest_not_after(["2026-10-19T16:30:00Z"], NOW) is None


def test_every_timestamp_format_parses_to_the_same_utc_moment() -> None:
    from dashboard.factory_history import et_day_start, utc
    same = {utc(v) for v in ("2026-10-18T23:18:45Z", "2026-10-18T23:18:45+00:00", "2026-10-18T23:18:45", "2026-10-18 19:18:45-04:00", "2026-10-18T23:18:45.000000Z")}
    assert same == {datetime(2026, 10, 18, 23, 18, 45, tzinfo=timezone.utc)}
    late = datetime(2026, 10, 19, 2, 6, tzinfo=timezone.utc)  # 22:06 Sunday in New York
    assert et_day_start(late) == datetime(2026, 10, 18, 4, 0, tzinfo=timezone.utc)
    assert utc("2026-10-18T23:18:45Z") >= et_day_start(late)  # 19:18 ET is today, so it counts as finished today


def test_log_times_show_the_weekday_when_from_an_earlier_day() -> None:
    late = datetime(2026, 10, 19, 2, 6, tzinfo=timezone.utc)
    assert clock("2026-10-18T23:18:45Z", late) == "19:18"
    assert clock("2026-10-16T21:51:00Z", late) == "Fri 17:51"


def test_hourly_chart_empty_message_and_whole_number_ticks() -> None:
    from dashboard.ui.factory_oversight import hourly_figure
    base = datetime(2026, 10, 18, 12)
    rows = [{"hour": base + timedelta(hours=i), "failed": 0, "close": 0, "passed": 0, "crashed": 0, "running": 0} for i in range(48)]
    empty = hourly_figure(rows)
    assert [a.text for a in empty.layout.annotations] == ["No tests finished in the last 48 hours"] and empty.layout.yaxis.visible is False
    rows[5]["passed"] = 2
    full = hourly_figure(rows)
    assert full.layout.yaxis.tickformat == "d" and full.layout.yaxis.dtick == 1


def test_timeline_has_one_now_marker_and_failed_is_slate() -> None:
    from dashboard.ui.factory_oversight import OUTCOME_COLOR, timeline_figure
    figure = timeline_figure([], NOW.replace(tzinfo=None))
    assert [a.text for a in figure.layout.annotations if a.text == "now"] == ["now"]
    assert len([s for s in figure.layout.shapes if s.line.dash == "dash"]) == 1
    assert OUTCOME_COLOR["failed"] == "#4B5160"


def test_a_crash_with_no_research_run_is_counted_the_same_by_every_panel(tmp_path: Path, monkeypatch) -> None:
    """campaign_events are the only record of tests: tiles, timeline, per-hour chart and log must all agree, even for a crash that never wrote a research run."""
    import sqlite3
    from dashboard import factory_overview as overview

    research = sqlite3.connect(":memory:")
    research.row_factory = sqlite3.Row
    research.executescript("""
        CREATE TABLE experiment_runs (run_id, configuration_id, stage, status, started_at, completed_at, created_at, error_summary);
        CREATE TABLE experiment_configurations (configuration_id, experiment_id, strategy_id, canonical_config_json);
        CREATE TABLE idea_drafts (draft_id, title, candidate_json, configuration_id);
        CREATE TABLE parameter_results (run_id, screening_status);
        CREATE TABLE run_operator_events (run_id, source, message);
        CREATE TEMP TABLE qf_campaign_admissions (candidate_id, policy_id, state, reason_code, reason_detail);
        INSERT INTO idea_drafts VALUES ('a', 'Idea A', '{}', NULL), ('b', 'Idea B', '{}', NULL), ('c', 'Idea C', '{}', NULL), ('d', 'Idea D', '{}', NULL);""")
    monkeypatch.setattr(overview, "_validated_connection", lambda _path: (research, None))
    gateway = tmp_path / "gateway.sqlite3"
    db = sqlite3.connect(gateway)
    db.execute("CREATE TABLE campaign_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT, policy_id TEXT, state TEXT, reason_code TEXT, reason_detail TEXT, packet_sha256 TEXT, run_id TEXT, created_at TEXT)")
    miss = "sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.10."
    events = [("d", "running", "started", None, "2026-10-16T17:00:00Z"), ("d", "screened_out", "screening", miss, "2026-10-16T17:05:00Z"),
              ("a", "running", "started", None, "2026-10-18T21:00:00Z"), ("a", "screened_out", "screening", miss, "2026-10-18T21:10:00Z"),
              ("b", "running", "started", None, "2026-10-18T21:20:00+00:00"), ("b", "failed", "run_error", "the test process exited with code -9 before reporting", "2026-10-18T21:25:00+00:00"),
              ("c", "running", "started", None, "2026-10-18T22:00:00"), ("c", "survivor", "awaiting_owner_review", None, "2026-10-18T22:10:00")]
    for cid, state, code, detail, at in events:
        db.execute("INSERT INTO campaign_events (candidate_id,policy_id,state,reason_code,reason_detail,created_at) VALUES (?,?,?,?,?,?)", (cid, "p", state, code, detail, at))
    db.commit()
    db.close()
    now = datetime(2026, 10, 19, 2, 6, tzinfo=timezone.utc)  # Sunday 22:06 Eastern: three tests today, one on Friday
    data = overview.load_factory_overview(database=tmp_path / "x", gateway=str(gateway), now=now, drain_marker=tmp_path / "none")
    assert data["available"], data["message"]
    tile = {t["label"]: t["value"] for t in data["tiles"]}
    assert (tile["Runs today"], tile["Runs crashed today"]) == ("3", "1")
    assert [t["sub"] for t in data["tiles"] if t["label"] == "Runs today"] == ["1 passed · 1 failed · 1 crashed"]
    assert sorted(row["outcome"] for row in data["timeline"]) == ["crashed", "failed", "passed"]
    assert sum(row[k] for row in data["hourly"] for k in ("failed", "close", "passed", "crashed")) == 3 and sum(row["crashed"] for row in data["hourly"]) == 1
    texts = [row["text"] for row in data["log"]]
    assert sum("code -9" in t for t in texts) == 1 and sum("Idea" in t and "failed" in t for t in texts) >= 2
    assert any(row["t"].startswith("Fri") for row in data["log"])  # the earlier day is labelled
