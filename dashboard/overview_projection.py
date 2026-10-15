"""Bounded, read-only Dashboard projection over authoritative Quant Factory state."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = REPOSITORY_ROOT / "state" / "quant_factory.sqlite3"
DATABASE_ENVIRONMENT_VARIABLE = "QUANT_FACTORY_DB_PATH"
GATEWAY_DATABASE_ENVIRONMENT_VARIABLE = "QF_GATEWAY_DB_PATH"
EXPECTED_SCHEMA_VERSION = 7
SURVIVOR_EVENT_SOURCE = "candidate_pipeline_runtime"
SURVIVOR_EVENT_MESSAGE = "Factory filter chain completed and is ready for the protected-test gate."
CHART_LIMIT = 200
SURVIVOR_LIMIT = 50
CANDIDATE_PAGE_LIMIT = 100
# Throwaway entries (connectivity probes, smoke runs): hidden from every count and list by default; never deleted.
TEST_TITLE_PATTERNS = ("connection test%", "smoke test%", "test idea%", "test candidate%", "dummy%")
IS_TEST_SQL = "CASE WHEN " + " OR ".join(f"LOWER(d.title) LIKE '{pattern}'" for pattern in TEST_TITLE_PATTERNS) + " THEN 1 ELSE 0 END"


def live_run_clause(status: str, candidate_id: str) -> str:
    """SQL for "this run is really running": the one rule every page counts running tests by.

    A run left marked running by a server restart is live only while its idea's latest
    campaign event still says running. Waiting runs are always live.
    """
    return (f"({status}='created' OR ({status}='running' AND ({candidate_id} IS NULL OR EXISTS ("
            f"SELECT 1 FROM qf_campaign_admissions live_q WHERE live_q.candidate_id={candidate_id} AND live_q.state='running'))))")


STAGE_REACH = "WHEN 'oos' THEN 3 WHEN 'walk_forward' THEN 4 WHEN 'robustness' THEN 5 WHEN 'monte_carlo' THEN 5 ELSE 0"
# Funnel levels: 1 received, 2 after costs, 3 unseen data, 4 over time, 5 stress test, 6 passed.
FUNNEL_LEVEL = {"submitted": 1, "costs": 2, "oos": 3, "walk_forward": 4, "robustness": 5, "survivors": 6}
ADVANCING_CONDITION = "(" + live_run_clause("c.run_status", "c.candidate_id") + " AND c.survivor=0)"  # a passed idea counts as passed, not as testing


def configured_database_path() -> Path:
    configured = os.environ.get(DATABASE_ENVIRONMENT_VARIABLE)
    return Path(configured) if configured else DEFAULT_DATABASE_PATH


def _window_boundary(window: str) -> str | None:
    now = datetime.now(timezone.utc)
    if window == "30d":
        return datetime.fromtimestamp(now.timestamp() - 30 * 86400, timezone.utc).isoformat()
    if window == "90d":
        return datetime.fromtimestamp(now.timestamp() - 90 * 86400, timezone.utc).isoformat()
    if window == "ytd":
        return datetime(now.year, 1, 1, tzinfo=timezone.utc).isoformat()
    return None


def _open_read_only(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _empty_snapshot(*, database: Path, message: str, window: str, market: str) -> dict[str, Any]:
    return {
        "available": False, "message": message, "database": str(database),
        "window": window, "market": market, "observed_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"running": 0, "queued": 0, "survivors": 0, "advancing": 0, "needs": None, "failed": 0},
        "stages": {"submitted": 0, "costs": 0, "oos": 0, "walk_forward": 0, "robustness": 0, "survivors": 0},
        "operation": {"active": 0, "terminal": 0, "bottleneck": "Unavailable", "median_minutes": None},
        "chart": [], "survivors": [], "chart_limit": CHART_LIMIT,
        "survivor_limit": SURVIVOR_LIMIT, "population_count": 0,
        "latest_finding": None,
    }


BASE_CTE = f"""
WITH candidate_base AS (
    SELECT d.draft_id AS candidate_id, d.title, d.description, d.candidate_json,
           d.configuration_id, d.updated_at,
           {IS_TEST_SQL} AS is_test,
           campaign.policy_id AS campaign_policy_id,
           campaign.state AS campaign_state,
           campaign.reason_code AS campaign_reason_code,
           campaign.reason_detail AS campaign_reason_detail,
           COALESCE(c.canonical_config_json, '{{}}') AS canonical_config_json,
           COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'),
                    json_extract(d.candidate_json, '$.market.instruments.preferred[0]'),
                    'Unrecorded') AS symbol,
           CASE LOWER(COALESCE(json_extract(c.canonical_config_json, '$.market_data.asset_class'), ''))
             WHEN 'future' THEN 'futures' WHEN 'futures' THEN 'futures'
             WHEN 'equity' THEN 'equities' WHEN 'equities' THEN 'equities'
             WHEN 'etf' THEN 'equities' WHEN 'index' THEN 'equities'
             WHEN 'crypto' THEN 'crypto' WHEN 'cryptocurrency' THEN 'crypto'
             ELSE 'unclassified' END AS asset_class
    FROM idea_drafts d
    LEFT JOIN experiment_configurations c ON c.configuration_id = d.configuration_id
    LEFT JOIN qf_campaign_admissions campaign ON campaign.candidate_id=d.draft_id
    WHERE d.candidate_json <> ''
), latest_runs AS (
    SELECT r.*, ROW_NUMBER() OVER (
        PARTITION BY r.configuration_id ORDER BY r.created_at DESC, r.run_id DESC
    ) AS recency
    FROM experiment_runs r
), survivor_runs AS (
    SELECT r.*, ROW_NUMBER() OVER (
        PARTITION BY r.configuration_id ORDER BY r.created_at DESC, r.run_id DESC
    ) AS survivor_rank
    FROM experiment_runs r
    JOIN run_operator_events e ON e.run_id = r.run_id
    WHERE e.source = ? AND e.message = ?
), best_results AS (
    SELECT p.*, ROW_NUMBER() OVER (
        PARTITION BY p.run_id ORDER BY p.ranking_position, p.row_id
    ) AS result_rank
    FROM parameter_results p
), latest_oos_runs AS (
    SELECT r.*, ROW_NUMBER() OVER (
        PARTITION BY r.configuration_id ORDER BY r.created_at DESC, r.run_id DESC
    ) AS oos_recency
    FROM experiment_runs r
    WHERE r.stage='oos' AND r.status='succeeded'
), best_oos_results AS (
    SELECT p.*, ROW_NUMBER() OVER (
        PARTITION BY p.run_id ORDER BY p.ranking_position, p.row_id
    ) AS oos_result_rank
    FROM parameter_results p
), candidates AS (
    SELECT cb.*, lr.run_id AS run_id,
           lr.stage AS stage,
           lr.status AS run_status,
           lr.created_at AS run_created_at,
           lr.started_at AS started_at,
           lr.completed_at AS completed_at,
           lr.error_summary AS error_summary,
           br.metrics_json, br.screening_status,
           obr.metrics_json AS oos_metrics_json,
           oor.run_id AS oos_run_id,
           CASE WHEN sr.run_id IS NULL THEN 0 ELSE 1 END AS survivor,
           CASE WHEN sr.run_id IS NOT NULL THEN 6 ELSE MAX(
             COALESCE((SELECT MAX(CASE fr.stage {STAGE_REACH} END) FROM experiment_runs fr
                       WHERE fr.configuration_id=cb.configuration_id AND fr.status='succeeded'), 0),
             CASE WHEN EXISTS (SELECT 1 FROM experiment_runs pr JOIN parameter_results pp ON pp.run_id=pr.run_id
                               WHERE pr.configuration_id=cb.configuration_id AND pp.screening_status='passed')
                  THEN 2 ELSE 1 END) END AS reach,
           COALESCE(lr.created_at, cb.updated_at) AS observed_at
    FROM candidate_base cb
    LEFT JOIN latest_runs lr ON lr.configuration_id = cb.configuration_id AND lr.recency = 1
    LEFT JOIN survivor_runs sr ON sr.configuration_id = cb.configuration_id AND sr.survivor_rank = 1
    LEFT JOIN best_results br ON br.run_id = lr.run_id AND br.result_rank = 1
    LEFT JOIN latest_oos_runs oor ON oor.configuration_id=cb.configuration_id AND oor.oos_recency=1
    LEFT JOIN best_oos_results obr ON obr.run_id=oor.run_id AND obr.oos_result_rank=1
)
"""


def _base_params() -> list[Any]:
    return [SURVIVOR_EVENT_SOURCE, SURVIVOR_EVENT_MESSAGE]


def _filter_clause(*, window: str, market: str, alias: str = "c", include_window: bool = True) -> tuple[str, list[Any]]:
    clauses = [f"(? = 'all' OR {alias}.asset_class = ?)", f"{alias}.is_test=0"]
    params: list[Any] = [market, market]
    boundary = _window_boundary(window) if include_window else None
    if boundary:
        clauses.append(f"{alias}.observed_at >= ?")
        params.append(boundary)
    return " AND ".join(clauses), params


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _unseen_report(row: sqlite3.Row, database: Path, reader: Callable[..., dict[str, Any] | None] | None) -> dict[str, Any] | None:
    """The unseen-data report for this row's unseen-data run; the caller above this module supplies the reader."""
    if reader is None:
        return None
    keys = row.keys()
    run_id = row["oos_run_id"] if "oos_run_id" in keys and row["oos_run_id"] else (row["run_id"] if row["stage"] == "oos" else None)
    return reader(database=database, run_id=str(run_id)) if run_id else None


