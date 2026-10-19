"""Read-only, server-paged projection for the Factory runs workspace."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
import shutil
import time
from pathlib import Path
import sqlite3
from typing import Any

from dashboard.time_display import EASTERN, eastern_label
from dashboard.overview_projection import (
    GATEWAY_DATABASE_ENVIRONMENT_VARIABLE,
    SURVIVOR_EVENT_MESSAGE,
    _open_read_only,
    SURVIVOR_EVENT_SOURCE,
    _scalar,
    _validated_connection,
    configured_database_path,
)


RUN_PAGE_LIMIT = 100
# Test fixtures that leaked into the research database; hidden from default views, never deleted.
TEST_TITLE_MARKERS = ("connection test",)
STOPPED_NOTE = "Stopped. This run was left over from a server restart and is not running now. Safe to run again."
# (text found in the stored error, plain wording shown to the trader), first match wins.
PLAIN_ERRORS = (
    ("crashed", "Stopped by the operator after a server restart. Safe to run again."),
    ("restart", "Stopped by a server restart. Safe to run again."),
    ("timed out", "Took too long and was stopped."),
    ("timeout", "Took too long and was stopped."),
    ("cancel", "Cancelled before it finished."),
    ("out of memory", "Ran out of computer memory and was stopped."),
)


def plain_error(text: Any) -> str:
    """Developer wording from the run record in plain words; unknown errors keep their text minus tool names."""
    raw = str(text or "").strip()
    lowered = raw.lower()
    for marker, plain in PLAIN_ERRORS:
        if marker in lowered:
            return plain
    return raw.replace("Prefect", "The scheduler")


def results_note(status: str, variations: int, stage: str) -> str:
    """Say what a run was when it has no results."""
    if variations:
        return f"{variations:,} results"
    if status == "running":
        return "Running now. No results yet"
    if status == "created":
        return "Waiting to start. No results yet"
    if status == "failed":
        return "Stopped before any results"
    return "Finished with no settings to test"


def _runs_source() -> str:
    """Run rows plus a hidden flag: test fixtures and finished runs that tested nothing."""
    junk = " OR ".join(f"LOWER(s.title) LIKE '%{marker}%'" for marker in TEST_TITLE_MARKERS)
    return (f"WITH run_records AS (SELECT s.*, CASE WHEN {junk} OR (s.status='succeeded' AND s.variation_count=0) "
            f"THEN 1 ELSE 0 END AS hidden FROM ({RUN_SOURCE}) s)")
SORT_FIELDS = {
    "title": "title", "run_id": "run_id", "symbol": "symbol", "stage": "stage",
    "status": "status", "variation_count": "variation_count", "survivor_count": "survivor_count",
    "completed_at": "completed_at",
}


RUN_SOURCE = """
SELECT r.run_id, r.configuration_id, r.stage, r.status, r.started_at, r.completed_at,
       r.created_at, r.error_summary, c.experiment_id, c.strategy_id,
       d.draft_id AS candidate_id,
       COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'),
                json_extract(c.canonical_config_json, '$.market_data.dataset_id'), 'Unrecorded') AS symbol,
       COALESCE(json_extract(d.candidate_json, '$.candidate.title'), d.title,
                c.experiment_id, c.strategy_id, r.run_id) AS title,
       (SELECT COUNT(*) FROM parameter_results p WHERE p.run_id=r.run_id) AS variation_count,
       (SELECT COUNT(*) FROM parameter_results p WHERE p.run_id=r.run_id AND p.screening_status='screened_out') AS screened_out_count,
       CASE WHEN EXISTS (
           SELECT 1 FROM run_operator_events e WHERE e.run_id=r.run_id AND e.source=? AND e.message=?
       ) THEN 1 ELSE 0 END AS survivor_count,
       CASE WHEN r.status='running' AND d.draft_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM qf_campaign_admissions q WHERE q.candidate_id=d.draft_id AND q.state='running')
            THEN 'failed'
            WHEN r.status IN ('created','running') THEN 'open'
            WHEN r.status='failed' THEN 'failed' ELSE 'completed' END AS cohort
