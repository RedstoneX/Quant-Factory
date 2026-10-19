"""Factory oversight: the 12-hour timeline rows, the plain-language event log and the helpers that turn events into words (read-only)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from dashboard.factory_projection import plain_error
from dashboard.time_display import EASTERN, eastern_label


STEPS = (("screening", "Survives costs"), ("oos", "Unseen data"), ("walk_forward", "Holds over time"), ("robustness", "Stress test"), ("monte_carlo", "Luck test"))


STEP_NAME = dict(STEPS)


SUBMITTERS = {"grok-remote": "Grok", "codex-local": "Codex"}


CLOSE_CALL_RATIO = 0.8  # measured at least 80% of the needed number counts as a close call


OUTCOMES = ("failed", "close", "passed", "crashed", "running")


OUTCOME_WORDS = {"failed": "Failed a test", "close": "Close call", "passed": "Passed", "crashed": "Crashed", "running": "Running"}


METRIC_WORDS = {"sharpe_ratio": "Sharpe", "sharpe": "Sharpe", "total_return": "Return", "max_drawdown": "Worst drop", "trade_count": "Trades", "trades": "Trades"}


_MEASURE = re.compile(r"(?P<metric>[A-Za-z_]+) failed: expected (?P<op>>=|<=|>|<)\s*(?P<needed>-?[\d.]+).*?observed (?P<observed>-?[\d.]+)", re.S)


def submitter_label(created_by: Any) -> str:
    """Exactly who the record says submitted it; an unknown id is shown as recorded, never guessed."""
    return SUBMITTERS.get(str(created_by or "").strip(), str(created_by or "").strip() or "Unknown")


def parse_measured_needed(detail: Any) -> dict[str, Any] | None:
    """'sharpe_ratio failed: expected >= 0.5 (inclusive); observed 0.34.' -> measured, needed, ratio and a plain phrase."""
    found = _MEASURE.search(str(detail or ""))
    if not found:
        return None
    label = METRIC_WORDS.get(found["metric"], found["metric"].replace("_", " ").capitalize())
    needed, observed = float(found["needed"]), float(found["observed"].rstrip("."))
    ratio = observed / needed if needed > 0 else None
    return {"metric": label, "measured": observed, "needed": needed, "ratio": ratio, "text": f"{label} {observed:.2f}, needed {needed:.2f}"}


def is_close_call(detail: Any) -> bool:
    parsed = parse_measured_needed(detail)
    return bool(parsed and parsed["ratio"] is not None and CLOSE_CALL_RATIO <= parsed["ratio"] < 1)


def utc(value: Any) -> datetime:
    """The ONE timestamp parser for every panel: 'Z', '+00:00', offsets, microseconds or naive (read as UTC) all become aware UTC."""
    return pd.to_datetime(value, utc=True).to_pydatetime()


def et_day_start(now: datetime) -> datetime:
    """The ONE 'today' boundary: midnight Eastern, as UTC."""
    return now.astimezone(EASTERN).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def clock(value: Any, now: datetime | None = None) -> str:
    """Eastern time; with `now`, an earlier day shows its weekday ("Sat 19:18")."""
    try:
        earlier = now is not None and utc(value) < et_day_start(now)
        return eastern_label(str(value), "%a %H:%M" if earlier else "%H:%M")
    except (ValueError, TypeError):
        return "—"


def hour_floor(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


SCORE_STEPS = (("walk_forward", "Holds over time"), ("robustness", "Stress test"), ("monte_carlo", "Luck test"))


def score_text(scores: dict[str, str] | None) -> str:
    """The three recorded scores (not gates) as 'Holds over time: passed, Stress test: failed, Luck test: not enough data'; 'not enough data' only when the recorded reason is too few windows, otherwise a missing score is 'not scored'.
    `scores` maps stage to the Report page's status word (Passed, Close call, Failed, Can't test, Crashed)."""
    marks = []
    for stage, label in SCORE_STEPS:
        status = (scores or {}).get(stage)
        word = "passed" if status == "Passed" else "failed" if status == "Failed" else "close call" if status == "Close call" else "not enough data" if status == "Too few windows" else "not scored"
        marks.append(f"{label}: {word}")
    return ", ".join(marks)


def event_sentence(event: dict[str, Any], name: str, who: str, scores: dict[str, str] | None = None) -> tuple[str, str]:
    """(plain sentence, tone) for one campaign event. Tone: indigo info, amber close call, red crash, green pass, grey failed a test."""
    state, code, detail = event["state"], event["reason_code"] or "", event["reason_detail"] or ""
    quoted = f"“{name}”"
    step = STEP_NAME.get(code, code.replace("_", " "))
    if state == "queued":
        return (f"{who} queued {quoted}.", "indigo") if code == "waiting" else (f"{quoted} was put back in line after {'a software update' if code == 'requeued_after_fix' else 'a restart'}.", "indigo")
    if state == "running":
        return f"{quoted} started.", "indigo"
    if state == "screened_out":
        measured = parse_measured_needed(detail)
        text = f" ({measured['text']})" if measured else ""
        return (f"{quoted} was a close call on {step}{text}.", "amber") if is_close_call(detail) else (f"{quoted} failed {step}{text}.", "grey")
    if state == "failed" and is_restart(detail):
        return f"{quoted} stopped by a server restart, safe to re-run.", "grey"
    if state == "failed":
        return f"{quoted} crashed: {plain_error(detail).rstrip('.').lower()}.", "red"
    if state == "implementation_blocked":
        return (f"{quoted} could not be tested: its rules are missing." if code == "rules_missing" else f"{quoted} could not be tested."), "amber"
    if state == "duplicate_closed":
        return f"{quoted} was closed as a duplicate of an earlier idea.", "grey"
    if state == "survivor":
        return f"{quoted} passed the gates (costs, unseen data); scores: {score_text(scores)}.", "green"
    return f"{quoted}: {state.replace('_', ' ')}.", "grey"


TERMINAL_STATES = ("screened_out", "survivor", "failed")


def tests_from_events(events: list[dict[str, Any]], titles: dict[str, str], now: datetime, max_age: timedelta = timedelta(days=1)) -> list[dict[str, Any]]:
    """The factory's record of tests: a 'running' event plus that idea's next terminal event. A start followed by a re-queue was cut short and is not a test.
    A start with nothing after it counts as running only while younger than `max_age`. Rows carry the same keys the page reads from run records."""
    open_: dict[str, dict[str, Any]] = {}
    tests: list[dict[str, Any]] = []
    for event in sorted(events, key=lambda e: e["event_id"]):
        cid, state = event["candidate_id"], event["state"]
        if state == "running":
            open_[cid] = event
        elif cid in open_ and state in TERMINAL_STATES:
            start = open_.pop(cid)
            outcome = "passed" if state == "survivor" else "crashed" if state == "failed" else "close" if is_close_call(event["reason_detail"]) else "failed"
            tests.append({"run_id": event["run_id"] or start["run_id"], "candidate_id": cid, "title": titles.get(cid, cid), "status": "failed" if state == "failed" else "succeeded", "cohort": "open",
                          "started_at": start["created_at"], "completed_at": event["created_at"], "outcome": outcome, "error_summary": event["reason_detail"] if state == "failed" else "",
                          "stage": "", "survivor_count": int(state == "survivor")})
        elif cid in open_:
            open_.pop(cid)
    for cid, start in open_.items():
        if now - utc(start["created_at"]) <= max_age:
            tests.append({"run_id": None, "candidate_id": cid, "title": titles.get(cid, cid), "status": "running", "cohort": "open", "started_at": start["created_at"], "completed_at": "",
                          "outcome": "running", "error_summary": "", "stage": "", "survivor_count": 0})
    return tests


def group_requeues(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hundreds of 'put back in line' events at one restart become one line."""
    out: list[dict[str, Any]] = []
    for event in events:
        previous = out[-1] if out else None
        if previous and (event["reason_code"] or "").startswith("requeued") and previous["reason_code"] == event["reason_code"] and previous["state"] == "queued":
            previous["count"] += 1
            continue
        out.append({**event, "count": 1})
    return out