def _row_view(row: sqlite3.Row, *, oos_metric: bool, report: dict[str, Any] | None = None) -> dict[str, Any]:
    candidate_json = str(row["candidate_json"] or "")
    try:
        candidate = json.loads(candidate_json).get("candidate") or {}
    except (json.JSONDecodeError, AttributeError):
        candidate = {}
    try:
        metric_field = (
            "oos_metrics_json"
            if oos_metric and "oos_metrics_json" in row.keys() and row["oos_metrics_json"]
            else "metrics_json"
        )
        metrics = json.loads(str(row[metric_field] or "{}"))
    except json.JSONDecodeError:
        metrics = {}
    if oos_metric and report and _finite_number(metrics.get("sharpe_ratio")) is None:
        metrics = report  # the pipeline keeps unseen-data metrics in its report artifact, not in parameter rows
    drawdown = _finite_number(metrics.get("max_drawdown"))
    if drawdown is not None:
        drawdown = abs(drawdown) * 100 if abs(drawdown) <= 1 else abs(drawdown)
    sharpe = _finite_number(metrics.get("sharpe_ratio")) if oos_metric else None
    candidate_id = str(row["candidate_id"]) if row["candidate_id"] else None
    return {
        "candidate_id": candidate_id,
        "configuration_id": str(row["configuration_id"]) if row["configuration_id"] else None,
        "candidate_version": hashlib.sha256(candidate_json.encode()).hexdigest() if candidate_json else None,
        "title": str(candidate.get("title") or row["title"] or "Untitled Candidate"),
        "family": str(candidate.get("family") or "Not recorded"),
        "symbol": str(row["symbol"] or "Unrecorded"),
        # Open goes to the unseen-data results: a succeeded unseen-data run if there is one, else the latest run.
        "run_id": str(row["oos_run_id"] if "oos_run_id" in row.keys() and row["oos_run_id"] else row["run_id"]) if row["run_id"] else None,
        "stage": str(row["stage"] or "not_run"),
        "run_status": str(row["run_status"] or "not_run"),
        "outcome": str(row["screening_status"] or row["run_status"] or "not_run"),
        "sharpe": sharpe, "max_drawdown": drawdown, "retained": None,
        "state": "survivor" if row["survivor"] else "advancing" if row["run_status"] in {"created", "running"} else "closed",
        "paper": "Inactive", "updated_at": str(row["observed_at"]),
        "record_type": "candidate" if candidate_id else "factory_study",
    }


