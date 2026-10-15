"""Read-only, server-paged projection for the Factory runs workspace."""

from __future__ import annotations

from datetime import datetime, timezone

from pathlib import Path
import sqlite3
from typing import Any

from dashboard.time_display import eastern_label
from dashboard.overview_projection import (
    SURVIVOR_EVENT_MESSAGE,
    SURVIVOR_EVENT_SOURCE,
    _scalar,
    _validated_connection,
    configured_database_path,
)


RUN_PAGE_LIMIT = 100
# Test fixtures that leaked into the research database; hidden from default views, never deleted.
TEST_TITLE_MARKERS = ("connection test", "five-bar run exhaustion")
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


__all__ = ["load_factory_page", "load_factory_summary"]