def control_log_rows(control: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Pause/resume presses from the gateway campaign_control table. The wording is always 'from dashboard', never who pressed."""
    return [{"t": clock(row["created_at"], now), "when": utc(row["created_at"]), "tone": "grey",
             "text": "Testing paused from dashboard" if row["paused"] else "Testing resumed from dashboard"} for row in control]


def log_rows(events: list[dict[str, Any]], titles: dict[str, str], submitters: dict[str, str], crashed_today: list[dict[str, Any]], now: datetime | None = None, control: list[dict[str, Any]] | None = None, scores: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = control_log_rows(control or [], now)
    for event in group_requeues(events[:60])[:20]:
        sentence, tone = event_sentence(event, titles.get(event["candidate_id"], event["candidate_id"]), submitter_label(submitters.get(event["candidate_id"])), (scores or {}).get(event["candidate_id"]))
        if event["count"] > 1:
            sentence, tone = f"{event['count']} ideas were put back in line after {'a software update' if event['reason_code'] == 'requeued_after_fix' else 'a restart'}.", "indigo"
        log.append({"t": clock(event["created_at"], now), "when": utc(event["created_at"]), "tone": tone, "text": sentence})
    for run in crashed_today:  # run events: a crashed run is recorded on the run, not always as a campaign event
        restart = is_restart(run["error_summary"])
        text = f"“{run['title']}” stopped by a server restart, safe to re-run." if restart else f"“{run['title']}” crashed: {plain_error(run['error_summary']).rstrip('.').lower()}."
        log.append({"t": clock(run["completed_at"], now), "when": utc(run["completed_at"]), "tone": "grey" if restart else "red", "text": text})
    log = [{k: v for k, v in item.items() if k != "when"} for item in sorted(log, key=lambda r: r["when"], reverse=True)[:20]]
    return log


def is_restart(error: Any) -> bool:
    """A test stopped only because the server restarted: handled by itself, so it is history, not something to look at."""
    return "restart" in plain_error(error).lower()


def crash_label(reason: str) -> str:
    return "server restarts" if "restart" in reason else "running out of memory" if "memory" in reason else reason


def short_reason(error: Any) -> str:
    """First sentence of the plain-words reason, sentence case after a label ("stopped by a server restart")."""
    first = plain_error(error).split(". ")[0].rstrip(".").strip()
    return first[:1].lower() + first[1:]


def timeline_rows(runs: list[dict[str, Any]], now: datetime, typical: float | None = None) -> list[dict[str, Any]]:
    """One row per run in the last 12 h. A crash is recorded when the server restarts, long after the process died, so a finished block never runs longer than 3x the typical test time."""
    timeline: list[dict[str, Any]] = []
    cutoff12 = now - timedelta(hours=12)
    for run in runs:
        if run["outcome"] == "abandoned" or not run["started_at"] or run["status"] == "created":
            continue
        end = now if run["status"] == "running" else utc(run["completed_at"]) if run["completed_at"] else None
        if end is None or end < cutoff12:
            continue
        start = utc(run["started_at"])
        capped = bool(typical and run["status"] != "running" and end - start > timedelta(minutes=3 * typical))
        end = start + timedelta(minutes=3 * typical) if capped else end
        timeline.append({"name": run["title"], "start": start.astimezone(EASTERN).replace(tzinfo=None), "end": end.astimezone(EASTERN).replace(tzinfo=None),
                         "minutes": max(0.0, (end - start).total_seconds() / 60), "outcome": run["outcome"], "candidate_id": run["candidate_id"], "capped": capped})
    return timeline
