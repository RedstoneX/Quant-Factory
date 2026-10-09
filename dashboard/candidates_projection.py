"""Bounded, read-only projection for the Candidates workspace."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Any

from dashboard.overview_projection import (
    BASE_CTE,
    CANDIDATE_PAGE_LIMIT,
    _base_params,
    _finite_number,
    _scalar,
    _validated_connection,
    configured_database_path,
)


CANDIDATE_SORT_FIELDS = {
    "title": "title", "symbol": "symbol", "family": "family",
    "lifecycle": "lifecycle", "sharpe": "sharpe", "max_drawdown": "max_drawdown",
    "retained": "retained", "net_return": "net_return", "robustness": "robustness",
    "paper": "paper", "updated_at": "observed_at",
}


def _candidate_source() -> str:
    return """
        SELECT c.candidate_id, c.configuration_id, c.candidate_json, c.description,
               c.title, c.symbol, c.asset_class,
               COALESCE(json_extract(c.candidate_json, '$.candidate.family'), 'Not recorded') AS family,
               COALESCE(json_extract(c.candidate_json, '$.candidate.status'), 'received') AS packet_status,
               c.run_id, c.stage, c.run_status, c.screening_status, c.error_summary,
               c.survivor, c.observed_at,
               CAST(json_extract(c.oos_metrics_json, '$.sharpe_ratio') AS REAL) AS sharpe,
               CAST(json_extract(c.oos_metrics_json, '$.max_drawdown') AS REAL) AS max_drawdown,
               CAST(json_extract(c.oos_metrics_json, '$.total_return') AS REAL) AS net_return,
               NULL AS retained,
               CASE
                 WHEN c.survivor=1 THEN 'survivor'
                 WHEN LOWER(COALESCE(json_extract(c.candidate_json, '$.candidate.status'), '')) IN ('needs_review','exception_hold') THEN 'needs_review'
                 WHEN c.run_status IN ('created','running') THEN 'advancing'
                 WHEN LOWER(COALESCE(json_extract(c.candidate_json, '$.candidate.status'), ''))='rejected'
                   OR c.run_status IN ('failed','cancelled')
                   OR c.screening_status IN ('screened_out','invalid','insufficient') THEN 'rejected'
                 ELSE 'received' END AS lifecycle,
               CASE
                 WHEN c.stage IN ('robustness','monte_carlo') AND c.run_status='succeeded' THEN 'Passed'
                 WHEN c.stage IN ('robustness','monte_carlo') AND c.run_status IN ('created','running') THEN 'Testing'
                 ELSE 'Not run' END AS robustness,
               CASE WHEN c.survivor=1 THEN 'Lane inactive' ELSE 'Ineligible' END AS paper
        FROM candidates c
    """


def _candidate_conditions(
    *, lifecycle: str, market: str, family: str, evidence: str, search: str,
) -> tuple[list[str], list[Any]]:
    conditions = ["1=1"]
    params: list[Any] = []
    if lifecycle != "all":
        conditions.append("lifecycle=?"); params.append(lifecycle)
    if market != "all":
        conditions.append("asset_class=?"); params.append(market)
    if family != "all":
        conditions.append("LOWER(family)=LOWER(?)"); params.append(family)
    if evidence == "all_gates":
        conditions.append("survivor=1")
    elif evidence == "failed_oos":
        conditions.append("stage='oos' AND COALESCE(screening_status,'')<>'passed'")
    elif evidence == "semantic_exception":
        conditions.append("lifecycle='needs_review'")
    if search.strip():
        token = f"%{search.strip().lower()}%"
        conditions.append("(LOWER(title) LIKE ? OR LOWER(symbol) LIKE ? OR LOWER(family) LIKE ? OR LOWER(candidate_id) LIKE ?)")
        params.extend([token, token, token, token])
    return conditions, params


def _candidate_grid_row(row: sqlite3.Row, *, rank: int | None = None) -> dict[str, Any]:
    def percent(value: Any, *, absolute: bool = False) -> float | None:
        number = _finite_number(value)
        if number is None:
            return None
        number = abs(number) if absolute else number
        return number * 100 if abs(number) <= 1 else number

    candidate_json = str(row["candidate_json"] or "")
    return {
        "candidate_id": str(row["candidate_id"]),
        "candidate_version": hashlib.sha256(candidate_json.encode()).hexdigest() if candidate_json else None,
        "configuration_id": str(row["configuration_id"]) if row["configuration_id"] else None,
        "run_id": str(row["run_id"]) if row["run_id"] else None,
        "title": str(row["title"] or "Untitled Candidate"), "description": str(row["description"] or ""),
        "symbol": str(row["symbol"] or "Unrecorded"), "family": str(row["family"] or "Not recorded"),
        "lifecycle": str(row["lifecycle"]), "packet_status": str(row["packet_status"]),
        "stage": str(row["stage"] or "not_run"), "run_status": str(row["run_status"] or "not_run"),
        "screening_status": str(row["screening_status"] or "not_run"), "error_summary": row["error_summary"],
        "sharpe": _finite_number(row["sharpe"]), "max_drawdown": percent(row["max_drawdown"], absolute=True),
        "retained": _finite_number(row["retained"]), "net_return": percent(row["net_return"]),
        "robustness": str(row["robustness"]), "paper": str(row["paper"]),
        "updated_at": str(row["observed_at"]), "rank": rank,
    }


def load_candidates_summary(*, database: str | Path | None = None) -> dict[str, Any]:
    """Aggregate the complete Candidate population and return bounded facets."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, error = _validated_connection(database_path)
    if connection is None:
        return {"available": False, "message": error, "counts": {key: 0 for key in ("survivor","advancing","needs_review","rejected","all")}, "families": []}
    try:
        source = BASE_CTE + ", candidate_records AS (" + _candidate_source() + ")"
        rows = connection.execute(source + " SELECT lifecycle, COUNT(*) AS count FROM candidate_records GROUP BY lifecycle", _base_params()).fetchall()
        counts = {key: 0 for key in ("survivor", "advancing", "needs_review", "rejected", "all")}
        for row in rows:
            key = str(row["lifecycle"]); counts[key] = int(row["count"]); counts["all"] += int(row["count"])
        families = [str(row[0]) for row in connection.execute(source + " SELECT DISTINCT family FROM candidate_records ORDER BY LOWER(family) LIMIT 100", _base_params())]
        return {"available": True, "message": "Read-only Candidate state loaded.", "counts": counts, "families": families}
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return {"available": False, "message": f"Candidate state could not be projected safely: {exc}", "counts": {key: 0 for key in ("survivor","advancing","needs_review","rejected","all")}, "families": []}
    finally:
        connection.close()


