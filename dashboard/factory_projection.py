"""Read-only, server-paged projection for the Factory runs workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from dashboard.overview_projection import (
    SURVIVOR_EVENT_MESSAGE,
    SURVIVOR_EVENT_SOURCE,
    _scalar,
    _validated_connection,
    configured_database_path,
)


RUN_PAGE_LIMIT = 100
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
       CASE WHEN EXISTS (
           SELECT 1 FROM run_operator_events e WHERE e.run_id=r.run_id AND e.source=? AND e.message=?
       ) THEN 1 ELSE 0 END AS survivor_count,
       CASE WHEN r.status IN ('created','running') THEN 'open'
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


def _row(row: sqlite3.Row) -> dict[str, Any]:
    duration = _duration_minutes(row["started_at"], row["completed_at"])
    return {
        "run_id": str(row["run_id"]), "configuration_id": str(row["configuration_id"]),
        "title": str(row["title"]) if row["candidate_id"] else str(row["title"]).replace("_", " ").title(), "symbol": str(row["symbol"]), "stage": str(row["stage"]),
        "status": str(row["status"]), "cohort": str(row["cohort"]),
        "variation_count": int(row["variation_count"] or 0), "survivor_count": int(row["survivor_count"] or 0),
        "started_at": str(row["started_at"] or ""), "completed_at": str(row["completed_at"] or ""),
        "created_at": str(row["created_at"] or ""), "error_summary": str(row["error_summary"] or ""),
        "duration_minutes": duration, "resource_state": "Unavailable", "worker": "Unavailable",
    }


def load_factory_summary(*, database: str | Path | None = None) -> dict[str, Any]:
    database_path = Path(database) if database is not None else configured_database_path()
    connection, error = _validated_connection(database_path)
    if connection is None:
        return {"available": False, "message": error, "counts": {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}, "throughput_24h": 0, "median_minutes": None}
    try:
        source = f"WITH run_records AS ({RUN_SOURCE})"
        rows = connection.execute(source + " SELECT cohort,status,COUNT(*) count FROM run_records GROUP BY cohort,status", _params()).fetchall()
        counts = {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}
        for row in rows:
            counts[str(row["cohort"])] += int(row["count"])
            if row["status"] == "running": counts["running"] += int(row["count"])
            if row["status"] == "created": counts["queued"] += int(row["count"])
        boundary = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 86400, timezone.utc).isoformat()
        throughput = _scalar(connection, "SELECT COUNT(*) FROM parameter_results p JOIN experiment_runs r ON r.run_id=p.run_id WHERE COALESCE(r.completed_at,r.created_at)>=?", [boundary])
        durations = [_duration_minutes(row[0], row[1]) for row in connection.execute("SELECT started_at,completed_at FROM experiment_runs WHERE completed_at IS NOT NULL")]
        measured = sorted(value for value in durations if value is not None)
        median = measured[len(measured)//2] if measured else None
        markets = [str(row[0]) for row in connection.execute(source + " SELECT DISTINCT symbol FROM run_records ORDER BY symbol", _params())]
        stages = [str(row[0]) for row in connection.execute(source + " SELECT DISTINCT stage FROM run_records ORDER BY stage", _params())]
        return {"available": True, "message": "Read-only Factory state loaded.", "counts": counts, "throughput_24h": throughput, "median_minutes": median, "markets": markets, "stages": stages}
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return {"available": False, "message": f"Factory state is unavailable: {exc}", "counts": {"open": 0, "completed": 0, "failed": 0, "running": 0, "queued": 0}, "throughput_24h": 0, "median_minutes": None, "markets": [], "stages": []}
    finally:
        connection.close()


def load_factory_page(
    *, cohort: str = "completed", search: str = "", market: str = "all", stage: str = "all",
    resource: str = "all", start: int = 0, end: int = 50,
    sort_model: list[dict[str, Any]] | None = None, filter_model: dict[str, dict[str, Any]] | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None: return {"rowData": [], "rowCount": 0}
    try:
        conditions, params = ["cohort=?"], [cohort]
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
        source = f"WITH run_records AS ({RUN_SOURCE})"; where = " AND ".join(conditions); base = _params() + params
        total = _scalar(connection, source + f" SELECT COUNT(*) FROM run_records WHERE {where}", base)
        limit = min(RUN_PAGE_LIMIT, max(1, int(end)-int(start)))
        rows = connection.execute(source + f" SELECT * FROM run_records WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", base + [limit, max(0,int(start))]).fetchall()
        return {"rowData": [_row(row) for row in rows], "rowCount": total}
    except (sqlite3.Error, ValueError, TypeError):
        return {"rowData": [], "rowCount": 0}
    finally:
        connection.close()


__all__ = ["load_factory_page", "load_factory_summary"]
