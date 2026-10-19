"""Factory oversight: one read-only snapshot of the whole factory (state, tiles, alerts, health) as plain dicts.

The gateway database is read raw and read-only, like overview_projection does (agent_gateway cannot be imported here).
"""

from __future__ import annotations

import json
from collections import Counter
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dashboard.factory_history import (
    OUTCOME_WORDS, OUTCOMES, STEP_NAME, STEPS, clock, crash_label, et_day_start, tests_from_events, hour_floor, is_close_call, is_restart, log_rows, unclosed_starts, short_reason, submitter_label, timeline_rows, utc,
)
from dashboard.idea_report_projection import score_statuses
from dashboard.results_projection import oos_report_metrics
from dashboard.factory_projection import _duration_minutes, _params, _row, _runs_source, plain_error
from dashboard.overview_projection import GATEWAY_DATABASE_ENVIRONMENT_VARIABLE, _open_read_only, _validated_connection, configured_database_path
from dashboard.time_display import EASTERN, eastern_label


DRAIN_MARKER = Path(os.environ.get("QF_DEPLOY_DRAIN_MARKER", "/run/quant-factory/deploy-drain"))


DRAIN_STALE_SECONDS = 2 * 3600  # same rule as the campaign: an older marker is ignored (agent_gateway cannot be imported here)


SLOW_FACTOR = 2.0


ABANDONED_AFTER = timedelta(days=1)


CRASH_FIXES = (("memory", "Fix: split the grid into smaller parts, or re-queue it after the memory is raised."), ("restart", "Nothing to do: it was stopped by a restart and is safe to run again."))


_EMPTY = {"paused": None, "pause_bands": [], "last_test": None, "tiles": [], "running": [], "alerts": [], "old_runs": None, "queue": {"total": 0, "next": [], "next_start": None}, "timeline": [], "hourly": [], "health": [], "log": []}