FROM experiment_runs r
JOIN experiment_configurations c ON c.configuration_id=r.configuration_id
LEFT JOIN idea_drafts d ON d.configuration_id=r.configuration_id AND d.candidate_json<>''
"""


def _params() -> list[Any]:
    return [SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE]


def _duration_minutes(start: Any, end: Any) -> float | None:
    if not start or not end:
        return None
    try:
        began = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        finished = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return max(0.0, (finished - began).total_seconds() / 60)
    except ValueError:
        return None


def _display_timestamp(value: Any) -> str:
    if not value:
        return "—"
    try:
        return eastern_label(str(value))
    except ValueError:
        return str(value)


def _row(row: sqlite3.Row) -> dict[str, Any]:
    duration = _duration_minutes(row["started_at"], row["completed_at"])
    screened_out_count = int(row["screened_out_count"] or 0)
    variation_count = int(row["variation_count"] or 0)
    stale = row["status"] == "running" and row["cohort"] == "failed"
    return {
        "run_id": str(row["run_id"]), "configuration_id": str(row["configuration_id"]),
        "candidate_id": str(row["candidate_id"]) if row["candidate_id"] else None,
        "title": str(row["title"]) if row["candidate_id"] else str(row["title"]).replace("_", " ").title(), "symbol": str(row["symbol"]), "stage": str(row["stage"]),
        "status": str(row["status"]), "cohort": str(row["cohort"]),
        "display_outcome": "screened_out" if variation_count and screened_out_count == variation_count else str(row["status"]),
        "variation_count": variation_count, "survivor_count": int(row["survivor_count"] or 0),
        "screened_out_count": screened_out_count,
        "started_at": str(row["started_at"] or ""), "completed_at": str(row["completed_at"] or ""),
        "completed_display": _display_timestamp(row["completed_at"]),
        "created_at": str(row["created_at"] or ""), "error_summary": STOPPED_NOTE if stale else plain_error(row["error_summary"]),
        "results_note": results_note(str(row["status"]), variation_count, str(row["stage"])),
        "hidden": bool(row["hidden"]),
        "duration_minutes": duration, "resource_state": "Unavailable", "worker": "Unavailable",
    }


def load_factory_summary(*, database: str | Path | None = None) -> dict[str, Any]:
    database_path = Path(database) if database is not None else configured_database_path()
    connection, error = _validated_connection(database_path)
    if connection is None:
        return {"available": False, "message": error, "counts": {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}, "throughput_24h": 0, "median_minutes": None}
    try:
        source = _runs_source()
        rows = connection.execute(source + " SELECT cohort,status,COUNT(*) count FROM run_records WHERE hidden=0 GROUP BY cohort,status", _params()).fetchall()
        counts = {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}
        for row in rows:
            counts[str(row["cohort"])] += int(row["count"])
            if row["status"] == "created": counts["queued"] += int(row["count"])
            # Same rule as the Dashboard: a restart leftover is in the failed cohort, never "running".
            if row["status"] == "running" and row["cohort"] == "open": counts["running"] += int(row["count"])
        boundary = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 86400, timezone.utc).isoformat()
        throughput = _scalar(connection, "SELECT COUNT(*) FROM parameter_results p JOIN experiment_runs r ON r.run_id=p.run_id WHERE COALESCE(r.completed_at,r.created_at)>=?", [boundary])
        durations = [_duration_minutes(row[0], row[1]) for row in connection.execute("SELECT started_at,completed_at FROM experiment_runs WHERE completed_at IS NOT NULL")]
        measured = sorted(value for value in durations if value is not None)
        median = measured[len(measured)//2] if measured else None
        markets = [str(row[0]) for row in connection.execute(source + " SELECT DISTINCT symbol FROM run_records WHERE hidden=0 ORDER BY symbol", _params())]
        stages = [str(row[0]) for row in connection.execute(source + " SELECT DISTINCT stage FROM run_records ORDER BY stage", _params())]
        return {"available": True, "message": "Read-only Factory state loaded.", "counts": counts, "throughput_24h": throughput, "median_minutes": median, "markets": markets, "stages": stages}
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return {"available": False, "message": f"Factory state is unavailable: {exc}", "counts": {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}, "throughput_24h": 0, "median_minutes": None, "markets": [], "stages": []}
    finally:
        connection.close()


def load_factory_page(
    *, cohort: str = "completed", search: str = "", market: str = "all", stage: str = "all",
    resource: str = "all", show_hidden: bool = False, start: int = 0, end: int = 50,
    sort_model: list[dict[str, Any]] | None = None, filter_model: dict[str, dict[str, Any]] | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None: return {"rowData": [], "rowCount": 0}
    try:
        conditions, params = ["cohort=?"], [cohort]
        if not show_hidden: conditions.append("hidden=0")
        if market != "all": conditions.append("symbol=?"); params.append(market)
        if stage != "all": conditions.append("stage=?"); params.append(stage)
        if resource == "unavailable": conditions.append("1=1")
        if search.strip():
            token = f"%{search.strip().lower()}%"; conditions.append("(LOWER(title) LIKE ? OR LOWER(run_id) LIKE ? OR LOWER(experiment_id) LIKE ?)"); params.extend([token, token, token])
        for field, model in (filter_model or {}).items():
            column = SORT_FIELDS.get(field); value = str(model.get("filter") or "").strip()
            if column and value: conditions.append(f"LOWER(CAST({column} AS TEXT)) LIKE ?"); params.append(f"%{value.lower()}%")
        order = "COALESCE(completed_at,created_at) DESC, run_id DESC"
        if sort_model:
            requested = sort_model[0]; column = SORT_FIELDS.get(str(requested.get("colId")))
            if column: order = f"{column} {'DESC' if requested.get('sort') == 'desc' else 'ASC'}, run_id"
        source = _runs_source(); where = " AND ".join(conditions); base = _params() + params
        total = _scalar(connection, source + f" SELECT COUNT(*) FROM run_records WHERE {where}", base)
        limit = min(RUN_PAGE_LIMIT, max(1, int(end)-int(start)))
        rows = connection.execute(source + f" SELECT * FROM run_records WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", base + [limit, max(0,int(start))]).fetchall()
        return {"rowData": [_row(row) for row in rows], "rowCount": total}
    except (sqlite3.Error, ValueError, TypeError):
        return {"rowData": [], "rowCount": 0}
    finally:
        connection.close()




# Factory oversight page (/factory): one read-only snapshot as plain dicts; the gateway DB is read raw read-only (agent_gateway cannot be imported).
DRAIN_MARKER = Path(os.environ.get("QF_DEPLOY_DRAIN_MARKER", "/run/quant-factory/deploy-drain"))
DRAIN_STALE_SECONDS = 2 * 3600  # same rule as the campaign: an older marker is ignored (agent_gateway cannot be imported here)
SLOW_FACTOR = 2.0
ABANDONED_AFTER = timedelta(days=1)
STEPS = (("screening", "Survives costs"), ("oos", "Unseen data"), ("walk_forward", "Holds over time"), ("robustness", "Stress test"), ("monte_carlo", "Luck test"))
STEP_NAME = dict(STEPS)
SUBMITTERS = {"grok-remote": "Grok", "codex-local": "Codex"}
CLOSE_CALL_RATIO = 0.8  # measured at least 80% of the needed number counts as a close call
OUTCOMES = ("failed", "close", "passed", "crashed", "running")
OUTCOME_WORDS = {"failed": "Failed a test", "close": "Close call", "passed": "Passed", "crashed": "Crashed", "running": "Running"}
METRIC_WORDS = {"sharpe_ratio": "Sharpe", "sharpe": "Sharpe", "total_return": "Return", "max_drawdown": "Worst drop", "trade_count": "Trades", "trades": "Trades"}
CRASH_FIXES = (("memory", "Fix: split the grid into smaller parts, or re-queue it after the memory is raised."), ("restart", "Nothing to do: it was stopped by a restart and is safe to run again."))
_MEASURE = re.compile(r"(?P<metric>[A-Za-z_]+) failed: expected (?P<op>>=|<=|>|<)\s*(?P<needed>-?[\d.]+).*?observed (?P<observed>-?[\d.]+)", re.S)
_EMPTY = {"tiles": [], "running": [], "alerts": [], "old_runs": None, "queue": {"total": 0, "next": [], "next_start": None}, "timeline": [], "hourly": [], "health": [], "log": []}


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


def header_pill(*, running: int, draining: bool, last_finished_crashed: bool) -> dict[str, str]:
    """The one status pill. Order: crash (until the next test finishes), paused for update, running, idle."""
    label, tone = (("Last test crashed", "red") if last_finished_crashed and not running else ("Paused for update", "amber") if draining else ("Running", "green") if running else ("Idle", "grey"))
    return {"label": label, "tone": tone}


def run_outcome(run: dict[str, Any], close_runs: set[str]) -> str:
    if run["status"] in ("running", "failed"):
        return "running" if run["status"] == "running" else "crashed"
    return "passed" if run["survivor_count"] > 0 else "close" if run["run_id"] in close_runs else "failed"


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def group_abandoned(runs: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    """Every 'running' record older than a day that the factory no longer owns becomes ONE alert, never one per run."""
    old = [r for r in runs if r["status"] == "running" and r["cohort"] == "failed" and r["started_at"] and now - _utc(r["started_at"]) > ABANDONED_AFTER]
    old.sort(key=lambda r: r["started_at"])
    if not old:
        return None
    oldest = eastern_label(old[0]["started_at"], "%b %-d")
    return {"count": len(old), "oldest": oldest, "title": f"{len(old)} old runs were never closed (oldest {oldest})",
            "items": [{"name": r["title"], "when": eastern_label(r["started_at"], "%b %-d, %-I:%M %p ET"), "candidate_id": r["candidate_id"]} for r in old]}


def _clock(value: Any) -> str:
    try:
        return eastern_label(str(value), "%H:%M")
    except (ValueError, TypeError):
        return "—"


def _human_minutes(minutes: float | None) -> str:
    seconds = int(round((minutes or 0) * 60))
    return "—" if minutes is None else f"{seconds // 3600}h {seconds % 3600 // 60}m" if seconds >= 3600 else f"{seconds // 60}m {seconds % 60:02d}s"


def _ago(minutes: float) -> str:
    return "under a minute ago" if minutes < 1 else f"{minutes:.0f} min ago" if minutes < 90 else f"{minutes / 60:.0f} h ago" if minutes < 2880 else f"{minutes / 1440:.0f} days ago"


def _hour_floor(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


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


def memory_health(crashes_today: int, meminfo: Path = Path("/proc/meminfo")) -> dict[str, Any]:
    free_pct = None
    try:
        values = {line.split(":")[0]: int(line.split()[1]) for line in meminfo.read_text().splitlines() if ":" in line}
        free_pct = 100 * values["MemAvailable"] / values["MemTotal"]
    except (OSError, KeyError, ValueError, IndexError):
        pass
    crash = f"{crashes_today} crash{'es' if crashes_today != 1 else ''} today" if crashes_today else "no crashes today"
    word = "" if free_pct is None else f"{free_pct:.0f}% free · "
    tone = "red" if free_pct is not None and free_pct < 5 else "amber" if crashes_today or (free_pct is not None and free_pct < 15) else "green"
    return {"tone": tone, "value": word + crash}


def _gateway(path: str | None):
    raw = (path if path is not None else os.environ.get(GATEWAY_DATABASE_ENVIRONMENT_VARIABLE, "")).strip()
    return _open_read_only(Path(raw)) if raw and Path(raw).is_file() else None


def event_sentence(event: dict[str, Any], name: str, who: str) -> tuple[str, str]:
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
    if state == "failed":
        return f"{quoted} crashed: {plain_error(detail).rstrip('.').lower()}.", "red"
    if state == "implementation_blocked":
        return (f"{quoted} could not be tested: its rules are missing." if code == "rules_missing" else f"{quoted} could not be tested."), "amber"
    if state == "duplicate_closed":
        return f"{quoted} was closed as a duplicate of an earlier idea.", "grey"
    if state == "survivor":
        return f"{quoted} passed every test and is waiting for review.", "green"
    return f"{quoted}: {state.replace('_', ' ')}.", "grey"


def _group_requeues(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hundreds of 'put back in line' events at one restart become one line."""
    out: list[dict[str, Any]] = []
    for event in events:
        previous = out[-1] if out else None
        if previous and (event["reason_code"] or "").startswith("requeued") and previous["reason_code"] == event["reason_code"] and previous["state"] == "queued":
            previous["count"] += 1
            continue
        out.append({**event, "count": 1})
    return out