def load_candidates_page(
    *, lifecycle: str = "survivor", market: str = "all", family: str = "all",
    evidence: str = "any", search: str = "", start: int = 0, end: int = 50,
    sort_model: list[dict[str, Any]] | None = None,
    filter_model: dict[str, dict[str, Any]] | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Return one capped server-sorted and server-filtered Candidate page."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return {"rowData": [], "rowCount": 0}
    try:
        conditions, params = _candidate_conditions(lifecycle=lifecycle, market=market, family=family, evidence=evidence, search=search)
        for field, model in (filter_model or {}).items():
            column = CANDIDATE_SORT_FIELDS.get(field)
            value = model.get("filter")
            if column and value not in (None, ""):
                if str(model.get("filterType")) == "number":
                    operator = {"greaterThan": ">", "greaterThanOrEqual": ">=", "lessThan": "<", "lessThanOrEqual": "<=", "equals": "="}.get(str(model.get("type")), "=")
                    conditions.append(f"{column} {operator} ?"); params.append(float(value))
                else:
                    conditions.append(f"LOWER(COALESCE(CAST({column} AS TEXT),'')) LIKE ?"); params.append(f"%{str(value).lower()}%")
        order = "sharpe DESC, max_drawdown ASC, candidate_id ASC"
        if sort_model:
            requested = sort_model[0]; column = CANDIDATE_SORT_FIELDS.get(str(requested.get("colId")))
            if column:
                direction = "DESC" if requested.get("sort") == "desc" else "ASC"
                order = f"{column} {direction}, candidate_id ASC"
        source = BASE_CTE + ", candidate_records AS (" + _candidate_source() + ")"
        where = " AND ".join(conditions)
        base_params = _base_params() + params
        total = _scalar(connection, source + f" SELECT COUNT(*) FROM candidate_records WHERE {where}", base_params)
        limit = min(CANDIDATE_PAGE_LIMIT, max(1, int(end) - int(start)))
        rows = connection.execute(source + f" SELECT * FROM candidate_records WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", base_params + [limit, max(0, int(start))]).fetchall()
        return {"rowData": [_candidate_grid_row(row, rank=max(0, int(start)) + index + 1) for index, row in enumerate(rows)], "rowCount": total}
    except (sqlite3.Error, ValueError, TypeError):
        return {"rowData": [], "rowCount": 0}
    finally:
        connection.close()


def load_candidate_detail(candidate_id: str | None, *, database: str | Path | None = None) -> dict[str, Any] | None:
    """Hydrate one exact Candidate plus bounded latest-per-stage lineage."""
    if not candidate_id:
        return None
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None:
        return None
    try:
        source = BASE_CTE + ", candidate_records AS (" + _candidate_source() + ")"
        row = connection.execute(source + " SELECT * FROM candidate_records WHERE candidate_id=?", _base_params() + [candidate_id]).fetchone()
        if row is None:
            return None
        detail = _candidate_grid_row(row)
        stages = connection.execute("""
            WITH ranked AS (
              SELECT run_id, stage, status, created_at, completed_at, error_summary,
                     ROW_NUMBER() OVER (PARTITION BY stage ORDER BY created_at DESC, run_id DESC) AS recency
              FROM experiment_runs WHERE configuration_id=?
            ) SELECT run_id,stage,status,created_at,completed_at,error_summary FROM ranked WHERE recency=1 ORDER BY created_at
        """, [detail["configuration_id"]]).fetchall() if detail["configuration_id"] else []
        detail["progression"] = [dict(stage) for stage in stages]
        return detail
    except (sqlite3.Error, ValueError, TypeError):
        return None
    finally:
        connection.close()


__all__ = ["load_candidates_summary", "load_candidates_page", "load_candidate_detail"]