RUN_BASE_CTE = """
WITH run_records AS (
    SELECT r.run_id, r.configuration_id, r.stage, r.status AS run_status,
           r.created_at, r.completed_at, r.error_summary,
           c.experiment_id, c.canonical_config_json,
           COALESCE(s.display_name, c.experiment_id, r.strategy_id) AS title,
           COALESCE(json_extract(c.canonical_config_json, '$.market_data.symbol'),
                    json_extract(c.canonical_config_json, '$.market_data.dataset_id'),
                    'Unrecorded') AS symbol,
           CASE
             WHEN LOWER(COALESCE(json_extract(c.canonical_config_json, '$.market_data.asset_class'),
                                      json_extract(c.canonical_config_json, '$.market_data.dataset_id'), ''))
                    LIKE 'future%' THEN 'futures'
             WHEN LOWER(COALESCE(json_extract(c.canonical_config_json, '$.market_data.asset_class'),
                                      json_extract(c.canonical_config_json, '$.market_data.dataset_id'), ''))
                    IN ('equity','equities','etf','index') THEN 'equities'
             WHEN LOWER(COALESCE(json_extract(c.canonical_config_json, '$.market_data.asset_class'),
                                      json_extract(c.canonical_config_json, '$.market_data.dataset_id'), ''))
                    LIKE 'crypto%' THEN 'crypto'
             ELSE 'unclassified' END AS asset_class,
           d.draft_id AS candidate_id, COALESCE(d.candidate_json, '') AS candidate_json,
           p.metrics_json, p.screening_status,
           CASE WHEN EXISTS (
             SELECT 1 FROM run_operator_events e
             WHERE e.run_id=r.run_id AND e.source=? AND e.message=?
           ) THEN 1 ELSE 0 END AS survivor,
           COALESCE(r.completed_at, r.created_at) AS observed_at
    FROM experiment_runs r
    JOIN experiment_configurations c ON c.configuration_id=r.configuration_id
    LEFT JOIN strategies s
      ON s.strategy_id=r.strategy_id AND s.strategy_version=r.strategy_version
    LEFT JOIN idea_drafts d
      ON d.configuration_id=r.configuration_id AND d.candidate_json<>''
     AND d.draft_id=(
       SELECT CASE WHEN COUNT(*)=1 THEN MIN(bound.draft_id) END
       FROM idea_drafts bound
       WHERE bound.configuration_id=r.configuration_id AND bound.candidate_json<>''
     )
    LEFT JOIN parameter_results p
      ON p.run_id=r.run_id AND p.ranking_position=(
        SELECT MIN(best.ranking_position) FROM parameter_results best WHERE best.run_id=r.run_id
      )
)
"""