def median_minutes(pairs: list[tuple[Any, Any]], last: int = 50) -> float | None:
    """Median run time in minutes of the last `last` finished runs (pairs are (started_at, completed_at), newest first)."""
    values = sorted(value for value in (_duration_minutes(a, b) for a, b in pairs[:last]) if value is not None)
    return None if not values else (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2


def drain_state(marker: Path | None = None, now: float | None = None) -> bool:
    """True while a deploy is waiting for the running test: the marker file exists and is under two hours old."""
    try:
        age = (time.time() if now is None else now) - (marker or DRAIN_MARKER).stat().st_mtime
    except OSError:
        return False
    return age <= DRAIN_STALE_SECONDS


def header_pill(*, running: int, draining: bool, last_finished_crashed: bool, paused: bool = False) -> dict[str, str]:
    """The one status pill. Order: paused from dashboard, crash (until the next test finishes), paused for update, running, idle."""
    label, tone = (("Paused", "amber") if paused else ("Last test crashed", "red") if last_finished_crashed and not running else ("Paused for update", "amber") if draining else ("Running", "green") if running else ("Idle", "grey"))
    return {"label": label, "tone": tone}


def run_outcome(run: dict[str, Any], close_runs: set[str]) -> str:
    if run["status"] in ("running", "failed"):
        return "running" if run["status"] == "running" else "crashed"
    return "passed" if run["survivor_count"] > 0 else "close" if run["run_id"] in close_runs else "failed"


def group_abandoned(starts: list[dict[str, Any]], titles: dict[str, str], now: datetime, typical: float | None = None) -> dict[str, Any] | None:
    """Every start with no later event at all (factory_history.unclosed_starts), older than 3x the typical test time (a day when there is none), becomes ONE alert, never one per run.
    A start followed by a re-queue or a fresh start already says how it ended (interrupted), so it never reaches here."""
    limit = timedelta(minutes=3 * typical) if typical else ABANDONED_AFTER
    old = sorted((s for s in starts if s["created_at"] and now - utc(s["created_at"]) > limit), key=lambda s: utc(s["created_at"]))
    if not old:
        return None
    oldest = eastern_label(old[0]["created_at"], "%b %-d")
    return {"count": len(old), "oldest": oldest, "title": f"{len(old)} old runs were never closed (oldest {oldest})",
            "items": [{"name": titles.get(s["candidate_id"], s["candidate_id"]), "when": eastern_label(s["created_at"], "%b %-d, %-I:%M %p ET"), "candidate_id": s["candidate_id"]} for s in old]}


def _human_minutes(minutes: float | None) -> str:
    seconds = int(round((minutes or 0) * 60))
    return "—" if minutes is None else f"{seconds // 3600}h {seconds % 3600 // 60}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60:02d}s"


def _ago(minutes: float) -> str:
    return "under a minute ago" if minutes < 1 else f"{minutes:.0f} min ago" if minutes < 90 else f"{minutes / 60:.0f} h ago" if minutes < 2880 else f"{minutes / 1440:.0f} days ago"


def crash_fix(error: str) -> str:
    lowered = error.lower()
    return next((text for marker, text in CRASH_FIXES if marker in lowered), "Fix: open the report to see what stopped it; it can be run again.")


def price_data_rows(manifest_dirs: list[Path]) -> list[dict[str, str]]:
    """Latest bar date per market from the nightly top-up manifests (read-only)."""
    latest: dict[str, str] = {}
    for folder in manifest_dirs:
        for path in sorted(Path(folder).glob("*.json")) if Path(folder).is_dir() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                symbol, stamp = str(data["symbol"]), str(data["latest_timestamp"])
            except (OSError, ValueError, KeyError):
                continue
            if stamp > latest.get(symbol, ""):
                latest[symbol] = stamp
    return [{"market": symbol, "last": eastern_label(stamp, "%a %-d %b")} for symbol, stamp in sorted(latest.items())]


def _price_health() -> dict[str, Any]:
    try:
        from dashboard.data_freshness import load_stale_price_banner
        from market_data.catalog import DEFAULT_CONFIG_PATH, load_data_locations
        banner = load_stale_price_banner()
        rows = price_data_rows([load_data_locations(DEFAULT_CONFIG_PATH).downloaded_manifest_dir])
    except (OSError, ValueError, ImportError) as exc:  # an unreadable data folder shows as unknown, never as fine
        return {"banner": None, "rows": [], "error": str(exc)}
    return {"banner": banner, "rows": rows, "error": None}


_PACE_CACHE: dict[str, tuple[float, int]] = {}


def _bytes_written_last_day(root: Path) -> int:
    """Bytes of files changed in the last 24 h under the runtime folder (cached 5 min)."""
    stamp, total = _PACE_CACHE.get(str(root), (0.0, 0))
    if time.time() - stamp < 300:
        return total
    cutoff, total = time.time() - 86400, 0
    for folder, _dirs, files in os.walk(root):
        for name in files:
            try:
                stat = os.stat(os.path.join(folder, name))
                total += stat.st_size if stat.st_mtime >= cutoff else 0
            except OSError:
                continue
    _PACE_CACHE[str(root)] = (time.time(), total)
    return total


def disk_health(root: Path) -> dict[str, Any]:
    try:
        free = shutil.disk_usage(root).free
    except OSError as exc:
        return {"tone": "amber", "value": f"unavailable ({exc.strerror or exc})"}
    pace = _bytes_written_last_day(root)
    gb = free / 1e9
    days = free / pace if pace > 0 else None
    tone = "green" if (days is None and gb > 10) or (days is not None and days > 14) else "red" if gb < 2 or (days is not None and days < 3) else "amber"
    runway = "" if days is None else " · more than a year at today’s pace (estimate)" if days > 365 else f" · about {days / 7:.0f} weeks at today’s pace (estimate)" if days >= 14 else f" · about {days:.0f} days at today’s pace (estimate)"
    return {"tone": tone, "value": f"{gb:.0f} GB free{runway}"}


def memory_health(meminfo: Path = Path("/proc/meminfo")) -> dict[str, Any]:
    free_pct = None
    try:
        values = {line.split(":")[0]: int(line.split()[1]) for line in meminfo.read_text().splitlines() if ":" in line}
        free_pct = 100 * values["MemAvailable"] / values["MemTotal"]
    except (OSError, KeyError, ValueError, IndexError):
        pass
    value = "could not be read here" if free_pct is None else f"{free_pct:.0f}% free"
    tone = "amber" if free_pct is None else "red" if free_pct < 5 else "amber" if free_pct < 15 else "green"
    return {"tone": tone, "value": value}


def not_after(rows: list[dict[str, Any]], key: str, now: datetime) -> list[dict[str, Any]]:
    """Rows whose `key` time is not after the page's as-of time (a missing time is kept)."""
    return [r for r in rows if not r.get(key) or utc(r[key]) <= now]


def latest_not_after(values: list[Any], now: datetime) -> Any:
    """The newest time that is not after the as-of time, or None."""
    return max((v for v in values if v and utc(v) <= now), key=utc, default=None)


def headline_for(*, running: int, waiting: int, looks: int, warnings: int, paused_since: str | None = None) -> tuple[str, str]:
    """(text, tone). 'All clear' only when nothing needs a look AND every health check is green. Paused from dashboard wins over everything."""
    if paused_since:
        extra = ([f"{looks} thing{'s' if looks != 1 else ''} need{'s' if looks == 1 else ''} a look"] if looks else []) + ([f"{warnings} health warning{'s' if warnings != 1 else ''}"] if warnings else [])
        return " ".join([f"Paused from dashboard since {paused_since}. {waiting} waiting."] + [f"{part}." for part in extra]), "amber"
    if not (looks or warnings or running or waiting):
        return "All clear", "green"
    state = f"{running} test{'s' if running != 1 else ''} running, {waiting} waiting" if running or waiting else "Idle"
    parts = [state]
    if looks:
        parts.append(f"{looks} thing{'s' if looks != 1 else ''} need{'s' if looks == 1 else ''} a look")
    if warnings:
        parts.append(f"{warnings} health warning{'s' if warnings != 1 else ''}")
    if not (looks or warnings):
        parts.append("All clear")
    return ". ".join(parts) + ".", "amber" if looks or warnings else "text"


def read_campaign_control(gate: sqlite3.Connection, now: datetime, tables: set[str]) -> list[dict[str, Any]]:
    """Pause/resume presses up to the as-of time, newest first. A gateway DB without the table (older) means never paused."""
    if "campaign_control" not in tables:
        return []
    return [dict(r) for r in gate.execute("SELECT event_id,paused,actor,reason,created_at FROM campaign_control WHERE julianday(created_at)<=julianday(?) ORDER BY event_id DESC LIMIT 20", [now.isoformat()])]


def pause_bands(control: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """Pause spans (Eastern wall time) from press to resume, or to now while still paused, clipped to the last 12 hours."""
    floor, bands, start = now - timedelta(hours=12), [], None
    for row in sorted(control, key=lambda r: r["event_id"]):
        if row["paused"] and start is None:
            start = utc(row["created_at"])
        elif not row["paused"] and start is not None:
            bands.append((start, utc(row["created_at"])))
            start = None
    if start is not None:
        bands.append((start, now))
    return [{"start": max(a, floor).astimezone(EASTERN).replace(tzinfo=None), "end": b.astimezone(EASTERN).replace(tzinfo=None)} for a, b in bands if b > floor]


def _gateway(path: str | None):
    raw = (path if path is not None else os.environ.get(GATEWAY_DATABASE_ENVIRONMENT_VARIABLE, "")).strip()
    return _open_read_only(Path(raw)) if raw and Path(raw).is_file() else None


def _unavailable(base: dict[str, Any], message: str | None, draining: bool) -> dict[str, Any]:
    return {**base, **_EMPTY, "message": message, "pill": header_pill(running=0, draining=draining, last_finished_crashed=False), "headline": "Factory data is unavailable"}


def crash_alerts(crashed: list[dict[str, Any]], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unhandled crashes, one alert per idea and reason (with ×N). A crash is handled once its idea has a later event that is not itself a crash."""
    groups: dict[tuple[str | None, str], dict[str, Any]] = {}
    for run in sorted(crashed, key=lambda r: r["completed_at"], reverse=True):
        cid, done = run["candidate_id"], utc(run["completed_at"])
        if is_restart(run["error_summary"]):
            continue  # a restart stop is handled by itself: it shows in What happened only
        if any(e["candidate_id"] == cid and e["state"] != "failed" and utc(e["created_at"]) > done for e in events):
            continue
        reason = plain_error(run["error_summary"])
        key = (cid, short_reason(reason))
        if key in groups:
            groups[key]["count"] += 1
            continue
        groups[key] = {"tone": "red", "title": f"Crashed: {short_reason(reason)}", "when": clock(run["completed_at"]), "sort": done.isoformat(), "count": 1,
                       "body": f"“{run['title']}” stopped on “{STEP_NAME[run['stage']]}”." if run.get("stage") in STEP_NAME else f"“{run['title']}” crashed.", "next": crash_fix(reason), "candidate_id": cid}
    for alert in groups.values():
        alert["title"] += f" ×{alert['count']}" if alert["count"] > 1 else ""
    return list(groups.values())[:3]


def load_factory_overview(*, database: str | Path | None = None, gateway: str | None = None, now: datetime | None = None,
                          drain_marker: Path | None = None, runtime_dir: Path | None = None) -> dict[str, Any]:
    """Everything the /factory page shows, in plain dicts. Missing sources give empty sections, never invented numbers."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local = now.astimezone(EASTERN)
    database_path = Path(database) if database is not None else configured_database_path()
    draining = drain_state(drain_marker)
    base: dict[str, Any] = {"available": False, "now_et": local.replace(tzinfo=None), "now_label": f"{local:%A} {local.day} {local:%B} · updated {local:%H:%M:%S} ET", "checked": f"{local:%H:%M} ET"}
    connection, error = _validated_connection(database_path)
    if connection is None:
        return _unavailable(base, error, draining)
    gate = None
    try:
        gate = _gateway(gateway)
        since48 = (now - timedelta(hours=48)).isoformat()
        runs = [_row(r) for r in connection.execute(
            _runs_source() + " SELECT * FROM run_records WHERE hidden=0 AND (status IN ('running','created') OR COALESCE(completed_at,started_at,created_at)>=?) ORDER BY COALESCE(started_at,created_at)", _params() + [since48])]
        titles = {str(r[0]): str(r[1]) for r in connection.execute("SELECT draft_id, COALESCE(NULLIF(json_extract(candidate_json,'$.candidate.title'),''), title) FROM idea_drafts")}
        events: list[dict[str, Any]] = []
        queued_events: list[dict[str, Any]] = []
        submitters: dict[str, str] = {}
        grok_last = last_event = None
        control: list[dict[str, Any]] = []
        if gate is not None:
            tables = {str(r[0]) for r in gate.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            control = read_campaign_control(gate, now, tables)
            if "campaign_events" in tables:
                events = [dict(r) for r in gate.execute("SELECT event_id,candidate_id,state,reason_code,reason_detail,run_id,created_at FROM campaign_events WHERE julianday(created_at)<=julianday(?) AND julianday(created_at)>=julianday(?)-7 ORDER BY event_id DESC", [now.isoformat(), now.isoformat()])]
                last_event = (gate.execute("SELECT created_at FROM campaign_events WHERE julianday(created_at)<=julianday(?) ORDER BY event_id DESC LIMIT 1", [now.isoformat()]).fetchone() or [None])[0]
                queued_events = [dict(r) for r in gate.execute(
                    "SELECT e.candidate_id,e.created_at FROM campaign_events e WHERE e.event_id=(SELECT MAX(event_id) FROM campaign_events WHERE candidate_id=e.candidate_id AND julianday(created_at)<=julianday(?)) AND e.state='queued' ORDER BY e.event_id", [now.isoformat()])]
            if "candidate_identities" in tables:
                submitters = {str(r[0]): str(r[1]) for r in gate.execute("SELECT candidate_id,created_by FROM candidate_identities")}
            if "gateway_audit" in tables:
                grok_last = (gate.execute("SELECT MAX(occurred_at) FROM gateway_audit WHERE agent_id='grok-remote' AND julianday(occurred_at)<=julianday(?)", [now.isoformat()]).fetchone() or [None])[0]
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return _unavailable(base, f"Factory state is unavailable: {exc}", draining)
    finally:
        connection.close()
        if gate is not None:
            gate.close()
    events = not_after(events, "created_at", now)  # nothing from after the as-of time, whatever the source
    runs = not_after(not_after(runs, "started_at", now), "completed_at", now)
    close_runs = {e["run_id"] for e in events if e["state"] == "screened_out" and e["run_id"] and is_close_call(e["reason_detail"])}
    for run in runs:
        run["outcome"] = "abandoned" if run["status"] == "running" and run["cohort"] == "failed" else run_outcome(run, close_runs)
    # campaign_events are the only record of tests; the research DB adds only the current step and the old never-closed runs
    tests = tests_from_events(events, titles, now)
    stages = {r["candidate_id"]: r["stage"] for r in runs if r["status"] == "running" and r["cohort"] == "open"}
    for test in tests:
        test["stage"] = stages.get(test["candidate_id"], "")
    live = [t for t in tests if t["status"] == "running"]
    finished = [t for t in tests if t["completed_at"] and t["outcome"] != "interrupted"]  # an interrupted start was re-queued: drawn on the timeline, never counted
    typical = median_minutes([(t["started_at"], t["completed_at"]) for t in sorted(finished, key=lambda t: utc(t["completed_at"]), reverse=True)])
    day_start = et_day_start(now)
    today = [r for r in finished if utc(r["completed_at"]) >= day_start]
    crashed_today = [r for r in today if r["outcome"] == "crashed"]
    passed_today = sum(r["outcome"] == "passed" for r in today)
    unchecked_today = sum(r["outcome"] == "unchecked" for r in today)  # our own settings mismatch: not the idea's failure
    latest_finished = max(finished, key=lambda r: utc(r["completed_at"]), default=None)
    paused = bool(control and control[0]["paused"])
    paused_since = clock(control[0]["created_at"], now) if paused else None
    pill = header_pill(running=len(live), draining=draining, last_finished_crashed=bool(latest_finished and latest_finished["outcome"] == "crashed"), paused=paused)
    queue_rows = [{"n": position, "name": titles.get(item["candidate_id"], item["candidate_id"]), "who": submitter_label(submitters.get(item["candidate_id"])),
                   "when": clock(item["created_at"], now), "candidate_id": item["candidate_id"]} for position, item in enumerate(queued_events, 1)]
    longest = max((((now - utc(i["created_at"])).total_seconds() / 60) for i in queued_events), default=None)
    # Hourly series, Eastern wall time, oldest first.
    top = hour_floor(now)
    hours = [top - timedelta(hours=k) for k in range(47, -1, -1)]
    hourly = [{"hour": h.astimezone(EASTERN).replace(tzinfo=None), **{o: 0 for o in OUTCOMES}} for h in hours]
    index = {h: i for i, h in enumerate(hours)}
    for run in finished:
        slot = index.get(hour_floor(utc(run["completed_at"])))
        if slot is not None:
            hourly[slot][run["outcome"]] += 1
    last24, hours24 = hourly[-24:], hours[-24:]
    queued_per_hour = [0] * 24
    for e in events:
        if e["state"] == "queued" and e["reason_code"] == "waiting":
            k = int((now - utc(e["created_at"])).total_seconds() // 3600)
            if 0 <= k < 24:
                queued_per_hour[23 - k] += 1
    typical_per_hour = [median_minutes([(r["started_at"], r["completed_at"]) for r in finished if hour_floor(utc(r["completed_at"])) == h]) or 0 for h in hours24]
    reasons = Counter(short_reason(r["error_summary"]) for r in crashed_today)
    top, top_n = reasons.most_common(1)[0] if reasons else ("none", 0)
    crash_reason = "none" if not reasons else f"mostly {crash_label(top)} ({top_n})" if top_n > 1 else crash_label(top)
    crash_reason = crash_reason if len(crash_reason) <= 44 else "see What happened"
    last_test = {"name": latest_finished["title"], "outcome": OUTCOME_WORDS[latest_finished["outcome"]].lower(), "when": clock(latest_finished["completed_at"], now), "candidate_id": latest_finished["candidate_id"]} if latest_finished else None
    tiles = [
        {"label": "Running now", "value": "Paused", "sub": f"since {paused_since}", "color": "amber"} if paused else
        {"label": "Running now", "value": f"{len(live)}" if live else "Idle", "sub": "one test at a time", "color": "indigo" if live else "idle"},
        {"label": "Waiting", "value": f"{len(queue_rows)}", "sub": f"longest wait {_human_minutes(longest)}" if longest is not None else "nothing in line", "color": "text", "spark": queued_per_hour},
        {"label": "Runs today", "value": f"{len(today)}", "sub": f"{passed_today} passed · {sum(r['outcome'] in ('failed', 'close') for r in today)} failed · {len(crashed_today)} crashed" + (f" · {unchecked_today} couldn't be checked" if unchecked_today else ""), "color": "text",
         "spark": [sum(row[o] for o in ("failed", "close", "passed", "crashed")) for row in last24]},
        {"label": "Runs crashed today", "value": f"{len(crashed_today)}", "sub": crash_reason, "color": "red" if crashed_today else "text", "spark": [row["crashed"] for row in last24]},
        {"label": "Typical test time", "value": _human_minutes(typical), "sub": "median of the last 50", "color": "text", "spark": typical_per_hour},
    ]
    running_cards, alerts = [], []
    stage_keys = [key for key, _n in STEPS]
    for run in live:
        elapsed = (now - utc(run["started_at"])).total_seconds() / 60 if run["started_at"] else 0.0
        slow = bool(typical and elapsed > SLOW_FACTOR * typical)
        current = stage_keys.index(run["stage"]) if run["stage"] in stage_keys else 0
        step = STEP_NAME.get(run["stage"], "starting")
        running_cards.append({"name": run["title"], "elapsed": _human_minutes(elapsed), "slow": slow, "candidate_id": run["candidate_id"],
                              "steps": ["done" if i < current else ("slow" if slow else "current") if i == current else "todo" for i in range(5)],
                              "where": f"Step {current + 1} of 5 · {step}", "note": "finishing; nothing new will start" if paused else f"typical {typical:.0f} min" if typical else "typical time not yet known"})
        if slow:
            alerts.append({"tone": "amber", "title": f"Slow: one test is taking {elapsed / typical:.1f}× longer than usual", "when": clock(now.isoformat()), "sort": now.isoformat(),
                           "body": f"“{run['title']}” has been on “{step}” for {_human_minutes(elapsed)}.", "next": "Nothing to do yet.", "candidate_id": run["candidate_id"]})
    alerts += crash_alerts(crashed_today, events)
    price = _price_health()
    if price["banner"]:
        alerts.append({"tone": "amber", "title": "Price data is out of date", "when": clock(now.isoformat()), "sort": now.isoformat(), "body": price["banner"],
                       "next": "Fix: the nightly price update needs to run.", "candidate_id": None})
    alerts.sort(key=lambda a: a["sort"], reverse=True)
    old_runs = group_abandoned(unclosed_starts(events), titles, now, typical)
    health: list[dict[str, Any]] = []
    if price["rows"]:
        health.append({"label": "Price data up to date", "tone": "amber" if price["banner"] else "green", "value": " · ".join(f"{r['market']} to {r['last']}" for r in price["rows"][:6])})
    else:
        health.append({"label": "Price data up to date", "tone": "amber", "value": "could not be read here" if price["error"] else "no price sets found"})
    if last_event:
        minutes = (now - utc(last_event)).total_seconds() / 60
        idle = not live and not queue_rows
        health.append({"label": "Factory responding", "tone": "green" if idle or minutes <= 30 else "amber" if minutes <= 120 else "red",
                       "value": f"last event {_ago(minutes)}" + (" (idle)" if idle and minutes > 30 else "")})
    else:
        health.append({"label": "Factory responding", "tone": "amber", "value": "no events recorded"})
    health.append({"label": "Disk space", **disk_health(runtime_dir or database_path.parent)})
    health.append({"label": "Memory", **memory_health()})
    if grok_last:
        minutes = (now - utc(grok_last)).total_seconds() / 60
        health.append({"label": "Grok connected", "tone": "green" if minutes <= 1440 else "amber", "value": "last request " + eastern_label(grok_last, "%a %-d %b, %H:%M") + " ET"})
    else:
        health.append({"label": "Grok connected", "tone": "amber", "value": "no requests recorded"})
    survivors = {e["candidate_id"] for e in events[:60] if e["state"] == "survivor"}
    log = log_rows(events, titles, submitters, [], now, control, {cid: score_statuses(cid, database_path) for cid in survivors},
                   {e["candidate_id"]: oos_report_metrics(database=database_path, run_id=e["run_id"]) for e in events[:60] if e["state"] == "screened_out" and "test did not pass" in str(e["reason_detail"] or "")})
    timeline = timeline_rows(tests, now, typical)
    looks = len(alerts) + (1 if old_runs else 0)
    warnings = sum(item["tone"] != "green" for item in health)
    headline, headline_tone = headline_for(running=len(live), waiting=len(queue_rows), looks=looks, warnings=warnings, paused_since=paused_since)
    return {**base, "available": True, "message": "", "pill": pill, "paused": {"since": paused_since} if paused else None, "pause_bands": pause_bands(control, now), "headline": headline, "headline_tone": headline_tone, "typical_minutes": typical, "tiles": tiles, "running": running_cards, "last_test": last_test, "alerts": alerts, "old_runs": old_runs,
            "queue": {"total": len(queue_rows), "next": queue_rows[:4], "next_start": f"~{typical:.0f} min (estimate)" if queue_rows and typical else None},
            "timeline": timeline, "hourly": hourly, "health": health, "log": log}


__all__ = ["load_factory_overview", "load_factory_page", "load_factory_summary"]


__all__ = ["OUTCOME_WORDS", "load_factory_overview"]