def _unavailable(base: dict[str, Any], message: str | None, draining: bool) -> dict[str, Any]:
    return {**base, **_EMPTY, "message": message, "pill": header_pill(running=0, draining=draining, last_finished_crashed=False), "headline": "Factory data is unavailable"}


def _log_rows(events: list[dict[str, Any]], titles: dict[str, str], submitters: dict[str, str], crashed_today: list[dict[str, Any]]) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = []
    for event in _group_requeues(events[:60])[:20]:
        sentence, tone = event_sentence(event, titles.get(event["candidate_id"], event["candidate_id"]), submitter_label(submitters.get(event["candidate_id"])))
        if event["count"] > 1:
            sentence, tone = f"{event['count']} ideas were put back in line after {'a software update' if event['reason_code'] == 'requeued_after_fix' else 'a restart'}.", "indigo"
        log.append({"t": _clock(event["created_at"]), "when": _utc(event["created_at"]), "tone": tone, "text": sentence})
    for run in crashed_today:  # run events: a crashed run is recorded on the run, not always as a campaign event
        log.append({"t": _clock(run["completed_at"]), "when": _utc(run["completed_at"]), "tone": "red", "text": f"“{run['title']}” crashed: {plain_error(run['error_summary']).rstrip('.').lower()}."})
    log = [{k: v for k, v in item.items() if k != "when"} for item in sorted(log, key=lambda r: r["when"], reverse=True)[:20]]
    return log