def _run_filter_clause(*, window: str, market: str, alias: str = "r", include_window: bool = True) -> tuple[str, list[Any]]:
    clauses = [f"(? = 'all' OR {alias}.asset_class = ?)"]
    params: list[Any] = [market, market]
    boundary = _window_boundary(window) if include_window else None
    if boundary:
        clauses.append(f"{alias}.observed_at >= ?")
        params.append(boundary)
    return " AND ".join(clauses), params


def _scalar(connection: sqlite3.Connection, sql: str, params: list[Any]) -> int:
    row = connection.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _validated_connection(database: Path) -> tuple[sqlite3.Connection | None, str | None]:
    if not database.is_file():
        return None, "The configured research state database does not exist."
    try:
        connection = _open_read_only(database)
        required = {"schema_metadata", "strategies", "idea_drafts", "experiment_configurations", "experiment_runs", "parameter_results", "run_operator_events"}
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(required - tables)
        if missing:
            connection.close(); return None, f"Research state is missing required tables: {', '.join(missing)}."
        version_row = connection.execute("SELECT schema_version FROM schema_metadata").fetchone()
        version = int(version_row[0]) if version_row else None
        if version != EXPECTED_SCHEMA_VERSION:
            connection.close(); return None, f"Research state schema {version!r} is unsupported; expected {EXPECTED_SCHEMA_VERSION}."
        connection.execute("""CREATE TEMP TABLE qf_campaign_admissions (
            candidate_id TEXT PRIMARY KEY, policy_id TEXT, state TEXT,
            reason_code TEXT, reason_detail TEXT
        )""")
        gateway_path = os.environ.get(GATEWAY_DATABASE_ENVIRONMENT_VARIABLE, "").strip()
        if gateway_path and Path(gateway_path).is_file():
            gateway = _open_read_only(Path(gateway_path))
            try:
                gateway_tables = {str(row[0]) for row in gateway.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "campaign_events" in gateway_tables:
                    rows = gateway.execute("""SELECT event.candidate_id,event.policy_id,event.state,
                        event.reason_code,event.reason_detail
                        FROM campaign_events event JOIN (
                          SELECT candidate_id,MAX(event_id) event_id FROM campaign_events GROUP BY candidate_id
                        ) latest ON latest.event_id=event.event_id""").fetchall()
                    connection.executemany("INSERT INTO qf_campaign_admissions VALUES (?,?,?,?,?)", [tuple(row) for row in rows])
            finally:
                gateway.close()
        return connection, None
    except (OSError, sqlite3.Error, ValueError) as exc:
        return None, f"Research state is unavailable: {exc}"


def load_dashboard_snapshot(
    *, window: str = "90d", market: str = "all", database: str | Path | None = None,
    unseen_report: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Read SQL-side aggregates and bounded display cohorts without mutation."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, error = _validated_connection(database_path)
    if connection is None:
        return _empty_snapshot(database=database_path, message=error or "Research state is unavailable.", window=window, market=market)
    try:
        historical_filter, historical_params = _filter_clause(window=window, market=market)
        current_filter, current_params = _filter_clause(window=window, market=market, include_window=False)
        population = _scalar(connection, BASE_CTE + f"SELECT COUNT(*) FROM candidates c WHERE {historical_filter}", _base_params() + historical_params)
        survivors_count = _scalar(connection, BASE_CTE + f"SELECT COUNT(*) FROM candidates c WHERE c.survivor=1 AND {historical_filter}", _base_params() + historical_params)

        run_filter, run_params = _run_filter_clause(window=window, market=market)
        current_run_filter, current_run_params = _run_filter_clause(window=window, market=market, include_window=False)
        active_sql = RUN_BASE_CTE + f"""
            SELECT r.run_status, r.stage, COUNT(*) AS run_count
            FROM run_records r
            WHERE {live_run_clause('r.run_status','r.candidate_id')} AND {current_run_filter}
            GROUP BY r.run_status, r.stage
        """
        active_rows = list(connection.execute(active_sql, _base_params() + current_run_params))
        running = sum(int(row["run_count"]) for row in active_rows if row["run_status"] == "running")
        queued = sum(int(row["run_count"]) for row in active_rows if row["run_status"] == "created")
        advancing = _scalar(connection, BASE_CTE + f"""
            SELECT COUNT(*) FROM candidates c
            WHERE {ADVANCING_CONDITION} AND {current_filter}
        """, _base_params() + current_params)
        failed = _scalar(connection, RUN_BASE_CTE + f"SELECT COUNT(*) FROM run_records r WHERE (r.run_status='failed' OR (r.run_status='running' AND NOT {live_run_clause('r.run_status','r.candidate_id')})) AND {run_filter}", _base_params() + run_params)
        terminal = _scalar(connection, RUN_BASE_CTE + f"SELECT COUNT(*) FROM run_records r WHERE r.run_status IN ('succeeded','failed','cancelled') AND {run_filter}", _base_params() + run_params)

        # A true funnel: each stage counts the ideas that reached it, so it never grows going down.
        def stage_count(level: int) -> int:
            return _scalar(connection, BASE_CTE + f"""
                SELECT COUNT(*) FROM candidates c WHERE c.reach>=? AND {historical_filter}
            """, _base_params() + [level] + historical_params)

        stages = {key: stage_count(level) for key, level in FUNNEL_LEVEL.items()}
        bottleneck = max(active_rows, key=lambda row: int(row["run_count"]))["stage"] if active_rows else "No active runs"

        chart_sql = BASE_CTE + f"""
            SELECT c.* FROM candidates c
            WHERE c.oos_metrics_json IS NOT NULL AND {historical_filter}
            ORDER BY CAST(json_extract(c.oos_metrics_json, '$.sharpe_ratio') AS REAL) DESC,
                     c.observed_at DESC, c.candidate_id LIMIT ?
        """
        chart_rows = list(connection.execute(chart_sql, _base_params() + historical_params + [CHART_LIMIT]))
        survivor_sql = BASE_CTE + f"""
            SELECT c.* FROM candidates c WHERE c.survivor=1 AND {historical_filter}
            ORDER BY CAST(json_extract(c.oos_metrics_json, '$.sharpe_ratio') AS REAL) DESC,
                     c.observed_at DESC, c.candidate_id LIMIT ?
        """
        survivor_rows = list(connection.execute(survivor_sql, _base_params() + historical_params + [SURVIVOR_LIMIT]))
        latest_row = connection.execute(
            RUN_BASE_CTE + f"""
                SELECT r.* FROM run_records r
                WHERE (r.metrics_json IS NOT NULL OR r.error_summary IS NOT NULL)
                  AND {run_filter}
                ORDER BY r.observed_at DESC, r.run_id DESC
                LIMIT 1
            """,
            _base_params() + run_params,
        ).fetchone()
        return {
            "available": True, "message": "Read-only research state loaded.", "database": str(database_path),
            "window": window, "market": market, "observed_at": datetime.now(timezone.utc).isoformat(),
            "counts": {"running": running, "queued": queued, "survivors": survivors_count, "advancing": advancing, "needs": None, "failed": failed},
            "stages": stages, "operation": {"active": running + queued, "terminal": terminal, "bottleneck": str(bottleneck).replace("_", " ").title(), "median_minutes": None},
            "chart": [_row_view(row, oos_metric=True, report=_unseen_report(row, database_path, unseen_report)) for row in chart_rows],
            "survivors": [_row_view(row, oos_metric=True, report=_unseen_report(row, database_path, unseen_report)) for row in survivor_rows],
            "latest_finding": _row_view(latest_row, oos_metric=True, report=_unseen_report(latest_row, database_path, unseen_report)) if latest_row else None,
            "chart_limit": CHART_LIMIT, "survivor_limit": SURVIVOR_LIMIT, "population_count": population,
        }
    except (sqlite3.Error, ValueError, TypeError) as exc:
        return _empty_snapshot(database=database_path, message=f"Research state could not be projected safely: {exc}", window=window, market=market)
    finally:
        connection.close()


DRILLDOWN_SORT_FIELDS = {
    "title": "title", "candidate_id": "candidate_id", "run_id": "run_id",
    "symbol": "symbol", "stage": "stage", "status": "status", "observed_at": "observed_at",
}


def load_drilldown_page(
    *, kind: str, window: str, market: str, start: int, end: int,
    sort_model: list[dict[str, Any]] | None = None,
    filter_model: dict[str, dict[str, Any]] | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Return one bounded, sorted and filtered drawer page with exact identities."""
    database_path = Path(database) if database is not None else configured_database_path()
    connection, _error = _validated_connection(database_path)
    if connection is None or kind in {"needs", "destination"}:
        return {"rowData": [], "rowCount": 0}
    run_kinds = {"running", "queued"}
    try:
        if kind in run_kinds:
            status_stage = {
                "running": f"r.run_status='running' AND {live_run_clause('r.run_status','r.candidate_id')}", "queued": "r.run_status='created'",
            }[kind]
            source = f"""
                SELECT DISTINCT r.candidate_id, r.title, r.symbol, r.run_id,
                       r.stage, r.run_status AS status, r.observed_at
                FROM run_records r
                WHERE {status_stage}
            """
            include_window = False
        else:
            condition = {
                "advancing": ADVANCING_CONDITION,
                **{key: f"c.reach>={level}" for key, level in FUNNEL_LEVEL.items() if key not in {"submitted", "survivors"}},
                "survivors": "c.survivor=1",
                "ranked": "c.survivor=1",
                "submitted": "1=1",
            }.get(kind, "1=0")
            include_window = kind != "advancing"
        if kind in run_kinds:
            filter_clause, filter_params = _run_filter_clause(
                window=window, market=market, alias="r", include_window=include_window
            )
            source += f" AND {filter_clause}"
        else:
            filter_clause, filter_params = _filter_clause(window=window, market=market, alias="c", include_window=include_window)
            source = f"SELECT c.candidate_id, c.title, c.symbol, c.run_id, c.stage, c.run_status AS status, c.observed_at FROM candidates c WHERE {condition} AND {filter_clause}"
        params = _base_params() + filter_params
        filters: list[str] = []
        for field, model in (filter_model or {}).items():
            column = DRILLDOWN_SORT_FIELDS.get(field)
            value = str(model.get("filter") or "").strip()
            if column and value:
                filters.append(f"LOWER(COALESCE(CAST({column} AS TEXT),'')) LIKE ?")
                params.append(f"%{value.lower()}%")
        outer_where = " WHERE " + " AND ".join(filters) if filters else ""
        order = "observed_at DESC, candidate_id"
        if sort_model:
            requested = sort_model[0]
            column = DRILLDOWN_SORT_FIELDS.get(str(requested.get("colId")))
            if column:
                direction = "DESC" if requested.get("sort") == "desc" else "ASC"
                order = f"{column} {direction}, candidate_id"
        base = RUN_BASE_CTE if kind in run_kinds else BASE_CTE
        cte_source = base + f", drawer_records AS ({source})"
        total = _scalar(connection, cte_source + f" SELECT COUNT(*) FROM drawer_records{outer_where}", params)
        rows = list(connection.execute(cte_source + f" SELECT candidate_id,title,symbol,run_id,stage,status,observed_at FROM drawer_records{outer_where} ORDER BY {order} LIMIT ? OFFSET ?", params + [max(1, end - start), max(0, start)]))
        return {"rowData": [dict(row) for row in rows], "rowCount": total}
    except (sqlite3.Error, ValueError, TypeError):
        return {"rowData": [], "rowCount": 0}
    finally:
        connection.close()


__all__ = [
    "configured_database_path", "load_dashboard_snapshot", "load_drilldown_page",
]