def _timeline_rows(runs: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    cutoff12 = now - timedelta(hours=12)
    for run in runs:
        if run["outcome"] == "abandoned" or not run["started_at"] or run["status"] == "created":
            continue
        end = now if run["status"] == "running" else _utc(run["completed_at"]) if run["completed_at"] else None
        if end is None or end < cutoff12:
            continue
        start = _utc(run["started_at"])
        timeline.append({"name": run["title"], "start": start.astimezone(EASTERN).replace(tzinfo=None), "end": end.astimezone(EASTERN).replace(tzinfo=None),
                         "minutes": max(0.0, (end - start).total_seconds() / 60), "outcome": run["outcome"], "candidate_id": run["candidate_id"]})
    return timeline


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
        durations = [(r[0], r[1]) for r in connection.execute("SELECT started_at,completed_at FROM experiment_runs WHERE completed_at IS NOT NULL AND started_at IS NOT NULL ORDER BY completed_at DESC LIMIT 50")]
        typical = median_minutes(durations)
        titles = {str(r[0]): str(r[1]) for r in connection.execute("SELECT draft_id, COALESCE(NULLIF(json_extract(candidate_json,'$.candidate.title'),''), title) FROM idea_drafts")}
        events: list[dict[str, Any]] = []
        queued_events: list[dict[str, Any]] = []
        submitters: dict[str, str] = {}
        grok_last = last_event = None
        if gate is not None:
            tables = {str(r[0]) for r in gate.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "campaign_events" in tables:
                events = [dict(r) for r in gate.execute("SELECT event_id,candidate_id,state,reason_code,reason_detail,run_id,created_at FROM campaign_events ORDER BY event_id DESC LIMIT 400")]
                last_event = (gate.execute("SELECT MAX(created_at) FROM campaign_events").fetchone() or [None])[0]
                queued_events = [dict(r) for r in gate.execute(
                    "SELECT e.candidate_id,e.created_at FROM campaign_events e WHERE e.event_id=(SELECT MAX(event_id) FROM campaign_events WHERE candidate_id=e.candidate_id) AND e.state='queued' ORDER BY e.event_id")]
            if "candidate_identities" in tables:
                submitters = {str(r[0]): str(r[1]) for r in gate.execute("SELECT candidate_id,created_by FROM candidate_identities")}
            if "gateway_audit" in tables:
                grok_last = (gate.execute("SELECT MAX(occurred_at) FROM gateway_audit WHERE agent_id='grok-remote'").fetchone() or [None])[0]
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return _unavailable(base, f"Factory state is unavailable: {exc}", draining)
    finally:
        connection.close()
        if gate is not None:
            gate.close()
    close_runs = {e["run_id"] for e in events if e["state"] == "screened_out" and e["run_id"] and is_close_call(e["reason_detail"])}
    for run in runs:
        run["outcome"] = "abandoned" if run["status"] == "running" and run["cohort"] == "failed" else run_outcome(run, close_runs)
    live = [r for r in runs if r["status"] == "running" and r["cohort"] == "open"]
    finished = [r for r in runs if r["completed_at"] and r["status"] in ("succeeded", "failed")]
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    today = [r for r in finished if _utc(r["completed_at"]) >= day_start]
    crashed_today = [r for r in today if r["outcome"] == "crashed"]
    passed_today, close_today = sum(r["outcome"] == "passed" for r in today), sum(r["outcome"] == "close" for r in today)
    latest_finished = max(finished, key=lambda r: _utc(r["completed_at"]), default=None)
    pill = header_pill(running=len(live), draining=draining, last_finished_crashed=bool(latest_finished and latest_finished["outcome"] == "crashed"))
    queue_rows = [{"n": position, "name": titles.get(item["candidate_id"], item["candidate_id"]), "who": submitter_label(submitters.get(item["candidate_id"])),
                   "when": _clock(item["created_at"]), "candidate_id": item["candidate_id"]} for position, item in enumerate(queued_events, 1)]
    longest = max((((now - _utc(i["created_at"])).total_seconds() / 60) for i in queued_events), default=None)
    # Hourly series, Eastern wall time, oldest first.
    top = _hour_floor(now)
    hours = [top - timedelta(hours=k) for k in range(47, -1, -1)]
    hourly = [{"hour": h.astimezone(EASTERN).replace(tzinfo=None), **{o: 0 for o in OUTCOMES}} for h in hours]
    index = {h: i for i, h in enumerate(hours)}
    for run in finished:
        slot = index.get(_hour_floor(_utc(run["completed_at"])))
        if slot is not None:
            hourly[slot][run["outcome"]] += 1
    last24, hours24 = hourly[-24:], hours[-24:]
    queued_per_hour = [0] * 24
    for e in events:
        if e["state"] == "queued" and e["reason_code"] == "waiting":
            k = int((now - _utc(e["created_at"])).total_seconds() // 3600)
            if 0 <= k < 24:
                queued_per_hour[23 - k] += 1
    busy = [sum(1 for r in runs if r["started_at"] and r["outcome"] != "abandoned" and _utc(r["started_at"]) < h + timedelta(hours=1) and (not r["completed_at"] or _utc(r["completed_at"]) >= h)) for h in hours24]
    typical_per_hour = [median_minutes([(r["started_at"], r["completed_at"]) for r in finished if _hour_floor(_utc(r["completed_at"])) == h]) or 0 for h in hours24]
    crash_reason = "none" if not crashed_today else plain_error(crashed_today[-1]["error_summary"]).rstrip(".").lower()
    crash_reason = crash_reason if len(crash_reason) <= 44 else crash_reason[:41].rstrip() + "…"
    tiles = [
        {"label": "Running now", "value": f"{len(live)}" if live else "idle", "sub": "one test at a time", "color": "indigo", "spark": busy},
        {"label": "Waiting", "value": f"{len(queue_rows)}", "sub": f"longest wait {_human_minutes(longest)}" if longest is not None else "nothing in line", "color": "text", "spark": queued_per_hour},
        {"label": "Finished today", "value": f"{len(today)}", "sub": f"{passed_today} passed · {close_today} close call{'s' if close_today != 1 else ''}", "color": "text",
         "spark": [sum(row[o] for o in ("failed", "close", "passed", "crashed")) for row in last24]},
        {"label": "Crashed today", "value": f"{len(crashed_today)}", "sub": crash_reason, "color": "red" if crashed_today else "text", "spark": [row["crashed"] for row in last24]},
        {"label": "Typical test time", "value": _human_minutes(typical), "sub": "median of the last 50", "color": "text", "spark": typical_per_hour},
    ]
    running_cards, alerts = [], []
    stage_keys = [key for key, _n in STEPS]
    for run in live:
        elapsed = (now - _utc(run["started_at"])).total_seconds() / 60 if run["started_at"] else 0.0
        slow = bool(typical and elapsed > SLOW_FACTOR * typical)
        current = stage_keys.index(run["stage"]) if run["stage"] in stage_keys else 0
        step = STEP_NAME.get(run["stage"], run["stage"])
        running_cards.append({"name": run["title"], "elapsed": _human_minutes(elapsed), "slow": slow, "candidate_id": run["candidate_id"],
                              "steps": ["done" if i < current else ("slow" if slow else "current") if i == current else "todo" for i in range(5)],
                              "where": f"Step {current + 1} of 5 · {step}", "note": f"typical {typical:.0f} min" if typical else "typical time not yet known"})
        if slow:
            alerts.append({"tone": "amber", "title": f"Slow: one test is taking {elapsed / typical:.1f}× longer than usual", "when": _clock(now.isoformat()), "sort": now.isoformat(),
                           "body": f"“{run['title']}” has been on “{step}” for {_human_minutes(elapsed)}.", "next": "Nothing to do yet.", "candidate_id": run["candidate_id"]})
    for run in sorted(crashed_today, key=lambda r: r["completed_at"], reverse=True)[:3]:
        reason = plain_error(run["error_summary"])
        alerts.append({"tone": "red", "title": f"Crashed: {reason.rstrip('.').lower()}", "when": _clock(run["completed_at"]), "sort": _utc(run["completed_at"]).isoformat(),
                       "body": f"“{run['title']}” stopped on “{STEP_NAME.get(run['stage'], run['stage'])}”.", "next": crash_fix(reason), "candidate_id": run["candidate_id"]})
    price = _price_health()
    if price["banner"]:
        alerts.append({"tone": "amber", "title": "Price data is out of date", "when": _clock(now.isoformat()), "sort": now.isoformat(), "body": price["banner"],
                       "next": "Fix: the nightly price update needs to run.", "candidate_id": None})
    alerts.sort(key=lambda a: a["sort"], reverse=True)
    old_runs = group_abandoned(runs, now)
    health: list[dict[str, Any]] = []
    if price["rows"]:
        health.append({"label": "Price data up to date", "tone": "amber" if price["banner"] else "green", "value": " · ".join(f"{r['market']} to {r['last']}" for r in price["rows"][:6])})
    else:
        health.append({"label": "Price data up to date", "tone": "amber", "value": "could not be read here" if price["error"] else "no price sets found"})
    if last_event:
        minutes = (now - _utc(last_event)).total_seconds() / 60
        idle = not live and not queue_rows
        health.append({"label": "Factory responding", "tone": "green" if idle or minutes <= 30 else "amber" if minutes <= 120 else "red",
                       "value": f"last event {_ago(minutes)}" + (" (idle)" if idle and minutes > 30 else "")})
    else:
        health.append({"label": "Factory responding", "tone": "amber", "value": "no events recorded"})
    health.append({"label": "Disk space", **disk_health(runtime_dir or database_path.parent)})
    health.append({"label": "Memory", **memory_health(len(crashed_today))})
    if grok_last:
        minutes = (now - _utc(grok_last)).total_seconds() / 60
        health.append({"label": "Grok connected", "tone": "green" if minutes <= 1440 else "amber", "value": "last request " + eastern_label(grok_last, "%a %-d %b, %H:%M") + " ET"})
    else:
        health.append({"label": "Grok connected", "tone": "amber", "value": "no requests recorded"})
    log = _log_rows(events, titles, submitters, crashed_today)
    timeline = _timeline_rows(runs, now)
    looks = len(alerts) + (1 if old_runs else 0)
    if not looks and not live and not queue_rows:
        headline = "All clear"
    else:
        headline = f"{len(live)} test{'s' if len(live) != 1 else ''} running, {len(queue_rows)} waiting. " + (f"{looks} thing{'s' if looks != 1 else ''} need{'s' if looks == 1 else ''} a look." if looks else "All clear.")
    return {**base, "available": True, "message": "", "pill": pill, "headline": headline, "typical_minutes": typical, "tiles": tiles, "running": running_cards, "alerts": alerts, "old_runs": old_runs,
            "queue": {"total": len(queue_rows), "next": queue_rows[:4], "next_start": f"~{typical:.0f} min (estimate)" if queue_rows and typical else None},
            "timeline": timeline, "hourly": hourly, "health": health, "log": log}


__all__ = ["load_factory_overview", "load_factory_page", "load_factory_summary"]
